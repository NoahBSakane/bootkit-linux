#!/usr/bin/env python3
"""xattr 全数突き合わせ: 公式10層 vs 統合5層。pf メタデータのみ使う。

使い方: python3 -I tools/ubuntu-merge/xfix-audit.py
  各 squashfs を ISO から1つずつ取り出し、pf の x 行だけ JSON 化し、
  取り出した squashfs はその場で消す(一時 5GB 以内)。
  結果は build/evidence/install-sources/xfix/ に書く。
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(HERE, "tools", "ubuntu-merge"))
from inventory import pf_metadata  # noqa: E402

OFF = "/Users/nbs/Downloads/ubuntu-merge-research-20261029"
INT = ("/Users/nbs/Downloads/bootkit-ubuntu-merge-20261101/"
       "ubuntu-merge-26.04.1-amd64.iso")
WORK = os.path.join(HERE, "build", "work", "xfix")
OUT = os.path.join(HERE, "build", "evidence", "install-sources", "xfix")

OFFICIAL = [
    ("ubuntu-26.04.1-desktop-amd64.iso",
     ["minimal.squashfs", "minimal.standard.squashfs",
      "minimal.standard.live.squashfs"], "ubuntu"),
    ("lubuntu-26.04.1-desktop-amd64.iso",
     ["minimal.squashfs", "minimal.standard.squashfs",
      "minimal.standard.live.squashfs"], "lubuntu"),
    ("ubuntu-26.04.1-live-server-amd64.iso",
     ["ubuntu-server-minimal.squashfs",
      "ubuntu-server-minimal.ubuntu-server.squashfs",
      "ubuntu-server-minimal.ubuntu-server.installer.squashfs",
      "ubuntu-server-minimal.ubuntu-server.installer.generic.squashfs"],
     "server"),
]
INTEGRATED = ["common.squashfs", "common.dl.squashfs",
              "common.dl.ubuntu.squashfs", "common.dl.lubuntu.squashfs",
              "common.server.squashfs"]
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


def extract(iso, casper_path, dest):
    if os.path.exists(dest):
        os.remove(dest)
    run(["xorriso", "-indev", iso, "-osirrox", "on",
         "-extract", "/casper/" + casper_path, dest])
    return dest


def pf_layer(sqfs):
    # (全パス集合, xattr 辞書) を返す。可視判定は全パス集合で行う。
    rec, _ = pf_metadata(sqfs)
    paths = set(rec)
    xa = {p: dict(m.get("x") or {}) for p, m in rec.items()}
    return paths, xa


def main():
    os.makedirs(WORK, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    log = open(os.path.join(OUT, "audit.log"), "w", encoding="utf-8")

    def msg(s):
        print(s, flush=True)
        log.write(s + "\n")
        log.flush()

    # 公式: OS ごとに可視ビュー(上層優先)を作る。
    # 可視の版は、そのパスを持つ最上層の版である
    # (xattr の有無にかかわらず)。overlay と同じ規則。
    official_view = {}  # os -> {path: {xname: val}}
    official_holder = {}  # os -> {path: layer}
    for iso_name, layers, osname in OFFICIAL:
        iso = os.path.join(OFF, iso_name)
        allpaths, allxa = {}, {}
        for layer in layers:
            tmp = os.path.join(WORK, "off.squashfs")
            msg("extract official %s/%s" % (osname, layer))
            extract(iso, layer, tmp)
            paths, xa = pf_layer(tmp)
            msg("  pf: %d paths with xattrs=%d" %
                (len(paths), sum(1 for v in xa.values() if v)))
            os.remove(tmp)
            allpaths[layer] = paths
            allxa[layer] = xa
        view, holder = {}, {}
        for layer in layers:  # 下から上へ重ね、上書きする
            for p in allpaths[layer]:
                view[p] = allxa[layer].get(p, {})
                holder[p] = layer
        official_view[osname] = view
        official_holder[osname] = holder
        with open(os.path.join(OUT, "official-%s.json" % osname), "w",
                  encoding="utf-8") as f:
            json.dump({p: x for p, x in view.items() if x}, f,
                      sort_keys=True)

    # 統合: 層ごとの xattr と OS ごとの可視ビュー。
    int_layer, int_paths = {}, {}
    for layer in INTEGRATED:
        tmp = os.path.join(WORK, "int.squashfs")
        msg("extract integrated %s" % layer)
        extract(INT, layer, tmp)
        paths, xa = pf_layer(tmp)
        int_layer[layer] = xa
        int_paths[layer] = paths
        msg("  pf: %d paths with xattrs=%d" %
            (len(paths), sum(1 for v in xa.values() if v)))
        os.remove(tmp)
        with open(os.path.join(OUT, "integrated-%s.json" % layer), "w",
                  encoding="utf-8") as f:
            json.dump({p: x for p, x in xa.items() if x}, f,
                      sort_keys=True)

    int_view, int_holder = {}, {}
    for osname, chain in CHAINS.items():
        view, holder = {}, {}
        for layer in chain:
            for p in int_paths[layer]:
                view[p] = int_layer[layer].get(p, {})
                holder[p] = layer
        int_view[osname] = view
        int_holder[osname] = holder

    # 突き合わせ: OS ごとに可視 xattr を比較。
    mismatch = []  # (os, path, xname, official, integrated, int_layer)
    for osname in CHAINS:
        ov, iv = official_view[osname], int_view[osname]
        for p in sorted(set(ov) | set(iv)):
            ox, ix = ov.get(p, {}), iv.get(p, {})
            for xn in sorted(set(ox) | set(ix)):
                if ox.get(xn) != ix.get(xn):
                    mismatch.append((osname, p, xn, ox.get(xn), ix.get(xn),
                                     int_holder[osname].get(p),
                                     official_holder[osname].get(p)))
    with open(os.path.join(OUT, "mismatch.json"), "w",
              encoding="utf-8") as f:
        json.dump([{"os": m[0], "path": m[1], "xattr": m[2],
                    "official": m[3], "integrated": m[4],
                    "int_layer": m[5], "off_layer": m[6]} for m in mismatch],
                  f, indent=1, sort_keys=False)
    by_name, by_layer, by_os = {}, {}, {}
    for m in mismatch:
        by_name[m[2]] = by_name.get(m[2], 0) + 1
        by_layer[(m[0], m[5])] = by_layer.get((m[0], m[5]), 0) + 1
        by_os[m[0]] = by_os.get(m[0], 0) + 1
    msg("TOTAL mismatch rows (os,path,xattr): %d" % len(mismatch))
    msg("by xattr name: %s" % json.dumps(by_name, sort_keys=True))
    msg("by os: %s" % json.dumps(by_os, sort_keys=True))
    msg("by (os,int_layer): %s"
        % json.dumps({"%s/%s" % k: v for k, v in sorted(by_layer.items())}))
    # 同一パスで OS をまたいだ重複を除いた件数も出す。
    uniq_paths = set((m[1], m[2]) for m in mismatch)
    msg("UNIQUE (path,xattr) across OS: %d" % len(uniq_paths))
    log.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
