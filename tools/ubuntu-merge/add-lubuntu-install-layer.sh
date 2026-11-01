#!/bin/sh
# Lubuntu の設置用上書き層 (install) を ISO の追記で足す。
# 層・pool の再生成や ISO 全体の作り直しはしない。既存 ISO への差分追記だけ。
# 使い方: sh tools/ubuntu-merge/add-lubuntu-install-layer.sh <入力ISO> <複製ISO>
#   <入力ISO>: 読みだけ (pool の deb の出所。変更しない)
#   <複製ISO>: 変更する作業用の複製
# 追記する物:
#   /casper/common.dl.lubuntu.install.squashfs … 4 展開元の unpackfs.conf +
#     白抜きの蘇生 (dracut 等の実体) + xattr 補正 11 パス +
#     bootloader 用の小さな署名なし repo (/pool・/dists) +
#     contextualprocess@before_bootloader の上書き設定と手順本体
#   /casper/bootkit-chains/lubuntu.list … 新しい leaf を含む 4 行
#   /boot/grub/grub.cfg … BOOTKIT_LUBUNTU_LEAF=新leaf で再生成
#   (Lubuntu の layerfs-path が新しい leaf を指す)
#
# 層の並び (親から子。起動の overlay・toram 複写・unpackfs 展開の順で一致):
#   common.squashfs → common.dl.squashfs → common.dl.lubuntu.squashfs
#   → common.dl.lubuntu.install.squashfs (本層)
# 名前を土台 leaf の子にするのは、casper の setup_overlay が layerfs-path
# の leaf からドットで親を列挙するためである。起動の連鎖・toram 複写・
# unpackfs 展開の順はどれも親から子の 4 層で一致する。
#
# 層の中身と目的:
# - etc/calamares/modules/unpackfs.conf … 起動の overlay と同じ順の 4 展開元
#   (原文 tools/offline-install/lubuntu-unpackfs-install.conf)。
#   先頭だけ無条件で、残りは通常の選択のときだけ展開する
#   (installation_data.unpack_regular は pkgselect が立てる)。
# - 白抜きの蘇生 … live の leaf 層の whiteout (char/block 0,0) で Server 層に
#   実体がある物 (dracut 一式など) を Server 層から抜いて同梱し、
#   leaf の whiteout を上書きして蘇らせる。写しだと標的で実行不能になる
#   (dracut 段が終了 126 で失敗する)。実体がどの層にも無い物は入れない。
# - xattr 補正 11 パス … 統合層の security.capability の値の切れ
#   (inventory.py が空白で割っていた。usr/bin/ping・usr/bin/mtr-packet の
#   公式 20 バイトに対し統合 5 バイト) を公式値で上書きし、unpack の
#   rsync -X で欠落した 2 ファイルの実体を補う。公式値の出所は
#   tools/ubuntu-merge/lubuntu-xfix-official.json。
#   中身・モード・所有者・時刻は統合層の版のまま、正しい xattr だけ公式の
#   可視値で置く。whiteout は使わない。
# - /pool・/dists … bootloader の deb だけの最小 repo
#   (grub-efi-amd64-{signed,bin,unsigned}・grub2-common・shim-signed・
#   efibootmgr の 6 deb + dists/resolute の索引) を層に同梱し、live の
#   overlay 上の /pool・/dists を file:/// の素性 (Trusted: yes) で読む。
#   contextualprocess@before_bootloader が grub-efi-amd64-signed 等を標的へ
#   入れるのに要る。統合 ISO に pool が無いと apt-get update が終了 100 で
#   後の段が全部飛ぶ。deb の出所は入力 ISO の /pool (読むだけ)。
#   依存の閉包は repo 内と統合層の既設で閉じること (不足があれば中断する)。
# - etc/calamares/modules/before_bootloader_context.conf … 手順本体を層内の
#   bootrepo-apt.sh に置き、conf 側は短い sh 呼び出し 1 行だけにする。
#   YAML の素朴な値に :+空白を含めると yaml-cpp が illegal map value で
#   読めず calamares が起動時に初期化失敗するため。
# - etc/calamares/bootrepo-apt.sh … file:/// 素性の更新と bootloader 用 5 指名
#   (grub-efi-amd64-{signed,bin,unsigned}・shim-signed・efibootmgr) の導入。
#   --no-upgrade は残して live の既設を変えない。指名漏れの新規依存は
#   入らないため、既設に無い物は指名に含める (道具が推移閉包を検査する)。
# - dists/resolute/Release … Date は C ロケールで書く (ja ロケールの
#   %a %b は apt が Invalid 'Date' と警告する。Packages の中身は変えない
#   ためハッシュはそのまま有効)。
set -eu
HERE=$(CDPATH='' && cd -- "$(dirname "$0")/../.." && pwd)
IN=${1:?usage: add-lubuntu-install-layer.sh '<input iso>' '<work iso>'}
ISO=${2:?usage: add-lubuntu-install-layer.sh '<input iso>' '<work iso>'}
LEAF=common.dl.lubuntu.install.squashfs
CONF=$HERE/tools/offline-install/lubuntu-unpackfs-install.conf
OFFJSON=$HERE/tools/ubuntu-merge/lubuntu-xfix-official.json
[ -f "$IN" ] || { echo "no input iso: $IN" >&2; exit 1; }
[ -f "$ISO" ] || { echo "no work iso: $ISO" >&2; exit 1; }
[ -f "$CONF" ] || { echo "no conf: $CONF" >&2; exit 1; }
[ -f "$OFFJSON" ] || { echo "no official json: $OFFJSON" >&2; exit 1; }
command -v xorriso >/dev/null 2>&1 || { echo "no xorriso" >&2; exit 1; }
command -v mksquashfs >/dev/null 2>&1 || { echo "no mksquashfs" >&2; exit 1; }
command -v unsquashfs >/dev/null 2>&1 || { echo "no unsquashfs" >&2; exit 1; }
WORK=$HERE/build/work/install-layer
rm -rf "$WORK/stage" "$WORK/out" "$WORK/verify" "$WORK/debs" "$WORK/cmp"
mkdir -p "$WORK/stage/etc/calamares/modules" "$WORK/out" "$WORK/debs"
LOG=$WORK/out/install-build.log
: > "$LOG"
exec >"$LOG" 2>&1
echo "== install layer build for $ISO from $IN"
cp "$CONF" "$WORK/stage/etc/calamares/modules/unpackfs.conf"
chmod 644 "$WORK/stage/etc/calamares/modules/unpackfs.conf"
# 白抜きの蘇生: live の leaf 層の whiteout で Server 層に実体がある物を抜く。
RESCUE_PY=$HERE/tools/ubuntu-merge/lubuntu-whiteout-rescue.py
python3 -I "$RESCUE_PY" "$ISO" > "$WORK/out/rescue.list.nul" 2>"$WORK/out/rescue.log"
tr '\0' '\n' < "$WORK/out/rescue.list.nul" > "$WORK/out/rescue.list.txt"
wc -l "$WORK/out/rescue.list.txt"
SRV_LBA=$(xorriso -indev "$ISO" -find /casper \
    -name 'common.server.squashfs' -exec report_lba -- 2>/dev/null \
    | awk -F'[ ,]+' '/File data lba/ {print $5}')
