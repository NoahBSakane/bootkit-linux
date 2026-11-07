#!/bin/sh
# bootkit-ramsel の静的試験と起動スクリプトの単体試験。通信不要。
# QEMU の実起動は含まない (重い検証は ventoy/ramsel/verify-qemu.py で行う)。
set -eu
HERE=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
RAMSEL=$HERE/ventoy/ramsel
WORK=$(mktemp -d "$HERE/tests/test-ramsel.XXXXXX")
# remount スタブが落とした権限を戻してから、一時物を片付ける。
trap 'chmod -R u+w "$WORK"; rm -rf "$WORK"' 0
trap 'exit 1' HUP INT TERM

fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
ok() { printf 'ok: %s\n' "$*"; }
contains() { grep -Fqx -- "$2" "$1" || fail "$1: 次の行が無い: $2"; }

# 1. 構文と ORDER の固定。
sh -n "$RAMSEL/30bootkit-ramsel"
sh -n "$RAMSEL/make-injection.sh"
sh -n "$RAMSEL/make-trial-iso.sh"
if command -v shellcheck >/dev/null 2>&1; then
    shellcheck -s sh "$RAMSEL/30bootkit-ramsel" || fail 'shellcheck'
    shellcheck -s sh "$RAMSEL/make-injection.sh" || fail 'shellcheck'
    shellcheck -s sh "$RAMSEL/make-trial-iso.sh" || fail 'shellcheck'
fi
python3 -I - "$WORK" "$RAMSEL/rebuild-initrd.py" "$RAMSEL/verify-qemu.py" <<'PY'
from pathlib import Path
import py_compile
import sys
for path in sys.argv[2:]:
    py_compile.compile(path, cfile=str(Path(sys.argv[1]) / (Path(path).name + 'c')),
                       doraise=True)
PY
python3 -I -B "$RAMSEL/verify-qemu.py" --help >/dev/null || fail '--help'
ok '構文'

# 置換 ORDER は標準の 4 行を含み、env/failed の接続を持つ。
# shellcheck disable=SC2016
for line in \
    '/scripts/casper-premount/10driver_updates "$@"' \
    '[ -e /conf/param.conf ] && . /conf/param.conf' \
    '/scripts/casper-premount/20iso_scan "$@"' \
    '/scripts/casper-premount/30bootkit-ramsel "$@"' \
    'if [ -f /run/bootkit-ramsel/env ]; then . /run/bootkit-ramsel/env; fi' \
    'if [ -f /run/bootkit-ramsel/failed ]; then panic "bootkit-ramsel: $(cat /run/bootkit-ramsel/failed)"; fi'; do
    contains "$RAMSEL/ORDER" "$line"
done
ok 'ORDER'

# 画面に出る行 (コメント以外) は VGA が扱える ASCII に限る。
python3 -I - "$RAMSEL/30bootkit-ramsel" "$RAMSEL/ORDER" <<'PY'
from pathlib import Path
import sys
for path in sys.argv[1:]:
    shown = b'\n'.join(
        line for line in Path(path).read_bytes().splitlines()
        if not line.lstrip().startswith(b'#'))
    if not shown.isascii():
        raise SystemExit('non-ASCII on-screen text: ' + path)
print('ok: on-screen ASCII')
PY

# 置換 ORDER に含まれる標準 4 行は rebuild-initrd.py の固定値と一致する (ずれ検出)。
python3 -I -B - "$RAMSEL/ORDER" "$RAMSEL/rebuild-initrd.py" <<'PY'
import importlib.util
import sys
order = open(sys.argv[1], 'rb').read()
spec = importlib.util.spec_from_file_location('rebuild_initrd', sys.argv[2])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert module.STOCK_ORDER in order, 'ORDER に標準 4 行が無い'
print('ok: ORDER の固定')
PY

