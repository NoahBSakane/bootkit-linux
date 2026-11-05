#!/bin/sh
# 統合層ツール群の軽量試験。実 ISO は使わず、小さな合成 squashfs で
# 往復・分割・検証の対照試験を行う。
set -eu
HERE=$(CDPATH='' cd -- "$(dirname "$0")/.." && pwd)
TOOLS=$HERE/tools/ubuntu-merge
WORK=$(mktemp -d "$HERE/test-results.XXXXXX")
trap 'rm -rf "$WORK"' 0
trap 'exit 1' HUP INT TERM
cd "$WORK"
export LC_ALL=C

# 1. 合成ツリーを作る(通常ファイル・空 dir・symlink・空白名)。
mkdir -p src/etc src/usr/share/fonts
echo hello > src/etc/motd
# 空白を含む xattr 値 (security.capability の 0x20 バイトの代理)。
xattr -w user.note 'hello world' src/etc/motd
printf 'A%.0s' $(seq 1 100) > src/etc/big.bin
ln -s ../etc/motd src/usr/link1
ln -s /nonexistent src/usr/dangle
touch src/usr/share/fonts/a
mkdir -p "src/sp ace"
echo "sp ace" > "src/sp ace/f ile.txt"
mksquashfs src o1.squashfs -comp xz -b 131072 -no-progress > /dev/null

# 2. 棚卸し→疑似→再構成→再棚卸しでビューが一致すること。
mkdir -p st1
unsquashfs -no-xattrs -no-wildcards -f -d st1 o1.squashfs > /dev/null
python3 -I "$TOOLS/inventory.py" o1.squashfs L1 inv st1
mkdir -p st2
unsquashfs -no-xattrs -no-wildcards -f -d st2 o1.squashfs > /dev/null
python3 -I "$TOOLS/inventory.py" o1.squashfs L1b inv st2
cmp inv/L1.jsonl inv/L1b.jsonl
# 空白を含む xattr 値は切れずに棚卸しされること
# (security.capability 欠けの回帰。設置の rsync -X が EINVAL で失敗する)。
python3 -I - <<'PYEOF'
import json
recs = [json.loads(x) for x in open("inv/L1.jsonl", encoding="utf-8")]
motd = [r for r in recs if r["p"] == "etc/motd"]
assert len(motd) == 1, motd
assert motd[0]["x"].get("user.note") == "hello world", motd[0]["x"]
print("xattr roundtrip OK")
PYEOF
cat > check_pf.py <<'PYEOF'
import subprocess, sys
def pfmeta(sqfs):
    p = subprocess.run(["unsquashfs", "-pf", "-", sqfs], capture_output=True)
    data = p.stdout
    i = data.find(b"# START OF DATA")
    meta = data[:i] if i >= 0 else data
    lines = []
    for ln in meta.split(b"\n"):
        if ln.startswith(b"#"):
            continue
        parts = ln.split(b" ")
        if len(parts) < 2:
            continue
        if parts[0] == b"/":
            continue
        if parts[1] in (b"D", b"R"):
            lines.append(b" ".join([parts[0], b"M"] + parts[2:6]))
        else:
            lines.append(ln)
    return sorted(lines)
a, b = pfmeta(sys.argv[1]), pfmeta(sys.argv[2])
if a != b:
    print("PF-DIFF orig=%d new=%d" % (len(a), len(b)))
    for ln in sorted(set(a) - set(b))[:10]:
        print("ONLY-ORIG", ln[:160])
    for ln in sorted(set(b) - set(a))[:10]:
        print("ONLY-NEW", ln[:160])
    sys.exit(1)
print("PF-MATCH %d" % len(a))
PYEOF

# 3. pf2pseudo 往復: 除外なし・全量展開→再構成で pf が一致すること。
unsquashfs -pf - o1.squashfs > o1.pfmeta 2>/dev/null
python3 -I "$TOOLS/pf2pseudo.py" --exclude-file excl.txt o1.pfmeta o1.pseudo
test ! -s excl.txt
mksquashfs st2 o2.squashfs -comp xz -b 131072 \
    -force-uid 0 -force-gid 0 -pseudo-override -pf o1.pseudo \
    -xattrs-exclude '^com\.apple\.' -e '.DS_Store' -no-progress > /dev/null