[ -n "$SRV_LBA" ] || { echo "no server lba" >&2; exit 1; }
SRV_OFF=$((SRV_LBA * 2048))
# shellcheck disable=SC2046
unsquashfs -o "$SRV_OFF" -d "$WORK/stage" -f "$ISO" \
    $(cat "$WORK/out/rescue.list.txt") 2>&1 | tail -2
# 手順本体は層内の shell 記述 (bootrepo-apt.sh) に置く。
# contextualprocess の command の素朴な値は 1 行で書かねばならず、
# 長い apt 行を YAML に直書きすると yaml-cpp の map 値の誤読を招くため、
# conf 側は短い sh 呼び出し 1 行だけにする (5 指名版)。
cat > "$WORK/stage/etc/calamares/bootrepo-apt.sh" <<'SHEOF'
#!/bin/sh
# 層同梱の pool/dists (live の /pool・/dists) を file:/// 素性として使い、
# bootloader 用の署名済み deb を live へ入れる。標的には残さない。
set -eu
D=/tmp/calamares-cdrom-sources
mkdir "$D" "$D/empty.parts"
cat > "$D/cdrom.sources" <<'EOF'
Types: deb
URIs: file:///
Suites: resolute
Components: main
Trusted: yes
EOF
OPTS="-o Dir::Etc::sourcelist=$D/cdrom.sources -o Dir::Etc::sourceparts=$D/empty.parts"
apt-get $OPTS update
apt-get $OPTS install -y --no-upgrade \
    -o Acquire::gpgv::Options::=--ignore-time-conflict \
    grub-efi-amd64-signed grub-efi-amd64-bin grub-efi-amd64-unsigned shim-signed efibootmgr
