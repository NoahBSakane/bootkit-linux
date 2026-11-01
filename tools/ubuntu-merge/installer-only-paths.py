#!/usr/bin/env python3
"""installer 層だけに在るパスの列挙: 公式 Server ISO の 4 層を突き合わせる。

使い方:
  python3 -I tools/ubuntu-merge/installer-only-paths.py OFFICIAL_SERVER_ISO OUT_TXT WORKDIR [--overlap-report PATH]

  OFFICIAL_SERVER_ISO (読むだけ) から下の 4 層を WORKDIR に取り出し、
  unsquashfs -pf で全パスを取る:
    下 2 層: ubuntu-server-minimal.squashfs (low1)
            ubuntu-server-minimal.ubuntu-server.squashfs (low2)
    installer 層: ...ubuntu-server.installer.squashfs (inst1)
                  ...ubuntu-server.installer.generic.squashfs (inst2)
  installer 層の和集合から下層の和集合を除いたパスを OUT_TXT に書く
  (絶対パスで 1 行 1 件、sort 済み。先頭に # の注記行)。
  下層にも在るパス (installer 層が上書きした物) は除いて残し、
  種類・内容の差を標準出力と --overlap-report に報告する。
  取り出した squashfs はその場で消す (一時 1.5GB 以内)。

late-commands での使い方は docs/ubuntu-merge.md を見る:
  rm -rf の対象は /target/<パス> のみ (空文字ガード付き)。
"""
import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(HERE, "tools", "ubuntu-merge"))
from inventory import pf_metadata  # noqa: E402

LOWERS = ["ubuntu-server-minimal.squashfs",
          "ubuntu-server-minimal.ubuntu-server.squashfs"]
INSTS = ["ubuntu-server-minimal.ubuntu-server.installer.squashfs",
         "ubuntu-server-minimal.ubuntu-server.installer.generic.squashfs"]


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("failed: %s\n%s" % (" ".join(cmd), p.stderr[-2000:]))
    return p


def extract(iso, casper_path, dest):
    if os.path.exists(dest):
        os.remove(dest)
    run(["xorriso", "-indev", iso, "-osirrox", "on",
         "-extract", "/casper/" + casper_path, dest])
    return dest


def fs_used_bytes(sqfs):
    # unsquashfs -s の "Filesystem size N bytes" を抜く (無圧縮の目安)。
    p = run(["unsquashfs", "-s", sqfs])
    for line in (p.stdout + p.stderr).split("\n"):
        if line.startswith("Filesystem size"):
            return int(line.split()[2])
    return -1


