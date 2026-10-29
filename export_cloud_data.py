"""Export report history for transfer to the cloud data volume."""
import argparse
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import tarfile
import tempfile

from progressive_report import TERMINAL, history_lock
from storage import DATA_ROOT


def export_data(destination, source=DATA_ROOT):
    destination = Path(destination).resolve()
    source = Path(source).resolve()
    if any((source / name).is_symlink() for name in ('history', 'reports')):
        raise ValueError('Report data directories must not be symbolic links.')
    if any(parent in destination.parents for parent in (source / 'history', source / 'reports')):
        raise ValueError('Save the export outside the history and reports directories.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    files = []
    with history_lock(source / 'history'):
        for name in ('report.xlsx', 'report.html', 'summary.json'):
            path = source / 'history' / name
            if path.is_file() and not path.is_symlink():
                files.append(path)
        files.extend(path for path in (source / 'history/runs').glob('*.json') if path.is_file() and not path.is_symlink())
        for checkpoint in sorted((source / 'reports').glob('*/run.json')):
            if checkpoint.parent.is_symlink():
                continue
            state = json.loads(checkpoint.read_text(encoding='utf-8'))
            if state.get('status') not in TERMINAL:
                continue
            files.extend(path for path in checkpoint.parent.rglob('*')
                         if path.is_file() and not path.is_symlink()
                         and path.suffix in {'.json', '.html', '.xlsx', '.xml', '.txt', '.png', '.csv'})
        manifest = {'created': datetime.now(timezone.utc).isoformat(), 'files': len(files),
                    'data_directories': ['history', 'reports']}
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(prefix='.pagespeed-export-', suffix='.tar.gz',
                                             dir=destination.parent, delete=False) as handle:
                temporary_path = Path(handle.name)
                with tarfile.open(fileobj=handle, mode='w:gz') as archive:
                    for path in files:
                        archive.add(path, arcname=path.relative_to(source).as_posix(), recursive=False)
                    metadata = json.dumps(manifest, indent=2).encode()
                    entry = tarfile.TarInfo('migration.json')
                    entry.size = len(metadata)
                    archive.addfile(entry, io.BytesIO(metadata))
            temporary_path.replace(destination)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    arguments = parser.parse_args()
    print(json.dumps(export_data(arguments.destination), indent=2))
