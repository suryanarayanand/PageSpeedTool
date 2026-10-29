#!/bin/bash
set -e

cd -- "$(dirname -- "$0")"
report_port="${PAGESPEED_PORT:-5055}"
if [[ ! "$report_port" =~ ^[0-9]+$ ]] || (( report_port < 1 || report_port > 65535 )); then
    printf 'PAGESPEED_PORT must be a number between 1 and 65535.\n' >&2
    exit 1
fi
report_pid="$(lsof -nP -t -iTCP:"$report_port" -sTCP:LISTEN 2>/dev/null | head -n 1)"
if [[ -n "$report_pid" ]]; then
    report_directory="$(lsof -a -p "$report_pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p')"
    if [[ "$report_directory" != "$(pwd -P)" ]]; then
        printf 'Port %s belongs to another application; it cannot be restarted by this launcher.\n' "$report_port" >&2
        exit 1
    fi
    # Check saved checkpoints before stopping this tool's server.
    .venv/bin/python - "$report_pid" <<'PY'
import json
from pathlib import Path
import sys

pid = int(sys.argv[1])
for path in Path('reports').glob('*/run.json'):
    state = json.loads(path.read_text(encoding='utf-8'))
    if state.get('status') == 'Running' and state.get('worker_pid') == pid:
        sys.exit('An article run is active. Let it finish before restarting the portal.')
PY
    printf 'Restarting the existing PageSpeed portal...\n'
    kill -TERM "$report_pid"
    for report_wait in {1..20}; do
        if ! kill -0 "$report_pid" 2>/dev/null; then
            break
        fi
        sleep 0.25
    done
    if kill -0 "$report_pid" 2>/dev/null; then
        printf 'The existing portal has not stopped yet. Try this launcher again after it exits.\n' >&2
        exit 1
    fi
fi
exec ./Start_PageSpeed_Reporter.command
