#!/bin/sh
# R2b専用。既存assemble.shの出力と更新経路には触れない。
set -eu
HERE=$(CDPATH='' cd -- "$(dirname "$0")/../.." && pwd)
cd "$HERE"
mkdir -p build/work/tmp build/work/logs
TMPDIR=$HERE/build/work/tmp
PYTHONDONTWRITEBYTECODE=1
export TMPDIR PYTHONDONTWRITEBYTECODE
exec python3 -u -I tools/ubuntu-merge/assemble_stages.py "$@"
