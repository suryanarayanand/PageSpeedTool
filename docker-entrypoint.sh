#!/bin/sh
set -eu

if [ "$(id -u)" -eq 0 ]; then
    mkdir -p /data
    chown -R pagespeed:pagespeed /data
    exec gosu pagespeed /usr/bin/tini -- "$@"
fi
exec /usr/bin/tini -- "$@"
