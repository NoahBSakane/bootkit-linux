#!/bin/sh
# R2b: 既存install層のbootrepo/context部分をそのまま流用する。
# 白抜き蘇生とxattr補正は行わない。WORKは呼び出し側で新規作成する。
set -eu
IN=${1:?official Lubuntu ISO}
WORK=${2:?new work directory}
CONF=${3:?unpackfs configuration}
OUT=${4:?output squashfs}
mkdir -p "$WORK/stage/etc/calamares/modules" "$WORK/debs"
cp "$CONF" "$WORK/stage/etc/calamares/modules/unpackfs.conf"
chmod 644 "$WORK/stage/etc/calamares/modules/unpackfs.conf"
# 手順本体は層内の shell 記述 (bootrepo-apt.sh) に置く。
# contextualprocess の command の素朴な値は 1 行で書かねばならず、
# 長い apt 行を YAML に直書きすると yaml-cpp の map 値の誤読を招くため、
# conf 側は短い sh 呼び出し 1 行だけにする (5 指名版)。
# この層は live 専用で標的へ展開されない。そのため conf は dontChroot: true
# とし、標的の root (${ROOT}) を引数に渡す。スクリプトは live の /pool・
# /dists を標的へ一時的に bind し、標的の chroot で apt を動かす。
cat > "$WORK/stage/etc/calamares/bootrepo-apt.sh" <<'SHEOF'
#!/bin/sh
# Install the bootloader debs into the target root ($1) from the repo
# carried by the live layer (/pool, /dists). Runs in the live environment
# (dontChroot); the repo is bind-mounted into the target only while apt runs.
set -eu
R=${1:?target root}
mkdir "$R/pool" "$R/dists" "$R/tmp/calamares-cdrom-sources" "$R/tmp/calamares-cdrom-sources/empty.parts"
cleanup() {
    umount "$R/pool" 2>/dev/null || true
    umount "$R/dists" 2>/dev/null || true
    rmdir "$R/pool" "$R/dists" 2>/dev/null || true
    rm -rf "$R/tmp/calamares-cdrom-sources"
}
trap cleanup EXIT
mount --bind /pool "$R/pool"
mount --bind /dists "$R/dists"
cat > "$R/tmp/calamares-cdrom-sources/cdrom.sources" <<'EOF'
Types: deb
URIs: file:///
Suites: resolute
Components: main
Trusted: yes
EOF
D=/tmp/calamares-cdrom-sources
OPTS="-o Dir::Etc::sourcelist=$D/cdrom.sources -o Dir::Etc::sourceparts=$D/empty.parts"
chroot "$R" apt-get $OPTS update
chroot "$R" apt-get $OPTS install -y --no-upgrade \
    -o Acquire::gpgv::Options::=--ignore-time-conflict \
    grub-efi-amd64-signed grub-efi-amd64-bin grub-efi-amd64-unsigned shim-signed efibootmgr
chroot "$R" apt-get $OPTS install -y --no-upgrade \
    -o Acquire::gpgv::Options::=--ignore-time-conflict \
    shim-signed
SHEOF
chmod 755 "$WORK/stage/etc/calamares/bootrepo-apt.sh"
# 上書きの before_bootloader_context.conf。
# command の値は短い呼び出しだけにし、:+空白を含む長い行を避ける。
cat > "$WORK/stage/etc/calamares/modules/before_bootloader_context.conf" <<'CONFEOF'
dontChroot: true
firmwareType:
    bios:    "-/bin/true"
    "*":
        -    command: sh /etc/calamares/bootrepo-apt.sh ${ROOT}
             timeout: 10800
CONFEOF
# YAML の素朴な値 (command の中身) に : を含めないこと
# (yaml-cpp が illegal map value で読めなくなる)。
if awk '/command: /{sub(/.*command: /, ""); if ($0 ~ /: /) print}' \
    "$WORK/stage/etc/calamares/modules/before_bootloader_context.conf" | grep -q .; then
    echo "plain scalar with colon-space found" >&2
    exit 1
fi
# grub2-commonのdebは公式Lubuntu ISOに無いため含めない。既設の依存として扱う。
# bootloader の deb と efibootmgr (grub-install の実行時に要る) を抜く。
DEBS="pool/main/g/grub2-signed/grub-efi-amd64-signed_1.215+2.14-2ubuntu1_amd64.deb
pool/main/g/grub2-unsigned/grub-efi-amd64-bin_2.14-2ubuntu1_amd64.deb
pool/main/g/grub2-unsigned/grub-efi-amd64-unsigned_2.14-2ubuntu1_amd64.deb
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
assert len(pool) == 5, [os.path.basename(p) for p in pool]


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
mksquashfs "$WORK/stage" "$OUT" -comp xz -b 131072 \
    -force-uid 0 -force-gid 0 -noappend -no-progress -processors 4 \
    -xattrs-exclude '^com\.apple\.' -e '.DS_Store'
