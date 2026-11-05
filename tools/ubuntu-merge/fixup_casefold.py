#!/usr/bin/env python3
"""macOS の case-insensitive FS 上での棚卸し補正。

unsquashfs で展開した stage は大文字小文字の違いだけの別パスが衝突
するため、inventory.py の出力(jsonl)に欠け・誤りが出る。pf(正・大文字
小文字を区別)を権威とし、次の規則で jsonl と stats を書き直す。

- pf に在るのに jsonl に無いパス: 種別ごとに合成する。通常ファイルは
  `unsquashfs -cat` で実バイトを取り直す(sha256/size)。dir・symlink・
  デバイス等は pf のメタデータから合成する。ハードリンクの片割れ
  (pf の linkto 行)は inventory.py と同じ形にする。
- jsonl に在るのに pf に無いパス: 大文字小文字を丸めた一致で pf の真
  のパスへ付け替える。一意に定まらない衝突組は捨て、全員を上の規則
  で作り直す(通常ファイルは全員 -cat で取り直す。生き残りの内容は
  上書き敗者の物の可能性があるため)。
- 衝突組の構成員がハードリンク(linkto の所有・対象)に関わる場合は、
  推測で割り当てず exit 2 で打ち切る。

使い方: fixup_casefold.py SQUASHFS TAG INVDIR
  INVDIR/<TAG>.jsonl と INVDIR/<TAG>.stats を書き直す。
"""

import hashlib
import json
import os
import subprocess
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from inventory import pf_metadata  # noqa: E402


def cat_bytes(sqfs, path):
    p = subprocess.run(["unsquashfs", "-cat", sqfs, "/" + path],
                       capture_output=True)
    if p.returncode != 0:
        raise RuntimeError("cat failed for %s: %s"
                           % (path, p.stderr[:200]))
    return p.stdout


def entry_of(p, m, r):
    # inventory.py と同じ項目組み立て。m は pf(正)、r は実体側。
    entry = {
        "p": p,
        "t": m.get("t", r.get("t")),
        "mode": m.get("mode"),
        "uid": m.get("uid"),
        "gid": m.get("gid"),
        "mtime": m.get("mtime"),
        "size": r.get("size"),
        "sha256": r.get("sha256"),
        "target": m.get("target", r.get("target")),
        "dev": m.get("dev"),
        "nlink": r.get("nlink", 1),
        "grp": r.get("grp"),
        "x": m.get("x", {}),
    }
    if "linkto" in m:
        entry["linkto"] = m["linkto"]
    if "sub" in m:
        entry["sub"] = m["sub"]
    return entry


def main(argv):
    sqfs, tag, invdir = argv
    pf, _ = pf_metadata(sqfs)
    link_targets = {m["linkto"] for m in pf.values() if "linkto" in m}
    with open(os.path.join(invdir, tag + ".jsonl"),
              encoding="utf-8") as f:
        disk = {}
        for line in f:
            r = json.loads(line)
            disk[r["p"]] = r
    if len(disk) < len(pf) * 0.99:
        print("FATAL: jsonl too small (%d < %d); rerun inventory.py"
              % (len(disk), len(pf)))
        return 2
    fold = {}
    for p in pf:
        fold.setdefault(p.lower(), []).append(p)
    multi = {k: v for k, v in fold.items() if len(v) > 1}
    # 衝突組とハードリンクの絡みは推測しない。
    for k, members in multi.items():
        for p in members:
            if "linkto" in pf[p] or p in link_targets:
                print("FATAL: collision member in hardlink: %s" % p)
                return 2
    fixed = dict(disk)
    ncat = 0
    # jsonl 側の余分(大文字小文字違いのキー)を真のパスへ付け替える。
    for j in list(fixed):
        if j in pf:
            continue
        cands = fold.get(j.lower(), [])
        if len(cands) == 1 and cands[0] not in fixed:
            p = cands[0]
            fixed[p] = entry_of(p, pf[p], fixed.pop(j))
        elif not cands:
            print("FATAL: jsonl path matches no pf path: %r" % j)
            return 2
        else:
            del fixed[j]  # 衝突組: 下で全員作り直す。
    # 欠けの合成と衝突組の取り直し。
    for p, m in pf.items():
        if p in fixed and p.lower() not in multi:
            continue
        if p in fixed and (m.get("t") != "f" or "linkto" in m):
            continue
        if "linkto" in m:
            r = {"p": p, "t": "l", "nlink": 2}
        elif m.get("t") in ("c", "b", "i", "s"):
            r = {"p": p, "t": m["t"], "nlink": 1}
        elif m.get("t") == "d":
            kids = [q for q in pf
                    if os.path.dirname(q) == p and pf[q].get("t") == "d"]
            r = {"p": p, "t": "d", "nlink": 2 + len(kids)}
        elif m.get("t") == "l":
            r = {"p": p, "t": "l", "nlink": 1,
                 "target": m.get("target")}
        elif m.get("t") == "f":
            data = cat_bytes(sqfs, p)
            ncat += 1
            r = {"p": p, "t": "f", "size": len(data),
                 "sha256": hashlib.sha256(data).hexdigest(),
                 "nlink": 1, "grp": None}
        else:
            print("FATAL: unknown pf record %r: %r" % (p, m))
            return 2
        fixed[p] = entry_of(p, m, r)
    missing = sorted(set(pf) - set(fixed))
    extra = sorted(set(fixed) - set(pf))
    if missing or extra:
        print("FATAL: still missing=%d extra=%d" % (len(missing), len(extra)))
        for p in missing[:10]:
            print("  MISSING %s" % p)
        for p in extra[:10]:
            print("  EXTRA %s" % p)
        return 1
    odd = sum(1 for rel in fixed
              if any(ord(c) > 127 or c in ('"', "'", "\\", "\n", " ")
                     for c in rel))
    grps = {}
    for rel, r in fixed.items():
        if r.get("t") == "f" and r.get("grp") is not None:
            grps.setdefault(r["grp"], []).append(rel)
    stats = {"paths": len(fixed), "pf_entries": len(pf),
             "odd_names": odd,
             "hardlink_groups": len(grps),
             "hardlinked_paths": sum(len(v) for v in grps.values()),
             "missing_meta": []}
    if any(v.get("mode") is None for v in fixed.values()):
        bad = sorted(p for p, v in fixed.items() if v.get("mode") is None)
        print("FATAL: missing metadata for: %s" % bad[:10])
        return 1
    with open(os.path.join(invdir, tag + ".jsonl"), "w",
              encoding="utf-8") as f:
        for rel in sorted(fixed):
            f.write(json.dumps(fixed[rel], ensure_ascii=True) + "\n")
    with open(os.path.join(invdir, tag + ".stats"), "w") as f:
        json.dump(stats, f, indent=1)
    print("%s: fixed=%d cat=%d collisions=%d (%d paths)"
          % (tag, len(fixed), ncat, len(multi), sum(len(v) for v in multi.values())))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