python3 -I "$WORK/check_pf.py" o1.squashfs o2.squashfs

# 4. 検証器: 同一の層を繰り返し照合できること。
mkdir -p newdir
cp o1.squashfs newdir/L1.squashfs
printf '{"t": ["L1"]}\n' > chains.json
python3 -I "$TOOLS/verify.py" inv chains.json newdir chains.json vw1
if python3 -I "$TOOLS/verify.py" inv chains.json newdir chains.json vw1 2>/dev/null; then
    : # 2 回目も成功(冪等)
else
    echo "FAIL: verify should pass on identical layers" >&2; exit 1
fi
# 5. plan の単体試験: 共有判定と shadow 除外。
mkdir -p pinv
for t in d-minimal d-standard d-live l-minimal l-standard l-live s-minimal s-server s-installer s-generic; do : > pinv/$t.jsonl; done
python3 -I - <<'PYEOF' > pinv/d-minimal.jsonl
import json
def r(p, t="f", sha="a", mode=644, uid=0, gid=0, mtime=1000, target=None):
    return {"p": p, "t": t, "mode": mode, "uid": uid, "gid": gid,
            "mtime": mtime, "size": 1, "sha256": sha, "target": target,
            "dev": None, "nlink": 1, "grp": None, "x": {}}
recs = [r("sh/common.txt", sha="c0ffee"),
        r("only-u.txt", sha="u1"),
        r("sh/sub/deep.txt", sha="deep"),
        r("etc/motd", sha="v1")]
print("\n".join(json.dumps(x) for x in recs))
PYEOF
python3 -I - <<'PYEOF' > pinv/d-standard.jsonl
import json
def r(p, t="f", sha="a", mode=644, uid=0, gid=0, mtime=2000, target=None):
    return {"p": p, "t": t, "mode": mode, "uid": uid, "gid": gid,
            "mtime": mtime, "size": 1, "sha256": sha, "target": target,
            "dev": None, "nlink": 1, "grp": None, "x": {}}
recs = [r("sh", t="l", target="elsewhere"),
        r("etc/motd", sha="v2")]
print("\n".join(json.dumps(x) for x in recs))
PYEOF
python3 -I - <<'PYEOF' > pinv/l-minimal.jsonl
import json
def r(p, t="f", sha="a", mode=644, uid=0, gid=0, mtime=1000, target=None):
    return {"p": p, "t": t, "mode": mode, "uid": uid, "gid": gid,
            "mtime": mtime, "size": 1, "sha256": sha, "target": target,
            "dev": None, "nlink": 1, "grp": None, "x": {}}
recs = [r("sh/common.txt", sha="c0ffee"),
        r("sh/only-l.txt", sha="l1")]
print("\n".join(json.dumps(x) for x in recs))
PYEOF
python3 -I "$TOOLS/plan.py" pinv pplan
# sh は ubuntu の上層で symlink が勝つため下層サブツリーは隠れる。
# common.txt は lubuntu だけに残り、C3 にならない。
python3 -I - <<'PYEOF'
import json
layers = json.load(open("pplan/layers.json"))
assert "sh/common.txt" not in layers["common"], "shadowed file leaked to common"
assert "sh/common.txt" not in layers["common.dl.ubuntu"], "ubuntu must not have shadowed file"
assert "sh/common.txt" in layers["common.dl.lubuntu"], "lubuntu copy missing"
assert "only-u.txt" in layers["common.dl.ubuntu"]
assert "sh/only-l.txt" in layers["common.dl.lubuntu"]
assert "sh/sub/deep.txt" not in layers["common.dl.ubuntu"], "shadowed deep file leaked"
assert "etc/motd" in layers["common.dl.ubuntu"]
print("plan unit OK")
PYEOF

