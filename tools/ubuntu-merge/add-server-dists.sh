#!/bin/sh
# Server のオフライン自動インストール用に、公式 Server ISO の /dists を
# 統合 ISO の複製へ追記する。層・pool の再生成や ISO 全体の作り直しはしない。
# 背景: subiquity の configure_apt は標的内で必ず `apt-get update` を走らせる。
# live の cdrom.sources (26.04 以降) は file:///cdrom の pool を指すため、
# /cdrom/dists が無いと update が終了 100 で失敗する。統合 ISO の組立では
# /pool だけを union して /dists を載せていなかったため、Server 用の dists
# (署名つき原本。小さい) をそのまま追記する。署名は自作できないため、
# 公式 ISO からの抜粋が必須である。desktop / Lubuntu 用の dists は Release が
# 衝突するため未対応 (文書参照)。
# 使い方: sh tools/ubuntu-merge/add-server-dists.sh <clone-iso> <official-server-iso>
set -eu
HERE=$(CDPATH='' cd -- "$(dirname "$0")/../.." && pwd)
CLONE=${1:?usage: add-server-dists.sh '<clone-iso> <official-server-iso>'}
SRC=${2:?usage: add-server-dists.sh '<clone-iso> <official-server-iso>'}
[ -f "$CLONE" ] || { echo "no clone iso: $CLONE" >&2; exit 1; }
[ -f "$SRC" ] || { echo "no official iso: $SRC" >&2; exit 1; }
command -v xorriso >/dev/null 2>&1 || { echo "no xorriso" >&2; exit 1; }
STAGE=$HERE/build/work/isoinfo/dists-stage
RT=$HERE/build/work/isoinfo/dists-roundtrip
mkdir -p "$STAGE" "$RT"
# osirrox の抜粋は読取り専用で残るため、先に書込みを足す。
[ -e "$STAGE/dists" ] && chmod -R u+w "$STAGE/dists" || true
[ -e "$RT/dists" ] && chmod -R u+w "$RT/dists" || true
rm -rf "$STAGE/dists" "$RT/dists"
xorriso -indev "$SRC" -osirrox on -extract /dists "$STAGE/dists"
xorriso -dev "$CLONE" -boot_image any replay -map "$STAGE/dists" /dists
python3 -I "$HERE/tools/ubuntu-merge/fix-pvd.py" "$CLONE"
xorriso -indev "$CLONE" -osirrox on -extract /dists "$RT/dists"
diff -r -q "$STAGE/dists/resolute" "$RT/dists/resolute"
xorriso -indev "$CLONE" -lsl /dists/resolute -- 2>&1 | grep -E "Release"
xorriso -indev "$CLONE" -ls / -- 2>&1 | grep -E "dists"