# 2. 起動スクリプトの単体試験。mount/umount だけを stub にする。
STUBS=$WORK/stubs
mkdir -p "$STUBS"
cat >"$STUBS/mount" <<'STUB'
#!/bin/sh
set -eu
# 最後の引数をマウント先とみなす。媒体と空の tmpfs は別に扱う。
printf '%s\n' "$*" >>"$MOUNT_LOG"
dest=""
for arg in "$@"; do dest=$arg; done
if [ "$1" = -o ] && [ "$2" = remount,ro ]; then
    # ro 化は追加ファイル・メタデータの複写後、env の公開前であること。
    for file in casper/test.base.squashfs casper/test.base.plus.squashfs \
        casper/test.base.manifest casper/vmlinuz casper/test.base.apt.squashfs \
        casper/install-sources.yaml .disk/info dists/resolute/Release \
        pool/main/e/efibootmgr/efibootmgr_1_amd64.deb; do
        cmp -s "$FIXTURE_MEDIA/$file" "$dest/$file" || exit 1
    done
    [ ! -e "$BOOTKIT_RAMSEL_RUN/env" ] || exit 1
    printf 'copies-verified %s\n' "$dest" >>"$MOUNT_LOG"
    [ "$FIXTURE_REMOUNT_FAIL" = 0 ] || exit 1
    # 実際の mount は使わず、非特権ユーザーの書き込みを権限で拒否する。
    chmod -R a-w "$dest"
elif [ "$1" = -t ] && [ "$2" = tmpfs ]; then
    [ "$dest" = "$BOOTKIT_RAMSEL_TARGET" ] || exit 1
    mkdir -p "$dest"
    [ -z "$(ls -A "$dest")" ] || exit 1
elif [ "$1" = -o ] && [ "$2" = ro ]; then
    [ "$dest" = "$BOOTKIT_RAMSEL_RUN/media" ] || exit 1
    mkdir -p "$dest"
    cp -a "$FIXTURE_MEDIA/." "$dest/"
else
    exit 1
fi
exit 0
STUB
cat >"$STUBS/umount" <<'STUB'
#!/bin/sh
printf '%s\n' "$*" >>"$MOUNT_LOG"
printf '%s\n' "$*" >>"$UMOUNT_LOG"
exit 0
STUB
chmod +x "$STUBS/mount" "$STUBS/umount"

MEDIA=$WORK/media
mkdir -p "$MEDIA/casper/bootkit-chains" "$MEDIA/.disk"
printf 'x%.0s' $(seq 1 2048) >"$MEDIA/casper/test.base.squashfs"
printf 'y%.0s' $(seq 1 1024) >"$MEDIA/casper/test.base.plus.squashfs"
printf 'meta' >"$MEDIA/casper/test.base.manifest"
printf 'info' >"$MEDIA/.disk/info"
printf 'kernel' >"$MEDIA/casper/vmlinuz"
printf 'sources' >"$MEDIA/casper/install-sources.yaml"
printf 'not selected' >"$MEDIA/casper/unselected.squashfs"
cat >"$MEDIA/casper/bootkit-chains/test.list" <<'LIST'
test.base.squashfs
test.base.plus.squashfs
LIST
mkdir -p "$MEDIA/dists/resolute" "$MEDIA/pool/main/e/efibootmgr"
printf 'Release' >"$MEDIA/dists/resolute/Release"
printf 'deb' >"$MEDIA/pool/main/e/efibootmgr/efibootmgr_1_amd64.deb"
printf 'apt' >"$MEDIA/casper/test.base.apt.squashfs"
cat >"$MEDIA/casper/bootkit-chains/test.extra" <<'LIST'
# apt が元の媒体なしで引くファイル
dists/resolute/Release
pool/main/e/efibootmgr/efibootmgr_1_amd64.deb
casper/test.base.apt.squashfs
casper/vmlinuz
LIST

env_for() {
    # $1: cmdline、$2: meminfo の MemAvailable 行
    printf '%s' "$1" >"$WORK/cmdline"
    printf '%s\n' "$2" 'MemFree:         1000 kB' >"$WORK/meminfo"
}

