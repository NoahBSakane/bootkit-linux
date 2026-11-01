#!/usr/bin/env python3
"""xfix の検証: 連鎖+xfix の可視 xattr が公式と全件一致すること。

使い方: python3 -I tools/ubuntu-merge/xfix-verify.py
  build/work/xfix/ の xfix 3 層を読み (ISO からは読まない)、
  xfix-audit.py と同じ可視規則で公式ビューと突き合わせる。
  結果は build/evidence/install-sources/xfix/verify.log。
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(HERE, "tools", "ubuntu-merge"))
from inventory import pf_metadata  # noqa: E402

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


def main():
    log = open(os.path.join(EVID, "verify.log"), "w", encoding="utf-8")

    def msg(s):
        print(s, flush=True)
        log.write(s + "\n")
        log.flush()

    int_xa = {}
    for f in os.listdir(EVID):
        if f.startswith("integrated-") and f.endswith(".json"):
            int_xa[f[len("integrated-"):-len(".json")]] = json.load(
                open(os.path.join(EVID, f), encoding="utf-8"))
    # フルパス集合は audit 時の層順から復元できないため、xfix の寄与だけ
    # 直接見る: xfix が持つパスは公式値を持つはず。
    official = {o: json.load(open(os.path.join(EVID, "official-%s.json" % o),
                                 encoding="utf-8")) for o in OSLIST}
    mm = json.load(open(os.path.join(EVID, "mismatch.json"),
                        encoding="utf-8"))
    rc = 0
    for osname in OSLIST:
        rec, _ = pf_metadata(os.path.join(WORK, LEAF[osname]))
        xa = {p: dict(m.get("x") or {}) for p, m in rec.items()}
        paths = set(rec)
        n_checked, n_bad = 0, 0
        for m in mm:
            if m["os"] != osname:
                continue
            p = m["path"]
            if p not in paths:
                msg("NG %s: %s missing in xfix" % (osname, p))
                rc = 1
                continue
            n_checked += 1
            # xfix が最上層になるので可視値は xfix の値になる。
            # 公式の可視値と比べる (公式 JSON は可視の非空値のみ)。
            want = official[osname].get(p, {})
            got = xa.get(p, {})
            if got != want:
                msg("NG %s: %s got=%r want=%r"
                    % (osname, p, got, want))
                n_bad += 1
                rc = 1
        msg("%s: xfix holds %d paths (%d files fixed checked), "
            "mismatch=%d" % (osname, len(paths), n_checked, n_bad))
        # xfix に余計な xattr (公式に無い名) がないこと。
        for p, x in xa.items():
            w = official[osname].get(p, {})
            for xn in x:
                if xn not in w:
                    msg("NG %s: %s extra xattr %s" % (osname, p, xn))
                    rc = 1
    msg("RESULT: %s" % ("ALL MATCH" if rc == 0 else "MISMATCH LEFT"))
    log.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
