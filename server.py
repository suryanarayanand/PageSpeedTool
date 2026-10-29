"""PageSpeed portal with local and public cloud report modes."""
import json
import os
import secrets
import threading
import sys
from datetime import datetime, timezone
from urllib.parse import urlsplit

from flask import Flask, Response, abort, jsonify, redirect, render_template, request, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix
from engine import ROOT, OUTPUT, STYLE, WORKER_INSTANCE, run, validate_config, save_json
from runtime_config import configuration_error, server_settings
from storage import DATA_ROOT

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100_000
app.config.update(server_settings())
proxy_count = int(os.getenv('PAGESPEED_TRUSTED_PROXIES', '0'))
if proxy_count:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=proxy_count, x_proto=proxy_count, x_host=0, x_port=0)
TOKEN = secrets.token_urlsafe(32)
lock = threading.Lock()
active = None


@app.before_request
def access_policy():
    if request.path == '/health':
        return None
    host = urlsplit('http://' + request.host).hostname
    if app.config['CLOUD_MODE']:
        error = configuration_error(app.config)
        if error:
            return jsonify(error=error), 503
        if host not in app.config['ALLOWED_REPORT_HOSTS']:
            abort(403)
        if app.config['REQUIRE_HTTPS'] and not request.is_secure:
            return redirect(request.url.replace('http://', 'https://', 1), code=308)
        manage = request.path == '/manage' or request.method not in {'GET', 'HEAD', 'OPTIONS'}
        if manage or not app.config['PUBLIC_REPORTS']:
            auth = request.authorization
            username = (auth.username or '') if auth and auth.type == 'basic' else ''
            password = (auth.password or '') if auth and auth.type == 'basic' else ''
            user_ok = secrets.compare_digest(username.encode('utf-8'), app.config['ADMIN_USERNAME'].encode('utf-8'))
            pass_ok = secrets.compare_digest(password.encode('utf-8'), app.config['ADMIN_PASSWORD'].encode('utf-8'))
            if not (user_ok and pass_ok):
                return Response('Sign in to manage PageSpeed audits.', 401,
                                {'WWW-Authenticate': 'Basic realm="PageSpeed management", charset="UTF-8"'})
    elif host not in {'127.0.0.1', 'localhost', '::1'}:
        abort(403)
    if request.method == "POST" and not secrets.compare_digest(request.headers.get("X-Report-Token", ""), TOKEN):
        abort(403)


@app.get("/")
def index():
    if app.config['CLOUD_MODE'] and app.config['PUBLIC_REPORTS']:
        return render_template('public_dashboard.html', base_style=STYLE)
    return management_page()


@app.after_request
def response_policy(response):
    if app.config['CLOUD_MODE']:
        response.headers.setdefault('X-Robots-Tag', 'noindex, nofollow')
        if request.path == '/manage' or request.method not in {'GET', 'HEAD'}:
            response.headers['Cache-Control'] = 'no-store'
    return response


def management_page():
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    collector = os.getenv('PAGESPEED_COLLECTOR')
    if collector in {'api', 'browser'}:
        config['collector'] = collector
    return render_template("home.html", token=TOKEN, config=config, cloud=app.config['CLOUD_MODE'],
                           allow_browser=app.config['ALLOW_BROWSER'],
                           names={"TH": "The Hindu", "BL": "BusinessLine", "SS": "Sportstar", "FL": "Frontline"})


@app.get('/manage')
def manage():
    return management_page()


@app.get('/health')
def health():
    if configuration_error(app.config):
        return jsonify(status='configuration_required'), 503
    return jsonify(status='ok', progressive_history=True)


@app.get("/report-format")
def report_format():
    from openpyxl import load_workbook
    from excel_layout import TEMPLATE
    from report_preview import workbook_preview_html
    book = load_workbook(TEMPLATE)
    try:
        return render_template('report_format.html', preview=workbook_preview_html(book), base_style=STYLE)
    finally:
        book.close()


@app.get("/report-template.xlsx")
def report_template():
    from excel_layout import TEMPLATE
    return send_from_directory(TEMPLATE.parent, TEMPLATE.name, as_attachment=True,
                               download_name='TH,BL,FL,SS- Core Web Vitals - Template.xlsx')


