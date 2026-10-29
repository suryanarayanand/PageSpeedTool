"""Upgrade exports from an already-running older server without interrupting audits."""
import argparse
import json
import time
from pathlib import Path

from engine import OUTPUT, ROOT, REPORT_LAYOUT_VERSION, now, write_reports


def refresh(output):
    updated = []
    for path in Path(output).glob('*/run.json'):
        state = json.loads(path.read_text(encoding='utf-8'))
        folder = path.parent
        excel, html, marker = folder / 'report.xlsx', folder / 'report.html', folder / 'report_layout.json'
        if state.get('status') not in {'Complete', 'Partial', 'Failed'} or not excel.exists() or not html.exists():
            continue
        if marker.exists():
            version = json.loads(marker.read_text(encoding='utf-8')).get('version')
            if version == REPORT_LAYOUT_VERSION and marker.stat().st_mtime_ns >= max(excel.stat().st_mtime_ns, html.stat().st_mtime_ns):
                continue
        write_reports(state, folder)
        updated.append(folder.name)
        print(now(), 'Updated reference layout:', folder.name, flush=True)
    return updated


if __name__ == '__main__':
    from server import process_running
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server-pid', type=int, required=True)
    args = parser.parse_args()
    while process_running(args.server_pid):
        pid_file = ROOT / 'server.pid'
        if pid_file.exists() and pid_file.read_text(encoding='utf-8').strip() != str(args.server_pid):
            break
        try:
            refresh(OUTPUT)
        except (OSError, ValueError) as error:
            print(now(), 'Will retry report refresh:', type(error).__name__, flush=True)
        time.sleep(3)
