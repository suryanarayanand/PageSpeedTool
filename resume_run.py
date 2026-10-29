"""Resume an interrupted website run without changing its sampled articles."""
import argparse
import json
import os
from pathlib import Path

from browser_collector import collect
from engine import METRICS, FetchError, extract_psi, now, save_json, write_reports


def resume(folder):
    folder = Path(folder).resolve()
    path = folder / 'run.json'
    state = json.loads(path.read_text(encoding='utf-8'))
    from server import process_running
    if state.get('status') == 'Running' and process_running(state.get('worker_pid')):
        raise ValueError('This run is still active. Wait for its worker to finish before resuming.')
    if state['config'].get('collector') != 'browser':
        raise ValueError('Resume currently supports website runs only')
    state.update(status='Running', worker_pid=os.getpid(), resumed=now())
    state.pop('finished', None)
    rows = {(r['Publication'], r['URL'], r['Device']): r for r in state['results']}
    total = len(state['samples']) * len(state['config']['strategies'])
    done = 0
    for index, sample in enumerate(state['samples']):
        for device in state['config']['strategies']:
            identity = (sample['Publication'], sample['URL'], device)
            old = rows.get(identity)
            done += 1
            if old and old['Status'] in {'OK', 'Partial'}:
                continue
            state['message'] = f'Analyzing {done}/{total}: {sample["Publication"]} / {device}'
            save_json(path, state)
            print(state['message'], flush=True)
            prior = next((r.get('PageSpeed link') for r in rows.values() if r['URL'] == sample['URL'] and r.get('Collection method') == 'PageSpeed website'), None)
            stem = f'{index + 1:03d}_{sample["Publication"]}_{device}_resumed'
            try:
                row = collect(sample['URL'], device, folder / 'raw', stem, analysis_url=prior)
            except FetchError as exc:
                row = extract_psi({})
                row['Error'] = str(exc)
            row.update(sample)
            row['Device'] = device
            row.setdefault('PageSpeed link', 'https://pagespeed.web.dev/')
            rows[identity] = row
            state['results'] = list(rows.values())
            save_json(path, state)
            print(row['Status'], row.get('Performance'), row.get('Error'), flush=True)
    ok = sum(r['Status'] == 'OK' for r in state['results'])
    has_data = any(any(r.get(k) is not None for k in METRICS) for r in state['results'])
    state['status'] = 'Complete' if ok == total and total and not state['errors'] else 'Partial' if has_data else 'Failed'
    state['finished'] = now()
    state['message'] = f'{ok}/{total} complete checks. ' + ('Report ready.' if state['status'] == 'Complete' else 'Available measurements saved; review the missing values.')
    write_reports(state, folder)
    save_json(path, state)
    print(state['status'], folder, flush=True)
    from progressive_report import update_progressive
    update_progressive(state, folder.parent)
    return state


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    resume(parser.parse_args().folder)