def cat_bytes(sqfs, relpath):
    # -cat で 1 件ずつ読む。-no-wildcards を付けないと
    # バックスラッシュ入りの実在名 (systemd の \x2d 逃がし等) が
    # glob 扱いで当たらない。sqfscat は同じ名を読めないため使わない。
    p = subprocess.run(["unsquashfs", "-cat", "-no-wildcards",
                        sqfs, relpath], capture_output=True)
    if p.returncode != 0:
        raise RuntimeError("unsquashfs -cat failed: %s %s: %s"
                           % (sqfs, relpath, p.stderr[:300]))
    return p.stdout


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def main(argv):
    if len(argv) < 3 or "--help" in argv:
        print(__doc__, file=sys.stderr)
        return 2
    iso, out_txt, workdir = argv[0], argv[1], argv[2]
    overlap_report = None
    if "--overlap-report" in argv:
        overlap_report = argv[argv.index("--overlap-report") + 1]
    os.makedirs(workdir, exist_ok=True)
    outdir = os.path.dirname(os.path.abspath(out_txt))
    os.makedirs(outdir, exist_ok=True)

    layers = {}   # name -> pf rec
    sizes = {}    # name -> (compressed bytes, fs bytes)
    for name in LOWERS + INSTS:
        tmp = os.path.join(workdir, "iol-" + name)
        print("extract %s" % name, flush=True)
        extract(iso, name, tmp)
        rec, _ = pf_metadata(tmp)
        layers[name] = rec
        sizes[name] = (os.path.getsize(tmp), fs_used_bytes(tmp))
        os.remove(tmp)

    lower = set(layers[LOWERS[0]]) | set(layers[LOWERS[1]])
    inst = set(layers[INSTS[0]]) | set(layers[INSTS[1]])
    only = sorted(inst - lower)
    over = sorted(inst & lower)

    def kind_of(rec, path):
        r = rec.get(path, {})
        if "t" in r:
            return r["t"]
        if "linkto" in r:
            return "h"  # ハードリンク (L 行のみ)
        return "?"

    def holder(path):
        # 可視の版を持つ層: installer 側は inst2 (generic) が上。
        if path in layers[INSTS[1]]:
            return INSTS[1]
        return INSTS[0]

    with open(out_txt, "w", encoding="utf-8") as f:
        f.write("# installer 層だけに在るパス (公式 Server ISO の\n")
        f.write("#   %s\n" % INSTS[0])
        f.write("#   %s\n" % INSTS[1])
        f.write("# から下の 2 層 %s, %s に在るパスを除いた物。\n"
                % (LOWERS[0], LOWERS[1]))
        f.write("# 絶対パスで 1 行 1 件。late-commands では /target/<パス>\n")
        f.write("# のみを rm -rf する (空文字ガード付き)。\n")
        for p in only:
            f.write("/" + p + "\n")

    # 内訳の報告。ファイル内容の合計は sqfscat 実測で行う
    # (pf の R 行は "mtime mode uid gid size ..." であることを -ll と
    # 突き合わせて確認済みだが、合計は実測値を優先する)。
    from collections import Counter
    tc = Counter()
    n_files, content_total = 0, 0
    for p in only:
        h = holder(p)
        t = kind_of(layers[h], p)
        tc[t] += 1
        if t == "f":
            n_files += 1
            content_total += len(cat_bytes(_reget(iso, workdir, h), p))
    lines = []
    lines.append("installer layers total paths: %d" % len(inst))
    lines.append("lower layers total paths: %d" % len(lower))
    lines.append("installer-only paths: %d" % len(only))
    lines.append("installer-only by type: %s"
                 % dict(sorted(tc.items())))
    for name in LOWERS + INSTS:
        comp, fsb = sizes[name]
        lines.append("layer %s: compressed=%d fs=%d" % (name, comp, fsb))
    lines.append("installer-only regular files: %d content bytes total: %d"
                 % (n_files, content_total))
    # overlap (下層にも在る = installer 層が上書きした物) の差。
    lines.append("overlap paths (kept, installer overwrote): %d" % len(over))
    oc = Counter()
    for p in over:
        # 可視の下層は low2 が上。installer 側は holder。
        h = holder(p)
        lowrec = layers[LOWERS[1]] if p in layers[LOWERS[1]] \
            else layers[LOWERS[0]]
        it = kind_of(layers[h], p)
        lt = kind_of(lowrec, p)
        oc[(it, lt)] += 1
    lines.append("overlap by (installer-type, lower-type): %s"
                 % dict(sorted(oc.items())))
    report = "\n".join(lines)
    print(report, flush=True)
    if overlap_report:
        with open(overlap_report, "w", encoding="utf-8") as f:
            f.write(report + "\n")
            f.write("--- overlap file content diff "
                    "(installer vs visible lower) ---\n")
            for p in over:
                h = holder(p)
                lowname = LOWERS[1] if p in layers[LOWERS[1]] else LOWERS[0]
                it = kind_of(layers[h], p)
                lowrec = layers[lowname]
                lt = kind_of(lowrec, p)
                if it == "f" and lt == "f":
                    ib = cat_bytes(_reget(iso, workdir, h), p)
                    lb = cat_bytes(_reget(iso, workdir, lowname), p)
                    same = "SAME" if sha256(ib) == sha256(lb) else "DIFFER"
                    f.write("%s file len(inst)=%d len(lower:%s)=%d\n"
                            % (same, len(ib), lowname, len(lb)))
                    f.write("  %s\n" % ("/" + p))
                elif it == "l" and lt == "l":
                    itg = layers[h][p].get("target")
                    ltg = lowrec[p].get("target")
                    same = "SAME" if itg == ltg else "DIFFER"
                    f.write("%s symlink inst->%r lower(%s)->%r\n"
                            % (same, itg, lowname, ltg))
                    f.write("  %s\n" % ("/" + p))
                else:
                    f.write("KEEP type(inst)=%s type(lower:%s)=%s\n"
                            % (it, lowname, lt))
                    f.write("  %s\n" % ("/" + p))
    return 0


_cache = {}


def _reget(iso, workdir, name):
    # overlap の内容比較用に層を取り直す (cache して使い回す)。
    # 呼び出し側で最後に消す。
    if name not in _cache:
        tmp = os.path.join(workdir, "iol-cmp-" + name)
        extract(iso, name, tmp)
        _cache[name] = tmp
    return _cache[name]


if __name__ == "__main__":
    rc = main(sys.argv[1:])
    for tmp in _cache.values():
        if os.path.exists(tmp):
            os.remove(tmp)
    sys.exit(rc)
