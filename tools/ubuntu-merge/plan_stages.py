#!/usr/bin/env python3
"""再層化(R1)の割り当てを決める。段1だけを共有し、段2は OS ごとに置く。

入力の棚卸しは設置元の 6 層だけ(d-minimal/d-standard/l-minimal/
l-standard/s-minimal/s-server)。live・installer の層は計算に含めない。

段1 = 各 OS の minimal の層のビュー。段2 = 各 OS の standard の層の内容
(standard が勝つ範囲。公式の層のまま。whiteout も保持)。
共有は段1の中だけで行い、層は次のとおり。
  common … 3 OS の段1で同一(パス・種別・内容・モード・所有者・xattr・
    symlink 先が一致)
  common.dl … Ubuntu・Lubuntu の段1で同一(Server に同名パスが在って
    内容が違う場合を含む。その Server 側は common.server に置く)
  common.dl.snap … Ubuntu の段1と Lubuntu の段2に同一内容で在る snap
    (var/lib/snapd/snaps/*.snap と var/lib/snapd/seed/snaps/*.snap の組。
    組の全名前を 1 つの層に置く)
  common.dl.snap.ubuntu / common.dl.snap.lubuntu … それぞれの段1の残り
  common.server … Server の段1の残り
  common.dl.snap.ubuntu.std / common.dl.snap.lubuntu.std /
    common.server.std … OS ごとの段2(段をまたぐ共有はしない)
Server の snap は共有層を使わず Server 側の層に入れる。
ハードリンク(nlink>1)の組は組の全名前を同じ層に置く。共有できる組
(全員で同じ OS 集合に一致)のときだけ共有層、そうでなければ OS 別の層に
組ごと入れる。デバイスとその peer は同じ層に同居させる。
ディレクトリのメタデータの衝突の解消は plan.py と同じ規則(leaf への
明示追加)を層の木に合わせて行う。

使い方: plan_stages.py INVDIR OUTDIR
  INVDIR の <tag>.jsonl を読み、OUTDIR に
    layers.json … 新層ごとの配置
    chains.json … OS ごとの Minimal / Normal の層の列(下から上へ)
    ochains.json … 公式の連鎖の対応
    report.txt … 数字の報告
  を書く。同一性判定に時刻は使わない。
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from plan import build_flat, key_of  # noqa: E402

MIN_TAG = {"ubuntu": "d-minimal", "lubuntu": "l-minimal",
           "server": "s-minimal"}
STD_TAG = {"ubuntu": "d-standard", "lubuntu": "l-standard",
           "server": "s-server"}
OSNAMES = ["ubuntu", "lubuntu", "server"]
PRIORITY = ["ubuntu", "lubuntu", "server"]

NEW_LAYERS = ["common", "common.dl", "common.dl.snap",
              "common.dl.snap.ubuntu", "common.dl.snap.lubuntu",
              "common.server", "common.dl.snap.ubuntu.std",
              "common.dl.snap.lubuntu.std", "common.server.std"]
LEAF_OF = {"ubuntu": "common.dl.snap.ubuntu",
           "lubuntu": "common.dl.snap.lubuntu",
           "server": "common.server"}


def dot_chain(leaf):
    """層名からドット規則で鎖を導く。leaf の名前をドットで削って
    NEW_LAYERS に在る接頭辞だけを残し、短い順(下から上へ)に並べる。
    casper が leaf から親をたどって重ねる順と同じ。
    """
    parts = leaf.split(".")
    return [".".join(parts[:i]) for i in range(1, len(parts) + 1)
            if ".".join(parts[:i]) in NEW_LAYERS]


CHAINS = {
    "ubuntu": {
        "minimal": dot_chain("common.dl.snap.ubuntu"),
        "normal": dot_chain("common.dl.snap.ubuntu.std"),
    },
    "lubuntu": {
        # Minimal は snap 層を使わない(段1に snap が無い)。snap 層を
        # 除いた順を別に持つ。
        "minimal": [ly for ly in dot_chain("common.dl.snap.lubuntu")
                    if ly != "common.dl.snap"],
        "normal": dot_chain("common.dl.snap.lubuntu.std"),
    },
    "server": {
        "minimal": dot_chain("common.server"),
        "normal": dot_chain("common.server.std"),
    },
}

SNAP_DIRS = ("var/lib/snapd/snaps/", "var/lib/snapd/seed/snaps/")


def load(invdir, tag):
    recs = {}
    with open(os.path.join(invdir, tag + ".jsonl"),
              encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            recs[r["p"]] = (tag, r)
    return recs


def is_snap_file(p, r):
    return (r["t"] == "f" and p.endswith(".snap")
            and p.startswith(SNAP_DIRS))


def main(argv):
    invdir, outdir = argv
    os.makedirs(outdir, exist_ok=True)
    inv = {t: load(invdir, t) for t in
           list(MIN_TAG.values()) + list(STD_TAG.values())}
    s1, s2, wtag2 = {}, {}, {}
    for o in OSNAMES:
        v1, _, _ = build_flat({MIN_TAG[o]: inv[MIN_TAG[o]]}, [MIN_TAG[o]])
        s1[o] = v1
        both = {MIN_TAG[o]: inv[MIN_TAG[o]], STD_TAG[o]: inv[STD_TAG[o]]}
        v2, w2, _ = build_flat(both, [MIN_TAG[o], STD_TAG[o]])
        s2[o] = v2
        wtag2[o] = w2
        print("%s stage1: %d paths stage2view: %d paths"
              % (o, len(v1), len(v2)))

    # snap 共有の組: Ubuntu の段1と Lubuntu の段2に同一内容で在る snap。
    snap_set = set()
    groups_u = {}
    for p, r in s1["ubuntu"].items():
        if r.get("grp") is not None:
            groups_u.setdefault(r["grp"], []).append(p)
    for p, r in s1["ubuntu"].items():
        if not is_snap_file(p, r):
            continue
        if p in snap_set:
            continue
        # Lubuntu の段1に在ると snap 層の共有では段1の再構成が壊れる
        # ため対象外にする。Server の段1に在る分は Server 側の層に残す
        # ので、snap 層との重複を許す。
        if p in s1["lubuntu"]:
            continue
        if p not in s2["lubuntu"]:
            continue
        if key_of(r) != key_of(s2["lubuntu"][p]):
            print("snap key differs, not shared: %s" % p)
            continue
        members = groups_u.get(r.get("grp"), [p]) if r.get("grp") is not None else [p]
        ok = True
        for m in members:
            mr = s1["ubuntu"][m]
            if not is_snap_file(m, mr):
                ok = False
            if m in s1["lubuntu"]:
                ok = False
            if m not in s2["lubuntu"]:
                ok = False
            elif key_of(mr) != key_of(s2["lubuntu"][m]):
                print("snap key differs, not shared: %s" % m)
                ok = False
        if ok:
            snap_set.update(members)
    print("snap-shared paths: %d" % len(snap_set))

    # Server の snap は共有層を使わない(Server 側の層に入れる)。
    server_snap = {p for p, r in s1["server"].items()
                   if is_snap_file(p, r)}

    # 段1の割り当て。
    assign = {}   # (os, path) -> 新層
    counts = {}
    dup_pair = {"ds": 0, "ls": 0, "dl": 0}
    dup_bytes = {"ds": 0, "ls": 0, "dl": 0}
    dev_peer = set()  # (os, path): デバイスへのリンク先。
    for o in OSNAMES:
        for p, r in s1[o].items():
            if r.get("linkto"):
                t = s1[o].get(r["linkto"], {})
                if t.get("t") in ("c", "b"):
                    dev_peer.add((o, p))
                    dev_peer.add((o, r["linkto"]))
    pool = set()
    for o in OSNAMES:
        for p in s1[o]:
            # Server の snap は Server 側の層に残す(snap 層との重複を許す)。
            if o == "server" and p in server_snap:
                assign[("server", p)] = "common.server"
                counts["server-snap"] = counts.get("server-snap", 0) + 1
                continue
            if p in snap_set:
                continue
            pool.add((o, p))
    allpaths = sorted({p for (o, p) in pool})
    for p in allpaths:
        pres = {oo: ((oo, p) in pool) for oo in OSNAMES}
        keys = {oo: key_of(s1[oo][p]) for oo in OSNAMES if pres[oo]}
        kset = set(keys.values())
        nlink_any = any((s1[oo][p].get("grp") is not None
                         or s1[oo][p].get("linkto") is not None
                         or (oo, p) in dev_peer)
                        for oo in keys)
        in_all = all(pres.values()) and len(kset) == 1
        # Ubuntu・Lubuntu が同一なら Server に同名パスが在っても
        # common.dl に入れる。3 OS 同一(下の common 行き)は除く。
        ul = (pres["ubuntu"] and pres["lubuntu"]
              and keys["ubuntu"] == keys["lubuntu"]
              and not (all(pres.values()) and len(kset) == 1))
        if in_all and not nlink_any:
            for oo in keys:
                assign[(oo, p)] = "common"
            counts["C3"] = counts.get("C3", 0) + 1
        elif ul and not nlink_any:
            for oo in ("ubuntu", "lubuntu"):
                assign[(oo, p)] = "common.dl"
            if pres["server"]:
                # Server の別内容は Server 側の層に置く。
                assign[("server", p)] = LEAF_OF["server"]
            counts["Cdl"] = counts.get("Cdl", 0) + 1
        else:
            if (pres["ubuntu"] and pres["server"]
                    and keys.get("ubuntu") == keys.get("server")):
                dup_pair["ds"] += 1
                dup_bytes["ds"] += s1["ubuntu"][p].get("size") or 0
            if (pres["lubuntu"] and pres["server"]
                    and keys.get("lubuntu") == keys.get("server")):
                dup_pair["ls"] += 1
                dup_bytes["ls"] += s1["lubuntu"][p].get("size") or 0
            if (pres["ubuntu"] and pres["lubuntu"]
                    and keys.get("ubuntu") == keys.get("lubuntu")
                    and (pres["server"] or nlink_any)):
                dup_pair["dl"] += 1
                dup_bytes["dl"] += s1["ubuntu"][p].get("size") or 0
            for oo in keys:
                assign[(oo, p)] = LEAF_OF[oo]
                counts["leaf-" + oo] = counts.get("leaf-" + oo, 0) + 1
    # snap 共有層。Ubuntu の段1と Lubuntu の段2の両方から使う。
    for p in snap_set:
        assign[("ubuntu", p)] = "common.dl.snap"
        assign[("lubuntu", p)] = "common.dl.snap"
    counts["snap"] = len(snap_set)
    # デバイスとその peer は同じ層に同居させる。
    for (o, p) in sorted(dev_peer):
        r = s1[o].get(p)
        if not r or not r.get("linkto"):
            continue
        t = r["linkto"]
        if (o, t) not in assign or (o, p) not in assign:
            continue
        if assign[(o, p)] != assign[(o, t)]:
            assign[(o, p)] = assign[(o, t)]
            counts["devpeer-follow"] = counts.get("devpeer-follow", 0) + 1
    # ハードリンクの組は組ごと 1 つの層に。割れたら OS 別の層へ。
    for o in OSNAMES:
        groups = {}
        for p, r in s1[o].items():
            if r.get("grp") is not None and (o, p) in assign:
                groups.setdefault((MIN_TAG[o], r["grp"]), []).append(p)
        for members in groups.values():
            layers = {assign[(o, m)] for m in members}
            if len(layers) > 1:
                for m in members:
                    assign[(o, m)] = LEAF_OF[o]
                counts["hl-forced-" + o] = \
                    counts.get("hl-forced-" + o, 0) + 1
    print("stage1 classes:", json.dumps(counts, sort_keys=True))

    # 段2は OS ごと。standard が勝つ範囲をそのまま置く。段1の帰属は
    # 上書きせず、両方に置く(下は隠れるが見た目の再構成に要る)。
    assign2 = {}
    for o in OSNAMES:
        n = 0
        for p in s2[o]:
            if wtag2[o][p] != STD_TAG[o]:
                continue
            if p in snap_set:
                continue
            assign2[(o, p)] = LEAF_OF[o] + ".std"
            n += 1
        print("%s stage2 paths: %d" % (o, n))

    rec1, rec2 = s1, s2
    members = {layer: {} for layer in NEW_LAYERS}
    for (o, p), layer in assign.items():
        members[layer][(o, p)] = None
    for (o, p), layer in assign2.items():
        members[layer][(o, p)] = None
    # 層ごとの使用 OS と必要 dir。snap 層の lubuntu 側は段2のビューを使う。
    for layer in NEW_LAYERS:
        users = [o for o in PRIORITY
                 if any(k[0] == o for k in members[layer])]
        need_dirs = set()
        for (o, p) in members[layer]:
            view = rec2[o] if (layer == "common.dl.snap" and o == "lubuntu") \
                else (rec2[o] if layer.endswith(".std") else rec1[o])
            parts = p.split("/")[:-1]
            for i in range(1, len(parts) + 1):
                need_dirs.add("/".join(parts[:i]))
        for d in sorted(need_dirs):
            for o in users:
                if (o, d) not in members[layer]:
                    view = rec2[o] if (layer == "common.dl.snap"
                                       and o == "lubuntu") \
                        else (rec2[o] if layer.endswith(".std") else rec1[o])
                    if d in view:
                        members[layer][(o, d)] = None
    stored = {}   # (layer, path) -> {os: record}
    topmost = {}  # (os, path) -> layer
    for o in PRIORITY:
        for layer in reversed(CHAINS[o]["normal"]):
            for (oo, p) in members[layer]:
                if oo != o:
                    continue
                view = rec2[o] if (layer == "common.dl.snap"
                                   and o == "lubuntu") \
                    else (rec2[o] if layer.endswith(".std") else rec1[o])
                stored.setdefault((layer, p), {})[o] = view[p]
                topmost.setdefault((o, p), layer)
    final = {}  # (layer, path) -> record
    extra_leaf = {o: {} for o in PRIORITY}
    for (layer, p), cand in stored.items():
        users = [o for o in PRIORITY if (o, p) in members[layer]]
        req = [o for o in users if topmost.get((o, p)) == layer]
        if not req:
            first = next(o for o in PRIORITY if o in cand)
            final[(layer, p)] = cand[first]
            continue
        first = next(o for o in PRIORITY if o in req)
        final[(layer, p)] = cand[first]
        for o in req:
            if o == first:
                continue
            if key_of(cand[o]) == key_of(cand[first]):
                continue
            extra_leaf[o][p] = cand[o]
    for o, dmap in extra_leaf.items():
        leaf = LEAF_OF[o]
        for p, r in dmap.items():
            final[(leaf, p)] = r
            parts = p.split("/")[:-1]
            for i in range(1, len(parts) + 1):
                a = "/".join(parts[:i])
                if (leaf, a) not in final and a in rec1[o]:
                    final[(leaf, a)] = rec1[o][a]
    # leaf 明示追加でハードリンクの組が割れたら組ごと leaf へ戻す。
    for o in OSNAMES:
        groups = {}
        for p, r in rec1[o].items():
            if r.get("grp") is not None:
                groups.setdefault(r["grp"], []).append(p)
        for members_g in groups.values():
            layers = set()
            for m in members_g:
                for layer in CHAINS[o]["normal"]:
                    if (layer, m) in final:
                        layers.add(layer)
                        break
            if len(layers) > 1:
                top = [ly for ly in CHAINS[o]["normal"]
                       if ly in layers][-1]
                for m in members_g:
                    for layer in list(layers):
                        if (layer, m) in final and layer != top:
                            del final[(layer, m)]
                    if (top, m) not in final and m in rec1[o]:
                        final[(top, m)] = rec1[o][m]
                counts["hl-leaf-repair-" + o] = \
                    counts.get("hl-leaf-repair-" + o, 0) + 1
    print("explicit leaf additions:",
          {o: len(v) for o, v in extra_leaf.items()})
    layers_out = {}
    for layer in NEW_LAYERS:
        items = {}
        for (ly, p), r in final.items():
            if ly != layer:
                continue
            src = {}
            for o in PRIORITY:
                if (o, p) in members[layer]:
                    if layer == "common.dl.snap" and o == "lubuntu":
                        src[o] = STD_TAG[o]
                    elif layer.endswith(".std"):
                        src[o] = STD_TAG[o]
                    else:
                        src[o] = MIN_TAG[o]
            items[p] = {"os": sorted(src), "src": src,
                        "t": r["t"], "mode": r["mode"], "uid": r["uid"],
                        "gid": r["gid"], "mtime": r["mtime"],
                        "size": r.get("size"), "sha256": r.get("sha256"),
                        "target": r.get("target"), "dev": r.get("dev"),
                        "sub": r.get("sub"), "linkto": r.get("linkto"),
                        "x": r.get("x", {})}
        layers_out[layer] = items
        print("%s: %d paths" % (layer, len(items)))

    # 段をまたぐ重複の計測。snap 共有は除く。
    cross = {}
    for o in OSNAMES:
        n = b = 0
        std_layer = LEAF_OF[o] + ".std"
        for p, r in layers_out[std_layer].items():
            if p in snap_set:
                continue
            if p in rec1[o] and key_of(rec1[o][p]) == key_of(r):
                n += 1
                b += r.get("size") or 0
        cross[o] = [n, b]
    print("cross-stage dups (excl snap):",
          json.dumps(cross, sort_keys=True))
    # standard の段での OS 間の重複(段をまたぐ共有をやめることで戻る量)。
    stds = {o: layers_out[LEAF_OF[o] + ".std"] for o in OSNAMES}
    seen = {}
    for o in OSNAMES:
        for p, r in stds[o].items():
            seen.setdefault((p, key_of(r)), []).append(o)
    multi = {k: v for k, v in seen.items() if len(v) > 1}
    std_overlap_paths = sum(len(v) for v in multi.values())
    std_overlap_extra = 0
    for (p, k), v in multi.items():
        size = stds[v[0]][p].get("size") or 0
        std_overlap_extra += size * (len(v) - 1)
    print("std overlap: groups=%d occurrences=%d extra-bytes=%d"
          % (len(multi), std_overlap_paths, std_overlap_extra))

    with open(os.path.join(outdir, "layers.json"), "w") as f:
        json.dump(layers_out, f, indent=1, ensure_ascii=True)
    with open(os.path.join(outdir, "chains.json"), "w") as f:
        json.dump(CHAINS, f, indent=1)
    with open(os.path.join(outdir, "ochains.json"), "w") as f:
        json.dump({o: {"minimal": [MIN_TAG[o]],
                       "standard": [MIN_TAG[o], STD_TAG[o]]}
                   for o in OSNAMES}, f, indent=1)
    with open(os.path.join(outdir, "report.txt"), "w") as f:
        f.write("classes: %s\n" % json.dumps(counts, sort_keys=True))
        f.write("snap_shared_paths: %d\n" % len(snap_set))
        f.write("stage1_pairs: %s\n"
                % json.dumps(dup_pair, sort_keys=True))
        f.write("stage1_pair_bytes: %s\n"
                % json.dumps(dup_bytes, sort_keys=True))
        f.write("cross_stage_dups: %s\n"
                % json.dumps(cross, sort_keys=True))
        f.write("std_overlap_groups: %d\n" % len(multi))
        f.write("std_overlap_occurrences: %d\n" % std_overlap_paths)
        f.write("std_overlap_extra_bytes: %d\n" % std_overlap_extra)
        f.write("explicit_leaf: %s\n"
                % json.dumps({o: len(v) for o, v in extra_leaf.items()},
                             sort_keys=True))
        for layer in NEW_LAYERS:
            nfile = sum(1 for r in layers_out[layer].values()
                        if r["t"] == "f")
            nbyte = sum(r.get("size") or 0
                        for r in layers_out[layer].values()
                        if r["t"] == "f")
            f.write("%s: paths=%d files=%d bytes=%d\n"
                    % (layer, len(layers_out[layer]), nfile, nbyte))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
