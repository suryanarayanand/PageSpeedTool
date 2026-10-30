"""Shared paths for local use and a mounted cloud data volume."""
import os
from pathlib import Path
from env_config import load_local_env

ROOT = Path(__file__).resolve().parent
load_local_env(ROOT / '.env')
DATA_ROOT = Path(os.environ.get('PAGESPEED_DATA_DIR', str(ROOT))).expanduser().resolve()
OUTPUT = DATA_ROOT / 'reports'