apt-get $OPTS install -y --no-upgrade \
    -o Acquire::gpgv::Options::=--ignore-time-conflict \
    shim-signed
rm "$D/cdrom.sources"
rmdir "$D/empty.parts" "$D"
SHEOF
chmod 755 "$WORK/stage/etc/calamares/bootrepo-apt.sh"
# 上書きの before_bootloader_context.conf (原文の行構成を保つ)。
# command の値は短い呼び出しだけにし、:+空白を含む長い行を避ける。
cat > "$WORK/stage/etc/calamares/modules/before_bootloader_context.conf" <<'CONFEOF'
firmwareType:
    bios:    "-/bin/true"
    "*":
        -    command: sh /etc/calamares/bootrepo-apt.sh
             timeout: 10800
CONFEOF
# YAML の素朴な値 (command の中身) に : を含めないこと
# (yaml-cpp が illegal map value で読めなくなる)。
if awk '/command: /{sub(/.*command: /, ""); if ($0 ~ /: /) print}' \
    "$WORK/stage/etc/calamares/modules/before_bootloader_context.conf" | grep -q .; then
    echo "plain scalar with colon-space found" >&2
    exit 1
fi
# bootloader の deb と efibootmgr (grub-install の実行時に要る) を抜く。
DEBS="pool/main/g/grub2-signed/grub-efi-amd64-signed_1.215+2.14-2ubuntu1_amd64.deb
pool/main/g/grub2-unsigned/grub-efi-amd64-bin_2.14-2ubuntu1_amd64.deb
pool/main/g/grub2-unsigned/grub-efi-amd64-unsigned_2.14-2ubuntu1_amd64.deb
pool/main/g/grub2/grub2-common_2.14-2ubuntu2.1_amd64.deb
pool/main/s/shim-signed/shim-signed_1.59+15.8-0ubuntu2_amd64.deb
pool/main/e/efibootmgr/efibootmgr_18-4ubuntu1_amd64.deb"
for d in $DEBS; do
    dest=$WORK/debs/$(basename "$d")
    xorriso -indev "$IN" -osirrox on -extract "/$d" "$dest" 2>&1 | tail -1
    mkdir -p "$WORK/stage/$(dirname "$d")"
    cp "$dest" "$WORK/stage/$d"
done
# Packages 索引と Release を作る。依存の閉包を検査する。
# INSTALLED は live (標的と同一) で dpkg -s の Status を実測した物に
# grub2-common を足した物 (shim-signed が grub2-common を要し、
# live に 2.14-2ubuntu2.1 が入っている)。
python3 -I - "$WORK" <<'PYEOF'
import gzip
import hashlib
import os
import re
import subprocess
import sys
work = sys.argv[1]
INSTALLED = {
    "debconf", "grub-common", "grub-pc", "grub2-common", "libc6",
    "libdevmapper1.02.1", "libefiboot1t64", "libefivar1t64",
    "libfreetype6", "libfuse3-4", "liblzma5", "gettext-base", "python3",
    "python3-apt", "mokutil", "sbsigntool", "openssl", "libpopt0",
}
pool = []
for root, _, files in os.walk(os.path.join(work, "stage", "pool")):
    for name in sorted(files):
        if name.endswith(".deb"):
            pool.append(os.path.join(root, name))
assert len(pool) == 6, [os.path.basename(p) for p in pool]


def control(deb):
    members = subprocess.check_output(["ar", "t", deb], text=True).split()
    ctl = [m for m in members if m.startswith("control.tar")][0]
    raw = subprocess.check_output(["ar", "p", deb, ctl])
    if ctl.endswith(".zst"):
        raw = subprocess.check_output(["unzstd", "-c"], input=raw)
    else:
        import lzma
        raw = lzma.decompress(raw)
    import tarfile
    import io
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        text = tar.extractfile("./control").read().decode()
    fields = {}
    for line in text.splitlines():
        if re.match(r"^[A-Za-z-]+:", line):
            key, _, val = line.partition(":")
            fields[key.strip()] = val.strip()
    return fields


