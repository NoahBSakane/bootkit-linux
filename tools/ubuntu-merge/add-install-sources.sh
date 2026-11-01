#!/bin/sh
# 統合 ISO の複製へ /casper/install-sources.yaml を追記する (方式a)。
# 層・pool の再生成や ISO 全体の作り直しはしない。既存 ISO への差分追記だけ。
# 使い方: sh tools/ubuntu-merge/add-install-sources.sh <iso> [catalog]
#   <iso>: 変更する複製 ISO (入力 ISO 自体には書かないこと)
#   [catalog]: 追記するカタログ原文 (既定は tools/offline-install/install-sources.yaml)
set -eu
HERE=$(CDPATH='' cd -- "$(dirname "$0")/../.." && pwd)
ISO=${1:?usage: add-install-sources.sh '<iso> [catalog]'}
CATALOG=${2:-$HERE/tools/offline-install/install-sources.yaml}
[ -f "$ISO" ] || { echo "no iso: $ISO" >&2; exit 1; }
[ -f "$CATALOG" ] || { echo "no catalog: $CATALOG" >&2; exit 1; }
command -v xorriso >/dev/null 2>&1 || { echo "no xorriso" >&2; exit 1; }
xorriso -dev "$ISO" -boot_image any replay \
  -map "$CATALOG" /casper/install-sources.yaml
python3 -I "$HERE/tools/ubuntu-merge/fix-pvd.py" "$ISO"
xorriso -indev "$ISO" -osirrox on \
  -extract /casper/install-sources.yaml "$HERE/build/work/isoinfo/install-sources-roundtrip.yaml"
cmp "$CATALOG" "$HERE/build/work/isoinfo/install-sources-roundtrip.yaml"
xorriso -indev "$ISO" -lsl /casper -- 2>&1 | grep -E "install-sources"
