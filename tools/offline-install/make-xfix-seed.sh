#!/bin/sh
# xfix 検証用の seed (CIDATA) を user-data 原文から作る。
# 使い方: sh tools/offline-install/make-xfix-seed.sh <user-data> <meta-data> <out-seed.iso> [extra-file]
# 例: sh tools/offline-install/make-xfix-seed.sh \
#       build/evidence/install-sources/xfix/user-data8 \
#       build/evidence/install-sources/xfix/meta-data8 \
#       build/evidence/install-sources/xfix/seed8.iso
# user-data の原文が正本で、この道具は ISO 化だけを行う。
# extra-file を渡すと seed ISO 内の別ファイル (同名) として同梱する
# (late-commands が CIDATA ラベルで mount して読む一覧用)。
set -eu
HERE=$(CDPATH='' cd -- "$(dirname "$0")/../.." && pwd)
USERDATA=${1:?usage: make-xfix-seed.sh '<user-data> <meta-data> <out-seed.iso> [extra-file]'}
METADATA=${2:?usage: make-xfix-seed.sh '<user-data> <meta-data> <out-seed.iso> [extra-file]'}
OUT=${3:?usage: make-xfix-seed.sh '<user-data> <meta-data> <out-seed.iso> [extra-file]'}
EXTRA=${4:-}
[ -f "$USERDATA" ] || { echo "no user-data: $USERDATA" >&2; exit 1; }
[ -f "$METADATA" ] || { echo "no meta-data: $METADATA" >&2; exit 1; }
case "$USERDATA" in /*) ;; *) USERDATA="$HERE/$USERDATA" ;; esac
case "$METADATA" in /*) ;; *) METADATA="$HERE/$METADATA" ;; esac
case "$OUT" in /*) ;; *) OUT="$HERE/$OUT" ;; esac
case "$USERDATA" in "$HERE"/*) ;; *) echo "worktree only" >&2; exit 1 ;; esac
case "$OUT" in "$HERE"/*) ;; *) echo "worktree only" >&2; exit 1 ;; esac
if [ -n "$EXTRA" ]; then
  case "$EXTRA" in /*) ;; *) EXTRA="$HERE/$EXTRA" ;; esac
  [ -f "$EXTRA" ] || { echo "no extra-file: $EXTRA" >&2; exit 1; }
  case "$EXTRA" in "$HERE"/*) ;; *) echo "worktree only" >&2; exit 1 ;; esac
  EXTRA_BASE=$(basename "$EXTRA")
  xorriso -as mkisofs -o "$OUT" -V CIDATA -J -r \
    -graft-points "user-data=$USERDATA" "meta-data=$METADATA" "$EXTRA_BASE=$EXTRA" \
    >"$OUT-mkisofs.log" 2>&1
else
  xorriso -as mkisofs -o "$OUT" -V CIDATA -J -r \
    -graft-points "user-data=$USERDATA" "meta-data=$METADATA" \
    >"$OUT-mkisofs.log" 2>&1
fi
xorriso -indev "$OUT" -pvd_info -- 2>&1 | grep -i -E "volume id|label" | head -3
ls -lh "$OUT"