def dep_ok(dep, provided):
    # "a (>= 1) | b" をどれか満たせばよい。版の比較は = 指定だけ見る。
    for alt in dep.split("|"):
        alt = alt.strip()
        match = re.match(r"([A-Za-z0-9.+\-:]+)(?:\s*\(\s*(=|>=|<<|>>|<=)\s*([^)]+)\))?",
                         alt)
        if not match:
            raise RuntimeError("cannot parse dep: %r" % alt)
        name = match.group(1)
        if name in provided:
            return True
    return False


entries = []
provided = set(INSTALLED)
metas = {}
for deb in pool:
    meta = control(deb)
    metas[meta["Package"]] = meta["Version"]
for deb in pool:
    meta = control(deb)
    provided.add(meta["Package"])
for deb in pool:
    meta = control(deb)
    for dep in meta.get("Depends", "").split(","):
        dep = dep.strip()
        if not dep:
            continue
        assert dep_ok(dep, provided), (meta["Package"], dep)
    data = open(deb, "rb").read()
    rel = os.path.relpath(deb, os.path.join(work, "stage"))
    entries.append((meta["Package"], "\n".join([
        "Package: " + meta["Package"],
        "Version: " + meta["Version"],
        "Architecture: " + meta.get("Architecture", "amd64"),
        "Filename: " + rel,
        "Size: %d" % len(data),
        "MD5sum: " + hashlib.md5(data).hexdigest(),
        "SHA1: " + hashlib.sha1(data).hexdigest(),
        "SHA256: " + hashlib.sha256(data).hexdigest(),
        "Description: bootkit minimal bootloader pool",
    ])))
entries.sort()
print("pool: %d debs, deps closed" % len(entries))
for name, _ in entries:
    print("  %s %s" % (name, metas[name]))
amd64 = os.path.join(work, "stage", "dists", "resolute", "main",
                     "binary-amd64")
i386 = os.path.join(work, "stage", "dists", "resolute", "main",
                    "binary-i386")
os.makedirs(amd64, exist_ok=True)
os.makedirs(i386, exist_ok=True)
body = "".join(text + "\n\n" for _, text in entries).encode()
open(os.path.join(amd64, "Packages"), "wb").write(body)
open(os.path.join(amd64, "Packages.gz"), "wb").write(gzip.compress(body))
open(os.path.join(i386, "Packages"), "wb").write(b"")
open(os.path.join(i386, "Packages.gz"), "wb").write(gzip.compress(b""))
records = []
for path in ("main/binary-amd64/Packages", "main/binary-amd64/Packages.gz",
             "main/binary-i386/Packages", "main/binary-i386/Packages.gz"):
    full = os.path.join(work, "stage", "dists", "resolute", path)
    data = open(full, "rb").read()
    records.append((path, len(data), hashlib.md5(data).hexdigest(),
                    hashlib.sha1(data).hexdigest(),
                    hashlib.sha256(data).hexdigest()))
lines = ["Origin: bootkit", "Label: bootkit-bootloader", "Suite: resolute",
         "Codename: resolute",
         "Date: " + subprocess.check_output(
             ["date", "-u", "+%a, %d %b %Y %H:%M:%S UTC"], text=True,
             env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                  "LC_ALL": "C"}).strip(),
         "Architectures: amd64 i386", "Components: main",
         "Description: minimal bootloader repo for offline install"]
for digest, label in ((2, "MD5Sum"), (3, "SHA1"), (4, "SHA256")):
    lines.append(label + ":")
    for path, size, md5, sha1, sha256 in records:
        lines.append(" %s %8d %s" % ([md5, sha1, sha256][[2, 3, 4].index(
            digest)], size, path))
open(os.path.join(work, "stage", "dists", "resolute", "Release"), "w",
     encoding="utf-8").write("\n".join(lines) + "\n")
print("dists written")
PYEOF
# xattr 補正 11 パス: 通常ファイルの中身を統合層から抜き、公式値の xattr を
# 疑似定義で付ける (中身・モード・所有者・時刻は統合層の版のまま)。
python3 -I - "$HERE" "$ISO" "$WORK" "$OFFJSON" <<'PYEOF'
import json
import os
import subprocess
import sys
here, iso, work, offjson = sys.argv[1:5]
sys.path.insert(0, os.path.join(here, "tools", "ubuntu-merge"))
from inventory import escape_pf, pf_metadata  # noqa: E402


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("failed: %s\n%s" % (" ".join(cmd), p.stderr[-2000:]))
    return p


