"""Local web interface. Run separately from the Maestro portal on port 5055."""
import json
import os
import secrets
import threading
import sys
from datetime import datetime, timezone

from flask import Flask, abort, jsonify, render_template, request, send_from_directory
from engine import ROOT, OUTPUT, STYLE, run, validate_config, save_json

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100_000
TOKEN = secrets.token_urlsafe(32)
lock = threading.Lock()
active = None


@app.before_request
def local_only():
    if request.host.split(":")[0] not in {"127.0.0.1", "localhost"}:
        abort(403)
    if request.method == "POST" and not secrets.compare_digest(request.headers.get("X-Report-Token", ""), TOKEN):
        abort(403)


@app.get("/")
def index():
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    return render_template("home.html", token=TOKEN, config=config,
                           names={"TH": "The Hindu", "BL": "BusinessLine", "SS": "Sportstar", "FL": "Frontline"})


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
    if state.get("status") == "Running" and state.get("id") != active and not process_running(state.get('worker_pid')):
        state.update(status="Interrupted", message="Server stopped before completion. Start a new run; collected data is retained.")
    state["has_reports"] = (path.parent / "report.html").exists() and (path.parent / "report.xlsx").exists()
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
    (ROOT / 'server.pid').write_text(str(os.getpid()), encoding='utf-8')
    print("Open http://127.0.0.1:5055 in your browser", flush=True)
    sys.path.insert(0, str(ROOT / "vendor"))
    from waitress import serve
    serve(app, host="127.0.0.1", port=int(os.getenv("PAGESPEED_PORT", "5055")), threads=4)
