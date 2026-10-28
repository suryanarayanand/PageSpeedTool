"""Read-only connectivity check; no API key values are printed."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from engine import ROOT, fetch, parse_feed, FetchError


def check(url):
    try:
        raw = fetch(url, timeout=20, attempts=1)
        print(f'{url}: {len(parse_feed(raw, url))} unique article links', flush=True)
    except Exception as exc:
        print(f'{url}: {type(exc).__name__}: {exc}', flush=True)


if __name__ == '__main__':
    config = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(check, [url for feeds in config['feeds'].values() for url in feeds]))
    print('PAGESPEED_API_KEY configured:', bool(os.getenv('PAGESPEED_API_KEY')))
    print('CRUX_API_KEY configured:', bool(os.getenv('CRUX_API_KEY')))