def lba(name):
    p = run(["xorriso", "-indev", iso, "-find", "/casper",
             "-name", name, "-exec", "report_lba", "--"])
    for line in p.stderr.splitlines() + p.stdout.splitlines():
        if "File data lba" in line:
            return int(line.replace(",", " ").split()[4])
    raise RuntimeError("no lba for " + name)


vend = json.load(open(offjson, encoding="utf-8"))["paths"]
paths = sorted(vend)
print("targets: %d" % len(paths))
# 必要な統合層を抜き出す (中身とメタデータの出所)。
need = sorted({vend[p]["int_layer"] for p in paths})
int_sqfs = {}
for layer in need:
    tmp = os.path.join(work, "int-%s" % layer)
    if os.path.exists(tmp):
        os.remove(tmp)
    print("extract %s" % layer)
    run(["xorriso", "-indev", iso, "-osirrox", "on",
         "-extract", "/casper/" + layer, tmp])
    int_sqfs[layer] = tmp
int_meta = {}
for layer in need:
    rec, _ = pf_metadata(int_sqfs[layer])
    int_meta[layer] = rec
# 通常ファイルの中身を取り出す (xattr なしでよい)。
files = [p for p in paths
         if int_meta[vend[p]["int_layer"]].get(p, {}).get("t") == "f"]
by_layer = {}
for p in files:
    by_layer.setdefault(vend[p]["int_layer"], []).append(p)
for layer, ps in by_layer.items():
    lst = os.path.join(work, "extract.list")
    with open(lst, "w", encoding="utf-8") as f:
        for p in ps:
            f.write(p + "\n")
    run(["unsquashfs", "-no-xattrs", "-no-wildcards", "-f",
         "-d", os.path.join(work, "stage"), "-extract-file", lst,
         int_sqfs[layer]])
# 通常ファイル以外の種別は dirs のはず (whiteout が混ざらないこと)。
for p in paths:
    t = int_meta[vend[p]["int_layer"]].get(p, {}).get("t")
    if t == "d":
        os.makedirs(os.path.join(work, "stage", p), exist_ok=True)
    elif t != "f":
        raise RuntimeError("unsupported type %r for %r" % (t, p))
print("files=%d dirs=%d" % (len(files),
      len([p for p in paths if p not in files])))
# 疑似定義を作る (M 行は raw パス順で親が子より先)。
# unpackfs.conf・蘇生・pool/dists・手順本体は stage の実ファイルのまま
# (所有者は -force-uid/-force-gid で付ける)。疑似定義は補正 11 パスだけ。
pseudo_m = []
for p in paths:
    rec = int_meta[vend[p]["int_layer"]][p]
    pseudo_m.append((p, "%s M %d %o %d %d"
                       % (escape_pf(p, True), rec["mtime"],
                          rec["mode"], rec["uid"], rec["gid"])))
pseudo_x = []
for p in paths:
    for xn, xv in sorted(vend[p]["x"].items()):
        pseudo_x.append("%s x %s=%s" % (escape_pf(p, True), xn, xv))
pseudo_path = os.path.join(work, "install.pseudo")
with open(pseudo_path, "w", encoding="utf-8",
          errors="surrogateescape") as f:
    for _, ln in sorted(pseudo_m):
        f.write(ln + "\n")
    for ln in pseudo_x:
        f.write(ln + "\n")
print("pseudo: M=%d x=%d" % (len(pseudo_m), len(pseudo_x)))
PYEOF
if [ -n "$(cd "$WORK/stage" && find . \( -type b -o -type c \) -print -quit)" ]; then
    echo "whiteout in stage" >&2
    (cd "$WORK/stage" && find . \( -type b -o -type c \)) >&2
    exit 1
fi
mksquashfs "$WORK/stage" "$WORK/out/$LEAF" \
    -comp xz -b 131072 -force-uid 0 -force-gid 0 -pseudo-override \
    -pf "$WORK/install.pseudo" -no-progress -noappend \
    -e '.DS_Store' -xattrs-exclude '^com\.apple\.' 2>&1 | tail -2
# 検証: xattr は公式値、中身は統合層と一致、5 指名の閉包は既設・repo・指名で閉じる。
python3 -I - "$HERE" "$WORK/out/$LEAF" "$OFFJSON" "$WORK" <<'PYEOF'
import io
import json
import lzma
import re
import subprocess
import sys
import tarfile
here, leaf, offjson, work = sys.argv[1:5]
sys.path.insert(0, here + "/tools/ubuntu-merge")
from inventory import pf_metadata  # noqa: E402
vend = json.load(open(offjson, encoding="utf-8"))["paths"]
rec, _ = pf_metadata(leaf)
assert not [p for p in rec
            if rec[p].get("t") == "c" or rec[p].get("t") == "b"], "whiteout in leaf"
