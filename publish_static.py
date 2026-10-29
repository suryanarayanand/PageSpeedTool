"""Build the public report portal for free static hosting such as GitHub Pages."""
import argparse
import json
from pathlib import Path
import re
import shutil
import tempfile
import uuid

from jinja2 import Environment, FileSystemLoader, select_autoescape

from engine import ROOT, OUTPUT, STYLE, write_reports
from progressive_report import history_root, rebuild_progressive, run_date


def publish_site(destination, output=OUTPUT, repository=None):
    destination, output = Path(destination).resolve(), Path(output).resolve()
    history = history_root(output)
    if destination in {ROOT.resolve(), output, history.resolve()} or destination in output.parents:
        raise ValueError('Choose a separate generated site directory.')
    if destination.exists() and not (destination / '.pagespeed-site').is_file():
        raise ValueError('The destination contains files not owned by this site exporter.')
    if repository and not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Use a repository in owner/name format.')
    summary = rebuild_progressive(output)
    states = [json.loads(path.read_text(encoding='utf-8')) for path in (history / 'runs').glob('*.json')]
    states.sort(key=lambda state: (state['started'], state['id']), reverse=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.pagespeed-site-', dir=destination.parent) as temporary:
        stage = Path(temporary) / 'site'
        (stage / 'data').mkdir(parents=True)
        (stage / 'progressive').mkdir()
        shutil.copyfile(history / 'report.xlsx', stage / 'progressive/report.xlsx')
        progressive = (history / 'report.html').read_text(encoding='utf-8')
        progressive = progressive.replace('href="/"', 'href="../index.html"')
        (stage / 'progressive/report.html').write_text(progressive, encoding='utf-8')
        public_runs = []
        for state in states:
            identifier = state['id']
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', identifier):
                raise ValueError('Invalid archived run ID')
            target = stage / 'reports' / identifier
            target.mkdir(parents=True)
            # Rebuild from canonical snapshots, including days whose individual
            # report folders have been cleaned up. No new measurements are made.
            write_reports(state, target)
            (target / 'report_layout.json').unlink(missing_ok=True)
            public_runs.append({
                'id': identifier, 'status': state['status'], 'started': state['started'],
                'finished': state.get('finished'), 'report_date': run_date(state).isoformat(),
                'config': {'feeds': {site: [] for site in state['config']['feeds']}},
                'results': [{'Status': row['Status']} for row in state['results']], 'has_reports': True,
            })
        (stage / 'data/summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        (stage / 'data/runs.json').write_text(json.dumps(public_runs, indent=2), encoding='utf-8')
        environment = Environment(loader=FileSystemLoader(ROOT / 'templates'), autoescape=select_autoescape())
        manager = f'https://github.com/{repository}/actions/workflows/daily-pages.yml' if repository else None
        page = environment.get_template('public_dashboard.html').render(
            base_style=STYLE, manage_url=manager, progressive_prefix='progressive/',
            report_prefix='reports/', summary_url='data/summary.json', runs_url='data/runs.json',
        )
        (stage / 'index.html').write_text(page, encoding='utf-8')
        (stage / '.nojekyll').touch()
        (stage / '.pagespeed-site').write_text('Generated PageSpeed report portal\n')
        size = sum(path.stat().st_size for path in stage.rglob('*') if path.is_file())
        if size > 100 * 1024 * 1024:
            raise ValueError('The generated site exceeds the 100 MB publishing guard. Existing published data is retained.')
        old = None
        if destination.exists():
            old = destination.with_name(destination.name + '.previous-' + uuid.uuid4().hex)
            destination.replace(old)
        try:
            stage.replace(destination)
        except OSError:
            if old is not None:
                old.replace(destination)
            raise
        if old is not None:
            shutil.rmtree(old)
    return {'runs': len(public_runs), 'bytes': size, 'directory': str(destination)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--repository')
    args = parser.parse_args()
    print(json.dumps(publish_site(args.destination, repository=args.repository), indent=2))
