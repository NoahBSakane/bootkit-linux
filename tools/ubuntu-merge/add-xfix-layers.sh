#!/bin/sh
# 複製 ISO へ xfix 補正層 3 個を追記する。層・pool の再生成や ISO 全体の
# 作り直しはしない。既存 ISO への差分追記だけ。
# 使い方: sh tools/ubuntu-merge/add-xfix-layers.sh <iso> [layerdir]
#   <iso>: 変更する複製 ISO (入力 ISO 自体には書かないこと)
#   [layerdir]: xfix 層のある場所 (既定は build/work/xfix)
# 注意: xorriso の追記は primary PVD の volume size を 2^22 sector 単位で
# 巻き戻すため、追記セッションと fix-pvd.py は対にすること。追記後に
# fix-pvd なしで次の xorriso を載せると ISO 像が読めなくなる
# (SUSP CE エラー)。3 層は 1 回の起動でまとめて写す。
set -eu
HERE=$(CDPATH='' cd -- "$(dirname "$0")/../.." && pwd)
ISO=${1:?usage: add-xfix-layers.sh '<iso> [layerdir]'}
LAYERDIR=${2:-$HERE/build/work/xfix}
[ -f "$ISO" ] || { echo "no iso: $ISO" >&2; exit 1; }
command -v xorriso >/dev/null 2>&1 || { echo "no xorriso" >&2; exit 1; }
for L in common.server.xfix.squashfs common.dl.ubuntu.xfix.squashfs \
    common.dl.lubuntu.xfix.squashfs; do
  [ -f "$LAYERDIR/$L" ] || { echo "no layer: $LAYERDIR/$L" >&2; exit 1; }
done
xorriso -dev "$ISO" -boot_image any replay \
  -map "$LAYERDIR/common.server.xfix.squashfs" \
    /casper/common.server.xfix.squashfs \
  -map "$LAYERDIR/common.dl.ubuntu.xfix.squashfs" \
    /casper/common.dl.ubuntu.xfix.squashfs \
  -map "$LAYERDIR/common.dl.lubuntu.xfix.squashfs" \
    /casper/common.dl.lubuntu.xfix.squashfs
python3 -I "$HERE/tools/ubuntu-merge/fix-pvd.py" "$ISO"
mkdir -p "$HERE/build/work/isoinfo"
for L in common.server.xfix.squashfs common.dl.ubuntu.xfix.squashfs \
    common.dl.lubuntu.xfix.squashfs; do
  xorriso -indev "$ISO" -osirrox on \
    -extract "/casper/$L" "$HERE/build/work/isoinfo/$L.roundtrip"
  cmp "$LAYERDIR/$L" "$HERE/build/work/isoinfo/$L.roundtrip"
  rm -f "$HERE/build/work/isoinfo/$L.roundtrip"
done
xorriso -indev "$ISO" -lsl /casper -- 2>&1 | grep -E "xfix"
