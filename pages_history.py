"""Persist canonical report snapshots on a separate Git branch for free hosting."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

from engine import ROOT, OUTPUT, validate_config
from progressive_report import TERMINAL, history_root, run_date

BRANCH = 'report-history'
README = b'# PageSpeed report history\n\nCanonical dated report snapshots used to rebuild the public portal.\n'


def git(repository, *arguments, data=None, check=True, environment=None):
    result = subprocess.run(['git', '-C', str(repository), *arguments], input=data,
                            capture_output=True, env=environment)
    if check and result.returncode:
        raise RuntimeError('Git history operation failed: ' + arguments[0] + '. Check repository permissions and connectivity.')
    return result


def snapshot(content, identifier):
    state = json.loads(content)
    if state.get('id') != identifier or state.get('status') not in TERMINAL:
        raise ValueError('Invalid completed history snapshot: ' + identifier)
    run_date(state)
    public = {key: state[key] for key in ('id', 'started', 'finished', 'seed', 'status', 'message', 'samples', 'results', 'errors') if key in state}
    public['config'] = validate_config(state['config'])
    return json.dumps(public, indent=2, sort_keys=True, ensure_ascii=False).encode('utf-8')


def remote_head(repository):
    result = git(repository, 'ls-remote', '--exit-code', '--heads', 'origin', 'refs/heads/' + BRANCH, check=False)
    if result.returncode == 2:
        return None
    if result.returncode:
        raise RuntimeError('Cannot read the history branch. Existing report history has been left untouched.')
    git(repository, 'fetch', '--quiet', '--depth=1', 'origin', 'refs/heads/' + BRANCH)
    return git(repository, 'rev-parse', 'FETCH_HEAD').stdout.decode().strip()


def restore_history(repository=ROOT, output=OUTPUT, only_missing=False, head=None, seed=None):
    head = remote_head(repository) if head is None else head
    destination = history_root(output) / 'runs'
    destination.mkdir(parents=True, exist_ok=True)
    if head is None:
        seed = ROOT / 'cloud_history_seed' if seed is None else Path(seed)
        for path in seed.glob('*.json'):
            target = destination / path.name
            if not target.exists():
                target.write_bytes(snapshot(path.read_bytes(), path.stem))
        return len(list(destination.glob('*.json')))
    paths = git(repository, 'ls-tree', '-r', '--name-only', head, '--', 'runs/').stdout.decode().splitlines()
    for name in paths:
        if not re.fullmatch(r'runs/[A-Za-z0-9_-]{1,100}\.json', name):
            raise ValueError('Unexpected file in report history')
        target = destination / Path(name).name
        if only_missing and target.exists():
            continue
        content = git(repository, 'show', head + ':' + name).stdout
        target.write_bytes(snapshot(content, target.stem))
    return len(list(destination.glob('*.json')))


def push_history(repository=ROOT, output=OUTPUT):
    head = remote_head(repository)
    if head is not None:
        restore_history(repository, output, only_missing=True, head=head)
    directory = history_root(output) / 'runs'
    entries = []
    for path in sorted(directory.glob('*.json')):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}\.json', path.name):
            raise ValueError('Invalid history filename')
        content = snapshot(path.read_bytes(), path.stem)
        blob = git(repository, 'hash-object', '-w', '--stdin', data=content).stdout.decode().strip()
        entries.append(f'100644 blob {blob}\t{path.name}\n')
    runs_tree = git(repository, 'mktree', data=''.join(entries).encode()).stdout.decode().strip()
    readme = git(repository, 'hash-object', '-w', '--stdin', data=README).stdout.decode().strip()
    tree = git(repository, 'mktree', data=f'100644 blob {readme}\tREADME.md\n040000 tree {runs_tree}\truns\n'.encode()).stdout.decode().strip()
    if head is not None:
        previous = git(repository, 'rev-parse', head + '^{tree}').stdout.decode().strip()
        if tree == previous:
            return {'changed': False, 'runs': len(entries)}
    environment = dict(os.environ, GIT_AUTHOR_NAME='github-actions[bot]',
                       GIT_AUTHOR_EMAIL='41898282+github-actions[bot]@users.noreply.github.com',
                       GIT_COMMITTER_NAME='github-actions[bot]',
                       GIT_COMMITTER_EMAIL='41898282+github-actions[bot]@users.noreply.github.com')
    arguments = ['commit-tree', tree] + (['-p', head] if head else [])
    commit = git(repository, *arguments, data=b'Update dated PageSpeed report history\n', environment=environment).stdout.decode().strip()
    # A normal push refuses concurrent non-fast-forward changes; history is
    # never force-pushed and the source branch is never checked out or modified.
    git(repository, 'push', '--quiet', 'origin', commit + ':refs/heads/' + BRANCH)
    return {'changed': True, 'runs': len(entries)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['restore', 'push'])
    arguments = parser.parse_args()
    result = restore_history() if arguments.operation == 'restore' else push_history()
    print(json.dumps(result))