for p, v in vend.items():
    assert rec[p]["x"] == v["x"], (p, rec[p]["x"], v["x"])
key = ["etc/calamares/modules/unpackfs.conf",
       "etc/calamares/modules/before_bootloader_context.conf",
       "etc/calamares/bootrepo-apt.sh",
       "dists/resolute/Release",
       "dists/resolute/main/binary-amd64/Packages",
       "pool/main/g/grub2-signed/grub-efi-amd64-signed_1.215+2.14-2ubuntu1_amd64.deb",
       "pool/main/s/shim-signed/shim-signed_1.59+15.8-0ubuntu2_amd64.deb",
       "usr/bin/dracut", "usr/bin/ping", "usr/bin/mtr-packet"]
missing = [p for p in key if p not in rec]
assert not missing, missing
print("install verify: %d paths, xattrs match official" % len(rec))
PYEOF
for f in usr/bin/ping usr/bin/mtr-packet; do
    LAYER=$(python3 -c "import json,sys;print(json.load(open('$OFFJSON'))['paths']['$f']['int_layer'])")
    OFF=$(xorriso -indev "$ISO" -find /casper -name "$LAYER" -exec report_lba -- 2>/dev/null | awk -F'[ ,]+' '/File data lba/ {print $5 * 2048}')
    rm -rf "$WORK/cmp"
    unsquashfs -o "$OFF" -d "$WORK/cmp" -f "$ISO" "$f" 2>&1 | tail -2
    cmp "$WORK/stage/$f" "$WORK/cmp/$f"
    rm -rf "$WORK/cmp"
done
echo "content cmp ok (ping, mtr-packet)"
# 指名集合の推移閉包の検査 (旧 aptfix 層の失敗を再発させない)。
# 既設に無い物は指名に含めること (--no-upgrade のため)。
python3 -I - "$WORK" <<'PYEOF'
import io
import lzma
import os
import re
import subprocess
import sys
import tarfile
work = sys.argv[1]
INSTALLED = {
    "debconf", "grub-common", "grub-pc", "grub2-common", "libc6",
    "libdevmapper1.02.1", "libefiboot1t64", "libefivar1t64",
    "libfreetype6", "libfuse3-4", "liblzma5", "gettext-base", "python3",
    "python3-apt", "mokutil", "sbsigntool", "openssl", "libpopt0",
}
script = open(work + "/stage/etc/calamares/bootrepo-apt.sh").read()
named = set()
for m in re.finditer(r"install\s+-y\b(.*?)(?:\n(?!\s)|$)", script, re.S):
    for tok in m.group(1).split():
        if tok.startswith("-") or "=" in tok or tok.startswith("$"):
            continue
        if re.fullmatch(r"[a-z0-9][a-z0-9.+\-]*", tok):
            named.add(tok)
assert "grub-efi-amd64-bin" in named, named
assert "grub-efi-amd64-unsigned" in named, named
assert "--no-upgrade" in script


def control(deb):
    members = subprocess.check_output(["ar", "t", deb], text=True).split()
    ctl = [m for m in members if m.startswith("control.tar")][0]
    raw = subprocess.check_output(["ar", "p", deb, ctl])
    if ctl.endswith(".zst"):
        raw = subprocess.check_output(["unzstd", "-c"], input=raw)
    else:
        raw = lzma.decompress(raw)
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        text = tar.extractfile("./control").read().decode()
    fields = {}
    for tline in text.splitlines():
        if re.match(r"^[A-Za-z-]+:", tline):
            key, _, val = tline.partition(":")
            fields[key.strip()] = val.strip()
    return fields


metas = {}
for root, _, files in os.walk(work + "/stage/pool"):
    for name in files:
        if name.endswith(".deb"):
            meta = control(os.path.join(root, name))
            metas[meta["Package"]] = meta