# 6. xfix の合成試験: 欠けた xattr 値だけを上書き層で直せること
# (security.capability 欠けの補正層の手順。空白入り値を mksquashfs の
# x 行で運び、再棚卸しで公式値と一致すること)。
python3 -I - <<PYEOF
import subprocess, sys
sys.path.insert(0, "$TOOLS")
from inventory import pf_metadata
rec, _ = pf_metadata("o1.squashfs")
want = rec["etc/motd"]["x"]
assert want.get("user.note") == "hello world", want
open("fx-want.txt", "w").write(repr(sorted(want.items())))
print("xfix want OK")
PYEOF
# 欠けた版 (旧 inventory の切り詰めを模した層) を作る。
printf '%s\n' '"etc/motd" M 1000 644 0 0' '"etc/motd" x user.note=hello' > brok.pseudo
mksquashfs st1 brok.squashfs -comp xz -b 131072 \
    -force-uid 0 -force-gid 0 -pseudo-override -pf brok.pseudo \
    -xattrs-exclude '^com\\.apple\\.' -no-progress > /dev/null
# 補正層: 中身は欠けた層から、xattr は公式値で上書きする。
mkdir -p fxstage/etc && cp -p st1/etc/motd fxstage/etc/motd
printf '%s\n' '"etc/motd" M 1000 644 0 0' '"etc/motd" x user.note=hello world' > fx.pseudo
mksquashfs fxstage fx.squashfs -comp xz -b 131072 \
    -force-uid 0 -force-gid 0 -pseudo-override -pf fx.pseudo \
    -xattrs-exclude '^com\\.apple\\.' -no-progress > /dev/null
python3 -I - <<PYEOF
import sys
sys.path.insert(0, "$TOOLS")
from inventory import pf_metadata
off, _ = pf_metadata("o1.squashfs")
fix, _ = pf_metadata("fx.squashfs")
assert fix["etc/motd"]["x"] == off["etc/motd"]["x"], (fix["etc/motd"], off["etc/motd"])
print("xfix overlay OK")
PYEOF
cmp fxstage/etc/motd st1/etc/motd

# 7. 設置先の検証道具の起動面: QEMU なしで --help と引数検査だけ行う。
OFFLINE=$HERE/tools/offline-install
python3 "$OFFLINE/verify-installed.py" --help > help1.txt
grep -q -- --kernel help1.txt
grep -q -- --initrd help1.txt
grep -q -- --append help1.txt
python3 "$OFFLINE/verify-installed-extra.py" --help > help2.txt
grep -q -- --kernel help2.txt
# --kernel だけでは不足 (--initrd と --append が要る)。
touch fakedisk.qcow2
if python3 "$OFFLINE/verify-installed.py" --disk fakedisk.qcow2 \
    --prefix prefix-nope --kernel /tmp/none 2>err.txt; then
    echo "verify-installed.py must reject --kernel without --initrd" >&2
    exit 1
fi
echo "verify CLI OK"

# 8. plan_stages の合成試験: 段別割り当てと自己検証が通ること。
mkdir -p sinv
python3 -I - <<'PYEOF' > sinv/d-minimal.jsonl
import json
def r(p, t="f", sha="a", mode=644, uid=0, gid=0, mtime=1000, target=None, grp=None):
    return {"p": p, "t": t, "mode": mode, "uid": uid, "gid": gid,
            "mtime": mtime, "size": 1, "sha256": sha, "target": target,
            "dev": None, "nlink": 1, "grp": grp, "x": {}}
recs = [r("sh/common.txt", sha="c0ffee"),
        r("sh/dl.txt", sha="d1"),
        r("only-u.txt", sha="u1"),
        r("etc/motd", sha="v1"),
        r("var/lib/snapd/snaps/x_1.snap", sha="S", grp=0),
        r("var/lib/snapd/seed/snaps/x_1.snap", sha="S", grp=0)]
print("\n".join(json.dumps(x) for x in recs))
PYEOF
python3 -I - <<'PYEOF' > sinv/d-standard.jsonl
import json
def r(p, t="f", sha="a", mode=644, uid=0, gid=0, mtime=2000, target=None, grp=None):
    return {"p": p, "t": t, "mode": mode, "uid": uid, "gid": gid,
            "mtime": mtime, "size": 1, "sha256": sha, "target": target,
            "dev": None, "nlink": 1, "grp": grp, "x": {}}
recs = [r("etc/motd", sha="v2"),
        r("new-u.txt", sha="nu")]