run_script() {
    # $1: 試験名、$2: remount だけを失敗させる場合は 1。
    RUN=$WORK/run-$1
    TARGET=$WORK/target-$1
    rm -rf "$RUN" "$TARGET"
    mkdir -p "$RUN" "$TARGET"
    export BOOTKIT_RAMSEL_CMDLINE="$WORK/cmdline" BOOTKIT_RAMSEL_MEMINFO="$WORK/meminfo"
    export BOOTKIT_RAMSEL_RUN="$RUN" BOOTKIT_RAMSEL_TARGET="$TARGET"
    export BOOTKIT_RAMSEL_CONFIG="$WORK/casper.conf"
    export BOOTKIT_RAMSEL_SCAN_WAIT=1 FIXTURE_MEDIA="$MEDIA" MOUNT_LOG="$WORK/mount-$1.log"
    export UMOUNT_LOG="$WORK/umount-$1.log" FIXTURE_REMOUNT_FAIL="${2:-0}"
    : >"$WORK/dev-fake"
    export BOOTKIT_RAMSEL_DEVICES="$WORK/dev-fake"
    export PATH="$STUBS:/usr/bin:/bin"
    : >"$WORK/mount-$1.log"
    : >"$WORK/umount-$1.log"
    if sh "$RAMSEL/30bootkit-ramsel" >"$WORK/stdout-$1.log" 2>&1; then
        printf '0'
    else
        status=$?
        printf '%s' "$status"
    fi
}

# 成功: toram + bootkit.os。
env_for 'BOOT_IMAGE=x toram bootkit.os=test --- quiet' 'MemAvailable:    8000000 kB'
[ "$(run_script good)" = 0 ] || fail '成功するはずが失敗'
[ ! -e "$WORK/run-good/failed" ] || fail 'failed が残った'
[ -f "$WORK/target-good/casper/test.base.squashfs" ] || fail '層が写っていない'
[ -f "$WORK/target-good/casper/test.base.plus.squashfs" ] || fail '層が写っていない (2)'
[ -f "$WORK/target-good/casper/test.base.manifest" ] || fail 'manifest が写っていない'
[ -f "$WORK/target-good/.disk/info" ] || fail '.disk が写っていない'
cmp -s "$MEDIA/casper/test.base.squashfs" "$WORK/target-good/casper/test.base.squashfs" ||
    fail '写し誤り'
contains "$WORK/run-good/env" 'LIVEMEDIA='"$WORK/target-good"
contains "$WORK/run-good/env" 'unset TORAM'
[ -f "$WORK/target-good/dists/resolute/Release" ] || fail 'extra (dists) が写っていない'
cmp -s "$MEDIA/pool/main/e/efibootmgr/efibootmgr_1_amd64.deb" \
    "$WORK/target-good/pool/main/e/efibootmgr/efibootmgr_1_amd64.deb" || fail 'extra (pool) の写し誤り'
cmp -s "$MEDIA/casper/test.base.apt.squashfs" "$WORK/target-good/casper/test.base.apt.squashfs" ||
    fail 'extra (casper の層) が写っていない'
for file in casper/vmlinuz casper/install-sources.yaml .disk/info; do
    cmp -s "$MEDIA/$file" "$WORK/target-good/$file" || fail "$file の写し誤り"
done
[ ! -e "$WORK/target-good/casper/unselected.squashfs" ] || fail '非選択の層まで写った'
[ ! -e "$WORK/target-good/casper/bootkit-chains" ] || fail '媒体全体が写った'
ok '成功 (選択複写と env と extra)'

# Lubuntu は全複写後に ro 化し、その後で媒体を外す。
cp "$MEDIA/casper/bootkit-chains/test.list" "$MEDIA/casper/bootkit-chains/lubuntu.list"
cp "$MEDIA/casper/bootkit-chains/test.extra" "$MEDIA/casper/bootkit-chains/lubuntu.extra"
env_for 'toram bootkit.os=lubuntu' 'MemAvailable:    8000000 kB'
[ "$(run_script lubuntu)" = 0 ] || fail 'Lubuntu の複写と ro 化に失敗'
cmp -s "$MEDIA/casper/vmlinuz" "$WORK/target-lubuntu/casper/vmlinuz" || fail 'vmlinuz の写し誤り'
contains "$WORK/mount-lubuntu.log" "-o remount,ro $WORK/target-lubuntu"
contains "$WORK/run-lubuntu/env" 'LIVEMEDIA='"$WORK/target-lubuntu"
python3 -I - "$WORK/mount-lubuntu.log" "$WORK/umount-lubuntu.log" \
    "$WORK/target-lubuntu" "$WORK/run-lubuntu/media" <<'PY'