need = set(named)
seen = set()
while need - seen:
    pkg = (need - seen).pop()
    seen.add(pkg)
    if pkg in INSTALLED:
        continue
    assert pkg in metas, ("not installed and not in repo", pkg)
    for dep in metas[pkg].get("Depends", "").split(","):
        dep = dep.strip()
        if not dep:
            continue
        alts = [a.strip() for a in dep.split("|")]
        names = []
        for a in alts:
            m = re.match(r"([A-Za-z0-9.+\-:]+)", a)
            names.append(m.group(1))
        if not any(n in INSTALLED or n in named for n in names):
            raise AssertionError(("dep not named", pkg, dep))
print("closure ok: named=%s" % sorted(named))
PYEOF
rm -f "$WORK"/int-*.squashfs "$WORK/extract.list"
wc -c "$WORK/out/$LEAF"
cp "$CONF" "$WORK/out/unpackfs-install.conf"
printf '%s\n' common.squashfs common.dl.squashfs \
    common.dl.lubuntu.squashfs "$LEAF" > "$WORK/out/lubuntu.list"
BOOTKIT_LUBUNTU_LEAF=$LEAF python3 -I "$HERE/tools/ubuntu-merge/grub.py" > "$WORK/out/grub.cfg"
grep -q "layerfs-path=$LEAF" "$WORK/out/grub.cfg" \
    || { echo "grub.cfg missing new leaf" >&2; exit 1; }
xorriso -dev "$ISO" -boot_image any replay \
    -map "$WORK/out/$LEAF" "/casper/$LEAF" \
    -map "$WORK/out/lubuntu.list" /casper/bootkit-chains/lubuntu.list \
    -map "$WORK/out/grub.cfg" /boot/grub/grub.cfg
python3 -I "$HERE/tools/ubuntu-merge/fix-pvd.py" "$ISO"
xorriso -indev "$ISO" -osirrox on \
    -extract "/casper/$LEAF" "$WORK/out/$LEAF.roundtrip" \
    -extract /casper/bootkit-chains/lubuntu.list "$WORK/out/lubuntu.list.roundtrip" \
    -extract /boot/grub/grub.cfg "$WORK/out/grub.cfg.roundtrip" -- 2>&1 | tail -1
cmp "$WORK/out/$LEAF" "$WORK/out/$LEAF.roundtrip"
cmp "$WORK/out/lubuntu.list" "$WORK/out/lubuntu.list.roundtrip"
cmp "$WORK/out/grub.cfg" "$WORK/out/grub.cfg.roundtrip"
xorriso -indev "$ISO" -osirrox on -lsl /casper -- 2>&1 | grep -E "install|lubuntu"
wc -c "$WORK/out/$LEAF"
LEAF_LBA=$(xorriso -indev "$ISO" -find /casper \
    -name "$LEAF" -exec report_lba -- 2>/dev/null \
    | awk -F'[ ,]+' '/File data lba/ {print $5}')
LEAF_OFF=$((LEAF_LBA * 2048))
rm -rf "$WORK/verify"
mkdir -p "$WORK/verify"
unsquashfs -o "$LEAF_OFF" -d "$WORK/verify" -f "$ISO" \
    etc/calamares/modules/unpackfs.conf \
    etc/calamares/modules/before_bootloader_context.conf \
    etc/calamares/bootrepo-apt.sh \
    dists/resolute/Release \
    usr/bin/ping 2>&1 | tail -1
test -f "$WORK/verify/etc/calamares/modules/unpackfs.conf"
test -f "$WORK/verify/usr/bin/ping"
test ! -b "$WORK/verify/usr/bin/ping" && test ! -c "$WORK/verify/usr/bin/ping"
grep -q "common.dl.lubuntu.install.squashfs" \
    "$WORK/verify/etc/calamares/modules/unpackfs.conf"
grep -q "sh /etc/calamares/bootrepo-apt.sh" \
    "$WORK/verify/etc/calamares/modules/before_bootloader_context.conf"
grep -q "grub-efi-amd64-bin grub-efi-amd64-unsigned" \
    "$WORK/verify/etc/calamares/bootrepo-apt.sh"
grep -q -- "--no-upgrade" "$WORK/verify/etc/calamares/bootrepo-apt.sh"
sh -n "$WORK/verify/etc/calamares/bootrepo-apt.sh"
grep -q "^Date: [A-Z][a-z][a-z], [0-9][0-9] [A-Z][a-z][a-z] [0-9][0-9][0-9][0-9] " \
    "$WORK/verify/dists/resolute/Release"
echo "leaf verify: install layer (unpackfs 4 sources + ctxfix conf + apt script + Release + ping) ok"