print("\n".join(json.dumps(x) for x in recs))
PYEOF
python3 -I - <<'PYEOF' > sinv/l-minimal.jsonl
import json
def r(p, t="f", sha="a", mode=644, uid=0, gid=0, mtime=1000, target=None, grp=None):
    return {"p": p, "t": t, "mode": mode, "uid": uid, "gid": gid,
            "mtime": mtime, "size": 1, "sha256": sha, "target": target,
            "dev": None, "nlink": 1, "grp": grp, "x": {}}
recs = [r("sh/common.txt", sha="c0ffee"),
        r("sh/dl.txt", sha="d1"),
        r("sh/only-l.txt", sha="l1")]
print("\n".join(json.dumps(x) for x in recs))
PYEOF
python3 -I - <<'PYEOF' > sinv/l-standard.jsonl
import json
def r(p, t="f", sha="a", mode=644, uid=0, gid=0, mtime=2000, target=None, grp=None):
    return {"p": p, "t": t, "mode": mode, "uid": uid, "gid": gid,
            "mtime": mtime, "size": 1, "sha256": sha, "target": target,
            "dev": None, "nlink": 1, "grp": grp, "x": {}}
recs = [r("var/lib/snapd/snaps/x_1.snap", sha="S", grp=0),
        r("var/lib/snapd/seed/snaps/x_1.snap", sha="S", grp=0),
        r("new-l.txt", sha="nl")]
print("\n".join(json.dumps(x) for x in recs))
PYEOF
python3 -I - <<'PYEOF' > sinv/s-minimal.jsonl
import json
def r(p, t="f", sha="a", mode=644, uid=0, gid=0, mtime=1000, target=None, grp=None):
    return {"p": p, "t": t, "mode": mode, "uid": uid, "gid": gid,
            "mtime": mtime, "size": 1, "sha256": sha, "target": target,
            "dev": None, "nlink": 1, "grp": grp, "x": {}}
recs = [r("sh/common.txt", sha="c0ffee"),
        r("only-s.txt", sha="s1")]
print("\n".join(json.dumps(x) for x in recs))
PYEOF
python3 -I - <<'PYEOF' > sinv/s-server.jsonl
import json
def r(p, t="f", sha="a", mode=644, uid=0, gid=0, mtime=2000, target=None, grp=None):
    return {"p": p, "t": t, "mode": mode, "uid": uid, "gid": gid,
            "mtime": mtime, "size": 1, "sha256": sha, "target": target,
            "dev": None, "nlink": 1, "grp": grp, "x": {}}
recs = [r("new-s.txt", sha="ns")]
print("\n".join(json.dumps(x) for x in recs))
PYEOF
python3 -I "$TOOLS/plan_stages.py" sinv splan
python3 -I "$TOOLS/verify_stages.py" sinv splan
python3 -I - <<'PYEOF'
import json
layers = json.load(open("splan/layers.json"))
chains = json.load(open("splan/chains.json"))
snap = layers["common.dl.snap"]
assert "var/lib/snapd/snaps/x_1.snap" in snap
assert "var/lib/snapd/seed/snaps/x_1.snap" in snap
# lubuntu の段2からは除かれ、下の snap 層と重ねて同じになる。
assert "var/lib/snapd/snaps/x_1.snap" not in layers["common.dl.snap.lubuntu.std"]
assert "sh/common.txt" in layers["common"]
assert "sh/dl.txt" in layers["common.dl"]
assert chains["lubuntu"]["minimal"] == ["common", "common.dl", "common.dl.snap.lubuntu"]
assert chains["ubuntu"]["minimal"] == ["common", "common.dl", "common.dl.snap", "common.dl.snap.ubuntu"]
print("plan_stages synthetic OK")
PYEOF
# 9. R2a: 大文字小文字違い・リンク・whiteoutを実物の層で往復する。
# macOSでは既存のcase-sensitive作業領域を指定する。
CASEBASE=${BOOTKIT_CASE_STAGE:-$HERE/build/work/cs}
if [ "$(uname -s)" != Darwin ]; then CASEBASE=$WORK; fi
python3 -I "$TOOLS/test_repack_stages.py" "$CASEBASE" "$WORK/r2a"
echo "PASS: ubuntu-merge synthetic roundtrip"
# 10. R2b: GRUBの9項目・ドット親・設置カタログ・展開条件の合成試験。
python3 -I "$TOOLS/test_stages_layout.py" "$WORK/r2b"
