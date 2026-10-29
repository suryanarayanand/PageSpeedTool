"""Shared paths for local use and a mounted cloud data volume."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_ROOT = Path(os.environ.get('PAGESPEED_DATA_DIR', str(ROOT))).expanduser().resolve()
OUTPUT = DATA_ROOT / 'reports'
