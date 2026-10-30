"""Run the chosen article count on a cloud runner, without a client browser."""
import json
import os
from html import escape
from pathlib import Path

from engine import ROOT, OUTPUT, METRICS, run, validate_config


def audit_config(environment=None):
    environment = os.environ if environment is None else environment
    config = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
    config['sample_size'] = int(environment.get('ARTICLE_COUNT') or config['sample_size'])
    sites = environment.get('PUBLICATIONS', '').strip()
    if sites:
        requested = [name.strip() for name in sites.split(',') if name.strip()]
        unknown = set(requested) - set(config['feeds'])
        if unknown:
            raise ValueError('No RSS feed configured for: ' + ', '.join(sorted(unknown)))
        config['feeds'] = {name: config['feeds'][name] for name in requested}
    devices = environment.get('DEVICES', 'both') or 'both'
    config['strategies'] = ['mobile', 'desktop'] if devices == 'both' else [devices]
    collector = environment.get('COLLECTOR', 'auto') or 'auto'
    if collector == 'auto':
        collector = 'api' if environment.get('PAGESPEED_API_KEY') else 'browser'
    if collector == 'api' and not environment.get('PAGESPEED_API_KEY'):
        raise ValueError('Set the PAGESPEED_API_KEY repository secret, or use the auto/browser collector.')
    config['collector'] = collector
    return validate_config(config)


def summarize_audit(state):
    rows = state['results']
    measured = sum(any(row.get(metric) is not None for metric in METRICS) for row in rows)
    errors = list(dict.fromkeys(str(row['Error']) for row in rows + state.get('errors', []) if row.get('Error')))
    print('Measurement status:', state['status'], '| Checks with measurements:', str(measured) + '/' + str(len(rows)), flush=True)
    if not measured:
        print('::warning::No new measurements were collected. The published report contains failure details and retained history.')
    elif state['status'] != 'Complete':
        print('::warning::Some measurements are unavailable. Available values are published; unavailable values remain N/A.')
    if errors:
        print('Measurement errors:', json.dumps(errors[:3], ensure_ascii=True), flush=True)
    destination = os.getenv('GITHUB_STEP_SUMMARY')
    if destination:
        lines = ['## PageSpeed measurement results',
                 '**Measurement status: ' + escape(state['status']) + '**',
                 str(measured) + '/' + str(len(rows)) + ' checks returned measurements.',
                 'Run: `' + escape(state['id']) + '`',
                 'Deployment publishes available values and failure details; deployment success does not establish measurement success.']
        if errors:
            lines.append('### Measurement errors')
            lines.extend('- ' + escape(error[:1500]).replace('\n', ' ') for error in errors[:3])
        with Path(destination).open('a', encoding='utf-8') as handle:
            handle.write('\n\n'.join(lines) + '\n')
    return measured


if __name__ == '__main__':
    config = audit_config()
    folder = run(config, OUTPUT, progress=lambda message: print(message, flush=True))
    state = json.loads((folder / 'run.json').read_text(encoding='utf-8'))
    print('Saved run:', state['id'], '| Status:', state['status'])
    summarize_audit(state)
