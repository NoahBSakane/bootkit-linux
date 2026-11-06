#!/bin/sh
# make-extra-list.py の単体試験(toram で元の媒体を外した後に apt が引くファイルの一覧)。通信不要。
set -eu
HERE=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
TOOL=$HERE/tools/ubuntu-merge/make-extra-list.py
WORK=$(mktemp -d "$HERE/test-extra-list.XXXXXX")
trap 'rm -rf "$WORK"' 0
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
ok() { printf 'ok: %s\n' "$*"; }

mkdir -p "$WORK/media/dists/r" "$WORK/media/pool/main/a" "$WORK/media/pool/main/b"
printf 'R' >"$WORK/media/dists/r/Release"
printf 'x' >"$WORK/media/pool/main/a/top_1_amd64.deb"
printf 'x' >"$WORK/media/pool/main/b/dep_1_amd64.deb"
cat >"$WORK/Packages" <<'P'
Package: top
Version: 1
Depends: dep (>= 1), have-already | other
Filename: pool/main/a/top_1_amd64.deb
Size: 10

Package: dep
Version: 1
Filename: pool/main/b/dep_1_amd64.deb
Size: 20

Package: have-already
Version: 1
Filename: pool/main/c/have-already_1_amd64.deb
Size: 99
P
printf 'have-already 1\n' >"$WORK/manifest"

# 設置先に無い top と依存 dep だけが載り、設置先に在る have-already は載らない。
python3 -I "$TOOL" --index "$WORK/Packages" --manifest "$WORK/manifest" --seed top \
    --dists-file dists/r/Release --root "$WORK/media" --output "$WORK/out" >/dev/null ||
    fail '一覧の生成に失敗'
printf '%s\n' dists/r/Release pool/main/a/top_1_amd64.deb pool/main/b/dep_1_amd64.deb >"$WORK/expected"
cmp -s "$WORK/out" "$WORK/expected" || fail '一覧が期待と違う'
ok '設置先に無いものと依存の閉包だけを載せる'

# 媒体に無いファイルがあれば失敗する。
rm "$WORK/media/pool/main/b/dep_1_amd64.deb"
if python3 -I "$TOOL" --index "$WORK/Packages" --manifest "$WORK/manifest" --seed top \
    --dists-file dists/r/Release --root "$WORK/media" --output "$WORK/out2" >/dev/null 2>&1; then
    fail '媒体に無いファイルで止まらない'
fi
ok '媒体に無いファイルは失敗する'

# 解決できない依存は失敗する。
if python3 -I "$TOOL" --index "$WORK/Packages" --manifest "$WORK/manifest" --seed nosuch \
    --output "$WORK/out3" >/dev/null 2>&1; then
    fail '解決できない依存で止まらない'
fi
ok '解決できない依存は失敗する'
printf 'ALL OK\n'
