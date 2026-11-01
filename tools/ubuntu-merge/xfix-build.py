#!/usr/bin/env python3
"""xattr 補正層(xfix)の構築: 不一致パスだけを上書き層にする。

使い方: python3 -I tools/ubuntu-merge/xfix-build.py
  前提: xfix-audit.py の結果 (build/evidence/install-sources/xfix/
  mismatch.json・official-*.json) があること。
  統合 ISO から必要な層だけ1つずつ取り出し、終われば消す。
  出力: build/work/xfix/<leaf>.squashfs (+ .pseudo) と検証記録。

方針 (docs/ubuntu-merge.md の層の作り方に従う):
- 中身・モード・所有者・時刻は統合層の版のまま。正しい xattr だけ
  公式の可視値で置く。whiteout は使わない (上書きで隠す)。
- leaf 名は common.server.xfix / common.dl.ubuntu.xfix /
  common.dl.lubuntu.xfix (casper のドット規則で親連鎖を導出)。
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(HERE, "tools", "ubuntu-merge"))
from inventory import escape_pf, pf_metadata  # noqa: E402

INT = ("/Users/nbs/Downloads/bootkit-ubuntu-merge-20261101/"
       "ubuntu-merge-26.04.1-amd64.iso")
WORK = os.path.join(HERE, "build", "work", "xfix")
EVID = os.path.join(HERE, "build", "evidence", "install-sources", "xfix")

OSLIST = ["ubuntu", "lubuntu", "server"]
LEAF = {"ubuntu": "common.dl.ubuntu.xfix.squashfs",
        "lubuntu": "common.dl.lubuntu.xfix.squashfs",
        "server": "common.server.xfix.squashfs"}
CHAINS = {
    "ubuntu": ["common.squashfs", "common.dl.squashfs",
               "common.dl.ubuntu.squashfs"],
    "lubuntu": ["common.squashfs", "common.dl.squashfs",
                "common.dl.lubuntu.squashfs"],
    "server": ["common.squashfs", "common.server.squashfs"],
}


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("failed: %s\n%s" % (" ".join(cmd), p.stderr[-2000:]))
    return p


def main():
    os.makedirs(WORK, exist_ok=True)
    os.makedirs(EVID, exist_ok=True)
    log = open(os.path.join(EVID, "build.log"), "w", encoding="utf-8")

    def msg(s):
        print(s, flush=True)
        log.write(s + "\n")
        log.flush()

    mm = json.load(open(os.path.join(EVID, "mismatch.json"),
                        encoding="utf-8"))
    official = {}
    for osname in OSLIST:
        official[osname] = json.load(
            open(os.path.join(EVID, "official-%s.json" % osname),
                 encoding="utf-8"))

    # OS ごとに補正対象パス集合 (可視の公式 xattr が空でないものに限る)。
    # 空への補正 (xattr の削除) は上書き層では表せないため対象外。
    # 今回は該当なし (全件 DIFF で公式側に値あり)。
    targets = {}
    for osname in OSLIST:
        paths = set(m["path"] for m in mm if m["os"] == osname)
        targets[osname] = sorted(paths)
        for m in mm:
            if m["os"] == osname and m["official"] is None:
                raise RuntimeError("cannot remove xattr via overlay: %r"
                                   % (m,))
        msg("%s: %d paths" % (osname, len(targets[osname])))

    # 必要な統合層の pf 全記録 (種別・モード・所有者・時刻のため)。
    need_layers = set()
    for m in mm:
        need_layers.add(m["int_layer"])
    int_meta = {}
    for layer in sorted(need_layers):
        tmp = os.path.join(WORK, "int.squashfs")
        msg("extract %s" % layer)
        run(["xorriso", "-indev", INT, "-osirrox", "on",
             "-extract", "/casper/" + layer, tmp])
        rec, _ = pf_metadata(tmp)
        int_meta[layer] = rec
        # 通常ファイルの中身を取り出す (xattr なしでよい)。
        files = [m["path"] for m in mm
                 if m["int_layer"] == layer
                 and (rec.get(m["path"], {}).get("t") == "f")]
        if files:
            lst = os.path.join(WORK, "extract.list")
            with open(lst, "w", encoding="utf-8") as f:
                for p in files:
                    f.write(p + "\n")
            stage = os.path.join(WORK, "stage-" + layer.replace(".", "_"))
            run(["rm", "-rf", stage])
            os.makedirs(stage)
            run(["unsquashfs", "-no-xattrs", "-no-wildcards", "-f",
                 "-d", stage, "-extract-file", lst, tmp])
            os.remove(lst)
        os.remove(tmp)

    summary = {}
    for osname in OSLIST:
        leaf = LEAF[osname]
        tag = leaf.replace(".", "_")
        stage = os.path.join(WORK, "xfix-" + tag)
        run(["rm", "-rf", stage])
        os.makedirs(stage)
        pseudo_m, pseudo_x = [], []
        n_file, n_dir = 0, 0
        for p in targets[osname]:
            mrow = [m for m in mm
                    if m["os"] == osname and m["path"] == p][0]
            rec = int_meta[mrow["int_layer"]].get(p, {})
            t = rec.get("t")
            if t == "d":
                os.makedirs(os.path.join(stage, p), exist_ok=True)
                n_dir += 1
            elif t == "f":
                src = os.path.join(
                    WORK, "stage-" + mrow["int_layer"].replace(".", "_"), p)
                dst = os.path.join(stage, p)
                os.makedirs(os.path.dirname(dst) or stage, exist_ok=True)
                run(["cp", "-p", src, dst])
                n_file += 1
            else:
                raise RuntimeError("unsupported type %r for %r" % (t, p))
            pseudo_m.append((p, "%s M %d %o %d %d"
                             % (escape_pf(p, True), rec["mtime"],
                                rec["mode"], rec["uid"], rec["gid"])))
            for xn, xv in sorted(official[osname][p].items()):
                pseudo_x.append("%s x %s=%s"
                                % (escape_pf(p, True), xn, xv))
        # 大文字小文字だけが違う衝突がないこと (作業場所は非敏感)。
        lowered = {}
        for p in targets[osname]:
            key = p.lower()
            if key in lowered:
                raise RuntimeError("case collision: %r vs %r"
                                   % (lowered[key], p))
            lowered[key] = p
        pseudo_path = os.path.join(WORK, leaf + ".pseudo")
        with open(pseudo_path, "w", encoding="utf-8",
                  errors="surrogateescape") as f:
            for _, ln in sorted(pseudo_m):
                f.write(ln + "\n")
            for ln in pseudo_x:
                f.write(ln + "\n")
        out = os.path.join(WORK, leaf)
        if os.path.exists(out):
            os.remove(out)
        cmd = ["mksquashfs", stage, out, "-comp", "xz", "-b", "131072",
               "-force-uid", "0", "-force-gid", "0", "-pseudo-override",
               "-pf", pseudo_path, "-no-progress",
               "-e", ".DS_Store",
               "-xattrs-exclude", "^com\\.apple\\."]
        run(cmd)
        size = os.path.getsize(out)
        msg("built %s: %d bytes (%d files, %d dirs)" %
            (leaf, size, n_file, n_dir))
        summary[leaf] = {"size": size, "files": n_file, "dirs": n_dir,
                         "paths": targets[osname]}
        run(["rm", "-rf", stage])
    for layer in sorted(need_layers):
        st = os.path.join(WORK, "stage-" + layer.replace(".", "_"))
        if os.path.exists(st):
            run(["rm", "-rf", st])
    with open(os.path.join(EVID, "xfix-summary.json"), "w",
              encoding="utf-8") as f:
        json.dump(summary, f, indent=1, sort_keys=True,
                  ensure_ascii=False)
    log.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