from pathlib import Path
import sys
lines = Path(sys.argv[1]).read_text().splitlines()
remount = '-o remount,ro ' + sys.argv[3]
assert lines.count(remount) == 1
assert lines.index(remount) < lines.index('copies-verified ' + sys.argv[3]) < lines.index(sys.argv[4])
assert Path(sys.argv[2]).read_text().splitlines() == [sys.argv[4]]
PY
if (printf 'probe' >"$WORK/target-lubuntu/write-probe") 2>/dev/null; then
    fail 'ro 化後の RAM 媒体にファイルを作れた'
fi
if (printf 'probe' >>"$WORK/target-lubuntu/casper/vmlinuz") 2>/dev/null; then
    fail 'ro 化後の RAM 媒体のファイルに書き込めた'
fi
cmp -s "$MEDIA/casper/vmlinuz" "$WORK/target-lubuntu/casper/vmlinuz" || fail 'ro 化後に vmlinuz が変わった'
ok 'Lubuntu の toram は vmlinuz を複写し、全複写後の RAM 媒体を ro にする'

# remount だけの失敗: env を公開せず、両マウント先を各 1 回解除する。
env_for 'toram bootkit.os=lubuntu' 'MemAvailable:    8000000 kB'
[ "$(run_script remount-error 1)" = 1 ] || fail 'remount 失敗の終了コードが 1 でない'
contains "$WORK/run-remount-error/failed" \
    'cannot remount RAM media read-only; will not continue from media'
[ ! -e "$WORK/run-remount-error/env" ] || fail 'remount 失敗で env を書いた'
contains "$WORK/mount-remount-error.log" "-o remount,ro $WORK/target-remount-error"
contains "$WORK/mount-remount-error.log" "copies-verified $WORK/target-remount-error"
printf '%s\n' "$WORK/target-remount-error" "$WORK/run-remount-error/media" >"$WORK/expected-umount"
cmp -s "$WORK/expected-umount" "$WORK/umount-remount-error.log" || fail 'remount 失敗の解除先・回数が違う'
ok 'remount 失敗は終了コード 1・failed・env 不在・両媒体の解除を満たす'

# 合格済みの Server・Ubuntu は既存どおり rw の tmpfs を渡す。
for osname in server ubuntu; do
    cp "$MEDIA/casper/bootkit-chains/test.list" "$MEDIA/casper/bootkit-chains/$osname.list"
    cp "$MEDIA/casper/bootkit-chains/test.extra" "$MEDIA/casper/bootkit-chains/$osname.extra"
    env_for "toram bootkit.os=$osname" 'MemAvailable:    8000000 kB'
    [ "$(run_script "$osname")" = 0 ] || fail "$osname の複写に失敗"
    if grep -Fq 'remount,ro' "$WORK/mount-$osname.log"; then fail "$osname を ro 化した"; fi
    contains "$WORK/run-$osname/env" 'LIVEMEDIA='"$WORK/target-$osname"
    printf 'probe' >"$WORK/target-$osname/write-probe" || fail "$osname の RAM 媒体に書き込めない"
    printf 'probe' >>"$WORK/target-$osname/casper/vmlinuz" || fail "$osname の RAM 媒体のファイルに書き込めない"
done
ok 'Server・Ubuntu の toram は ro 化しない'

# toram が無い: 何もしない。
env_for 'BOOT_IMAGE=x bootkit.os=lubuntu --- quiet' 'MemAvailable:    8000000 kB'
[ "$(run_script no-toram)" = 0 ] || fail 'no-toram で失敗'
[ ! -e "$WORK/run-no-toram/env" ] || fail 'no-toram で env を書いた'
[ ! -s "$WORK/mount-no-toram.log" ] || fail 'no-toram で mount した'
ok 'toram 無しは何もしない'

