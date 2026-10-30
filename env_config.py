"""Load local API settings without evaluating shell expressions or exposing values."""
import os
from pathlib import Path
import shlex

LOCAL_SETTINGS = frozenset({'PAGESPEED_API_KEY', 'CRUX_API_KEY', 'PAGESPEED_COLLECTOR'})


def load_local_env(path, environment=None):
    environment = os.environ if environment is None else environment
    path = Path(path)
    if not path.is_file():
        return set()
    loaded = set()
    for number, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:].lstrip()
        name, separator, value = line.partition('=')
        name = name.strip()
        if not separator or name not in LOCAL_SETTINGS:
            continue
        try:
            words = shlex.split(value, comments=True, posix=True)
        except ValueError:
            raise ValueError(f'Invalid quoting in .env on line {number}.') from None
        if len(words) > 1:
            raise ValueError(f'Use one value after the equals sign in .env on line {number}.')
        value = words[0] if words else ''
        if not value or name in environment:
            continue
        if name == 'PAGESPEED_COLLECTOR' and value not in {'api', 'browser'}:
            raise ValueError(f'PAGESPEED_COLLECTOR must be api or browser in .env on line {number}.')
        environment[name] = value
        loaded.add(name)
    return loaded
