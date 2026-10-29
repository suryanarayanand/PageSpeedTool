"""Run the chosen article count on a cloud runner, without a client browser."""
import json
import os

from engine import ROOT, OUTPUT, run, validate_config


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


if __name__ == '__main__':
    config = audit_config()
    folder = run(config, OUTPUT, progress=lambda message: print(message, flush=True))
    state = json.loads((folder / 'run.json').read_text(encoding='utf-8'))
    print('Saved run:', state['id'], '| Status:', state['status'])
    if state['status'] != 'Complete':
        print('::warning::Some Google measurements are unavailable. Available data and errors will still be published.')
