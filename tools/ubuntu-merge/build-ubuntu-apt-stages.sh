#!/bin/sh
# Ubuntu の設置用 APT 設定層と live 専用 kernel 設定層を作る。
# ROOT は組み立て木、WORK は未使用の作業ディレクトリ。
set -eu
ROOT=${1:?assembly root}
WORK=${2:?new work directory}
export LC_ALL=C
SOURCE=$ROOT/casper/common.server.squashfs
MINIMAL=$ROOT/casper/common.dl.snap.ubuntu.apt.squashfs
NORMAL=$ROOT/casper/common.dl.snap.ubuntu.std.apt.squashfs
KERNEL=$ROOT/casper/common.dl.snap.ubuntu.std.live.kernel.squashfs
test -f "$SOURCE"
test ! -e "$MINIMAL"
test ! -e "$NORMAL"
test ! -e "$KERNEL"
mkdir "$WORK"
unsquashfs -no-xattrs -no-wildcards -no-progress -processors 2 \
    -d "$WORK/stage" "$SOURCE" etc/apt/sources.list.d/cdrom.sources
test -f "$WORK/stage/etc/apt/sources.list.d/cdrom.sources"
test ! -L "$WORK/stage/etc/apt/sources.list.d/cdrom.sources"
chmod 755 "$WORK/stage" "$WORK/stage/etc" "$WORK/stage/etc/apt" \
    "$WORK/stage/etc/apt/sources.list.d"
chmod 644 "$WORK/stage/etc/apt/sources.list.d/cdrom.sources"
mksquashfs "$WORK/stage" "$MINIMAL" -comp xz -b 131072 \
    -force-uid 0 -force-gid 0 -noappend -no-progress -processors 2 \
    -all-time 0 -mkfs-time 0 -no-xattrs
# 内容が同じ二つの leaf は同じバイトを使う。
cp "$MINIMAL" "$NORMAL"
# subiquity は live 側のこの設定をカタログの kernel.default より優先する。
mkdir -p "$WORK/kernel/etc/subiquity"
printf '%s\n' 'linux-generic-hwe-24.04' > "$WORK/kernel/etc/subiquity/kernel-meta-package"
chmod 755 "$WORK/kernel" "$WORK/kernel/etc" "$WORK/kernel/etc/subiquity"
chmod 644 "$WORK/kernel/etc/subiquity/kernel-meta-package"
mksquashfs "$WORK/kernel" "$KERNEL" -comp xz -b 131072 \
    -force-uid 0 -force-gid 0 -noappend -no-progress -processors 2 \
    -all-time 0 -mkfs-time 0 -no-xattrs
