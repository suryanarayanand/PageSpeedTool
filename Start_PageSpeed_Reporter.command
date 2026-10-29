#!/bin/bash
set -e

cd -- "$(dirname -- "$0")"
trap 'printf "\nStartup failed. Review the error above and run this launcher again.\n" >&2' ERR

if [[ ! -x .venv/bin/python ]]; then
    if [[ -x "$HOME/.local/bin/python3.12" ]]; then
        "$HOME/.local/bin/python3.12" -m venv .venv
    else
        python3 -m venv .venv
    fi
fi

if ! .venv/bin/python -c 'import flask, openpyxl, waitress, playwright.sync_api' 2>/dev/null; then
    printf 'Installing Python dependencies. Internet access is required for this step.\n'
    .venv/bin/python -m pip install -r requirements.txt
fi

report_url="http://127.0.0.1:${PAGESPEED_PORT:-5055}"
report_port="${PAGESPEED_PORT:-5055}"
if [[ ! "$report_port" =~ ^[0-9]+$ ]] || (( report_port < 1 || report_port > 65535 )); then
    printf 'PAGESPEED_PORT must be a number between 1 and 65535.\n' >&2
    exit 1
fi
report_pid="$(lsof -nP -t -iTCP:"$report_port" -sTCP:LISTEN 2>/dev/null | head -n 1)"
if [[ -n "$report_pid" ]]; then
    report_directory="$(lsof -a -p "$report_pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p')"
    if [[ "$report_directory" == "$(pwd -P)" ]]; then
        printf 'The portal is already running at %s.\nUse Restart_PageSpeed_Reporter.command to load updated code.\n' "$report_url"
        open "$report_url" >/dev/null 2>&1 || true
        exit 0
    fi
    printf 'Port %s is already used by another application. Set PAGESPEED_PORT to a free port.\n' "$report_port" >&2
    exit 1
fi
printf '\nOpen %s in your browser.\nKeep this Terminal window open. Press Control+C to stop.\n\n' "$report_url"

# Open the browser only once the local interface is ready.
.venv/bin/python - "$report_url" <<'PY' &
import subprocess
import sys
import time
import urllib.error
import urllib.request

url = sys.argv[1]
for _ in range(20):
    try:
        with urllib.request.urlopen(url, timeout=1) as response:
            ready = response.status == 200
    except (urllib.error.URLError, OSError):
        ready = False
    if ready:
        subprocess.run(['open', url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        break
    time.sleep(1)
PY

exec .venv/bin/python server.py