@app.post("/runs")
def start():
    global active
    body = request.get_json()
    if not isinstance(body, dict):
        return jsonify(error="Provide a configuration object"), 400
    try:
        config = validate_config(body)
    except (ValueError, TypeError, AttributeError) as exc:
        return jsonify(error=str(exc)), 400
    if config['collector'] == 'browser' and not app.config['ALLOW_BROWSER']:
        return jsonify(error='This deployment uses the Google API collector. Select Google API in Advanced settings.'), 400
    if config['collector'] == 'api' and not (body.get('psi_key') or os.getenv('PAGESPEED_API_KEY')):
        return jsonify(error='Enter a PageSpeed API key, or choose PageSpeed website in Advanced settings.'), 400
    with lock:
        if active:
            return jsonify(error="An analysis is already running", id=active), 409
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_") + secrets.token_hex(4)
        active = run_id
    def worker():
        global active
        try:
            run(config, psi_key=body.get("psi_key") or None, crux_key=body.get("crux_key") or None, run_id=run_id)
        except Exception:
            folder = OUTPUT / run_id
            folder.mkdir(parents=True, exist_ok=True)
            saved = folder / "run.json"
            state = json.loads(saved.read_text(encoding="utf-8")) if saved.exists() else {"id": run_id}
            state.update(status="Failed", message="Unexpected failure. Check disk space and server console; collected data remains in this run folder.")
            save_json(saved, state)
            app.logger.exception("Report generation failed")
        finally:
            with lock:
                active = None
    threading.Thread(target=worker, daemon=True).start()
    return jsonify(id=run_id), 202


def progressive_summary():
    from progressive_report import history_root, rebuild_progressive
    path = history_root(OUTPUT) / 'summary.json'
    if not path.exists():
        return rebuild_progressive(OUTPUT)
    return json.loads(path.read_text(encoding='utf-8'))


@app.get('/progressive/status')
def progressive_status():
    return jsonify(progressive_summary())


@app.post('/progressive/rebuild')
def progressive_rebuild():
    from progressive_report import rebuild_progressive
    try:
        return jsonify(rebuild_progressive(OUTPUT))
    except (OSError, ValueError):
        app.logger.exception('Could not rebuild daily history')
        return jsonify(error='Could not rebuild history. Saved runs are retained; check disk access and try again.'), 500


@app.get('/progressive/<filename>')
def progressive_file(filename):
    from progressive_report import history_root
    if filename not in {'report.xlsx', 'report.html'}:
        abort(404)
    progressive_summary()
    return send_from_directory(history_root(OUTPUT), filename,
                               as_attachment=filename == 'report.xlsx',
                               download_name='Core_Web_Vitals_Daily_History.xlsx' if filename == 'report.xlsx' else filename)


def process_running(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x100000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5
        try:
            return kernel.WaitForSingleObject(handle, 0) == 258
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def read_state(path):
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get('id') == active and state.get('status') in {'Complete', 'Partial', 'Failed'}:
        state.update(status='Running', message='Saving reports and daily history')
    previous_worker = state.get('worker_instance') not in {None, WORKER_INSTANCE}
    if state.get("status") == "Running" and state.get("id") != active and (previous_worker or not process_running(state.get('worker_pid'))):
        state.update(status="Interrupted", message="Server stopped before completion. Start a new run; collected data is retained.")
    state["has_reports"] = (path.parent / "report.html").exists() and (path.parent / "report.xlsx").exists()
    if state.get('started'):
        from progressive_report import run_date
        state['report_date'] = run_date(state).isoformat()
    return state


@app.get("/runs")
def history():
    return jsonify([read_state(p) for p in sorted(OUTPUT.glob("*/run.json"), reverse=True)[:100]])


@app.get("/runs/<run_id>")
def status(run_id):
    if not __import__("re").fullmatch(r"[0-9]{8}_[0-9]{6}_[a-f0-9]{8}", run_id):
        abort(404)
    path = OUTPUT / run_id / "run.json"
    if not path.exists():
        if active == run_id:
            return jsonify(id=run_id, status="Running", message="Starting")
        abort(404)
    return jsonify(read_state(path))


@app.get("/reports/<run_id>/<filename>")
def report(run_id, filename):
    if not __import__("re").fullmatch(r"[0-9]{8}_[0-9]{6}_[a-f0-9]{8}", run_id) or filename not in {"report.html", "report.xlsx", "run.json"}:
        abort(404)
    return send_from_directory(OUTPUT / run_id, filename, as_attachment=filename != "report.html")


if __name__ == "__main__":
    error = configuration_error(app.config)
    if error:
        raise SystemExit(error)
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    (DATA_ROOT / 'server.pid').write_text(str(os.getpid()), encoding='utf-8')
    port = int(os.getenv('PORT', os.getenv('PAGESPEED_PORT', '5055')))
    host = '0.0.0.0' if app.config['CLOUD_MODE'] else '127.0.0.1'
    print(f'PageSpeed portal listening on {host}:{port}', flush=True)
    sys.path.insert(0, str(ROOT / "vendor"))
    from waitress import serve
    serve(app, host=host, port=port, threads=4)