# bootkit.os が無い: 何もしない。
env_for 'BOOT_IMAGE=x toram --- quiet' 'MemAvailable:    8000000 kB'
[ "$(run_script no-os)" = 0 ] || fail 'no-os で失敗'
[ ! -e "$WORK/run-no-os/env" ] || fail 'no-os で env を書いた'
[ ! -s "$WORK/mount-no-os.log" ] || fail 'no-os で mount した'
ok 'bootkit.os 無しは何もしない'

# RAM 不足: 黙って続かず failed。
env_for 'BOOT_IMAGE=x toram bootkit.os=test --- quiet' 'MemAvailable:      10000 kB'
[ "$(run_script poor)" = 1 ] || fail 'RAM 不足で止まらない'
grep -Fq 'not enough RAM' "$WORK/run-poor/failed" || fail '理由が違う'
[ ! -e "$WORK/run-poor/env" ] || fail 'RAM 不足で env を書いた'
ok 'RAM 不足は失敗する'

# 不正な os 値: 失敗する。
env_for 'BOOT_IMAGE=x toram bootkit.os=../x --- quiet' 'MemAvailable:    8000000 kB'
[ "$(run_script bados)" = 1 ] || fail '不正な os で止まらない'
ok '不正な os 値は失敗する'

# 連鎖に無い層: 失敗する。
printf 'nope.squashfs\n' >"$MEDIA/casper/bootkit-chains/broken.list"
env_for 'BOOT_IMAGE=x toram bootkit.os=broken --- quiet' 'MemAvailable:    8000000 kB'
[ "$(run_script broken)" = 1 ] || fail '欠落層で止まらない'
grep -Fq 'layer missing from media' "$WORK/run-broken/failed" || fail '理由が違う'
ok '欠落層は失敗する'

# extra に無いファイル・不正な相対パスは失敗する。
printf 'test.base.squashfs\n' >"$MEDIA/casper/bootkit-chains/xmiss.list"
printf 'pool/main/nope.deb\n' >"$MEDIA/casper/bootkit-chains/xmiss.extra"
env_for 'BOOT_IMAGE=x toram bootkit.os=xmiss --- quiet' 'MemAvailable:    8000000 kB'
[ "$(run_script xmiss)" = 1 ] || fail 'extra の欠落で止まらない'
grep -Fq 'extra file missing' "$WORK/run-xmiss/failed" || fail 'extra 欠落の理由が違う'
for bad in '../etc/passwd' '/etc/passwd' 'pool/../x' 'casper/x' 'casper/initrd' 'casper/vmlinuz.old' 'casper/a/b.squashfs' 'casper/../x.squashfs' 'pool//x' 'pool/a b'; do
    printf 'test.base.squashfs\n' >"$MEDIA/casper/bootkit-chains/xbad.list"
    printf '%s\n' "$bad" >"$MEDIA/casper/bootkit-chains/xbad.extra"
    env_for 'BOOT_IMAGE=x toram bootkit.os=xbad --- quiet' 'MemAvailable:    8000000 kB'
    [ "$(run_script xbad)" = 1 ] || fail "不正な extra で止まらない: $bad"
    grep -Fq 'invalid extra path' "$WORK/run-xbad/failed" || fail "不正な extra の理由が違う: $bad"
done
ok 'extra の欠落・不正パスは失敗する'

# 想定外の I/O 失敗でも failed が残り、親が panic できる。
cat >"$STUBS/stat" <<'STUB'
#!/bin/sh
exit 1
STUB
cat >"$STUBS/wc" <<'STUB'
#!/bin/sh
exit 1
STUB
chmod +x "$STUBS/stat" "$STUBS/wc"
env_for 'toram bootkit.os=test' 'MemAvailable:    8000000 kB'
[ "$(run_script io-error)" = 1 ] || fail 'I/O 異常終了で成功した'
grep -Fq 'copy-to-RAM aborted' "$WORK/run-io-error/failed" || fail '異常終了の理由が無い'
ok '想定外の I/O 異常終了も failed'

printf 'ALL OK\n'
