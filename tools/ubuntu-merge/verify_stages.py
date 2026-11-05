#!/usr/bin/env python3
"""plan_stages.py の割り当ての自己検証。層は作らない。

layers.json から各 OS の段1(Minimal)・段2まで(Normal)のビューを
鎖に沿って重ねて再構成し、棚卸しの公式のビュー(minimal 単体、
minimal + standard)と比べる。比較項目は verify.py と同じ(パス集合・
種別・モード・所有者・xattr・symlink 先・通常ファイルの SHA-256・
デバイス番号。時刻は数えない)。ハードリンクの組が 1 つの層内に
全名前そろって在ることも確かめる。差があれば一覧を出して exit 1。

使い方: verify_stages.py INVDIR OUTDIR
  OUTDIR は plan_stages.py の出力場所(layers.json・chains.json・
  ochains.json がある場所)。
"""
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from plan import build_flat, key_of  # noqa: E402


def load(invdir, tag):
    recs = {}
    with open(os.path.join(invdir, tag + ".jsonl"),
              encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            recs[r["p"]] = (tag, r)
    return recs


def dot_order(chain):
    """層名からドット規則で下から上への順を導く。chains.json の
    記載順によらず、名前のドット段数で並べる。鎖は leaf の接頭辞
    だけから成るため段数で一意に定まる。
    """
    return sorted(chain, key=lambda layer: (len(layer.split(".")), layer))


def stack(layers, chain):
    view = {}
    for layer in dot_order(chain):
        for p, r in layers[layer].items():
            view[p] = r
    nondirs = {p for p, r in view.items() if r["t"] != "d"}
    drop = []
    for q in view:
        parts = q.split("/")
        for i in range(1, len(parts)):
            if "/".join(parts[:i]) in nondirs:
                drop.append(q)
                break
    for q in drop:
        del view[q]
    return view


def main(argv):
    invdir, outdir = argv
    with open(os.path.join(outdir, "layers.json"),
              encoding="utf-8") as f:
        layers = json.load(f)
    with open(os.path.join(outdir, "chains.json"),
              encoding="utf-8") as f:
        chains = json.load(f)
    with open(os.path.join(outdir, "ochains.json"),
              encoding="utf-8") as f:
        ochains = json.load(f)
    inv = {}
    for o, tags in ochains.items():
        for t in tags["minimal"] + tags["standard"]:
            if t not in inv:
                inv[t] = load(invdir, t)
    failed = 0
    for o in chains:
        ot = ochains[o]
        omin, _, _ = build_flat({t: inv[t] for t in ot["minimal"]},
                                ot["minimal"])
        both = {t: inv[t] for t in ot["standard"]}
        onorm, _, _ = build_flat(both, ot["standard"])
        nmin = stack(layers, chains[o]["minimal"])
        nnorm = stack(layers, chains[o]["normal"])
        for name, a, b in (("minimal", omin, nmin),
                           ("normal", onorm, nnorm)):
            only_o = sorted(set(a) - set(b))
            only_n = sorted(set(b) - set(a))
            diffs = [p for p in sorted(set(a) & set(b))
                     if key_of(a[p]) != key_of(b[p])]
            print("%s %s: orig=%d new=%d only-orig=%d only-new=%d "
                  "content-diffs=%d"
                  % (o, name, len(a), len(b),
                     len(only_o), len(only_n), len(diffs)))
            for p in only_o[:25]:
                print("  ONLY-ORIG %s" % p)
            for p in only_n[:25]:
                print("  ONLY-NEW %s" % p)
            for p in diffs[:25]:
                print("  DIFF %s" % p)
                print("    orig: %s" % json.dumps(a[p], sort_keys=True)[:300])
                print("    new : %s" % json.dumps(b[p], sort_keys=True)[:300])
            if only_o or only_n or diffs:
                failed += 1
    # ハードリンクの組は 1 つの層内に全名前そろって在ること。
    split = 0
    for o in chains:
        ot = ochains[o]
        for stage, tags in (("minimal", ot["minimal"]),
                            ("normal", ot["standard"])):
            tag = tags[-1]
            groups = defaultdict(list)
            for line in open(os.path.join(invdir, tag + ".jsonl"),
                             encoding="utf-8"):
                r = json.loads(line)
                if r.get("grp") is not None:
                    groups[r["grp"]].append(r["p"])
            for g, members in sorted(groups.items()):
                tops = set()
                for m in members:
                    top = None
                    for layer in reversed(dot_order(chains[o][stage])):
                        if m in layers.get(layer, {}):
                            top = layer
                            break
                    tops.add(top)
                if len(tops) > 1 or None in tops:
                    split += 1
                    print("  HL-SPLIT %s %s grp=%s: %s"
                          % (o, stage, g, sorted(tops)))
    print("hardlink-group splits: %d" % split)
    failed += split
    if failed:
        print("VERIFY-STAGES FAILED: %d" % failed)
        return 1
    print("VERIFY-STAGES OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
