"""Isolate HTTP work so its caller can stop stalled DNS, TLS, or body reads."""
import json
import sys

from engine import FetchError, _fetch_in_process


def main():
    job = json.load(sys.stdin)
    try:
        raw = _fetch_in_process(**job)
    except FetchError as exc:
        # Request URLs and credentials never appear in command-line arguments
        # or this error protocol. engine supplies sanitized error messages.
        sys.stderr.write(json.dumps({'message': str(exc), 'status': exc.status}))
        return 2
    sys.stdout.buffer.write(raw)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
