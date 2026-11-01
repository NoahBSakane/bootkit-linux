#!/usr/bin/env python3
"""user-data10 の生成: user-data9 の late-commands に一括除去を足す。

使い方:
  python3 -I tools/offline-install/make-bulk-user-data.py BASE_USERDATA LIST_TXT OUT_USERDATA

  BASE_USERDATA (user-data9) の head (late-commands より前) を保ち、
  late-commands を組み直す:
    CMD0 casper purge (据え置き)
    CMD1 conf 2 件削除 (据え置き)
    CMD2 installer-only 一覧の一括除去 (新規。seed ISO 内の別ファイル
         installer-only-paths.txt を CIDATA ラベルで mount して読む。
         rm -rf の対象は /target/<パス> のみ。空文字ガード付き)
    CMD3 update-initramfs (旧 CMD2 を番号ずらし)
    CMD4 NOCASPER 確認 + 一覧の残存数報告 (旧 CMD3 を番号ずらし・拡張。
         残存は報告のみで失敗にしない)
    CMD5-7 直接 mask 3 件 (旧 CMD4-6 を番号ずらし)
  各 late-command は echo CMDn_RC=$R の終了記録を付ける。
  casper の purge と update-initramfs・個別の mask は残す (重複して無害)。
"""
import re
import sys

BULK_CMD = """    - sh -c 'dev=$(blkid -L CIDATA | head -n 1); [ -n "$dev" ] || { echo SEED_NOT_FOUND; exit 11; }; mkdir -p /mnt/seedlist; mountpoint -q /mnt/seedlist || mount -o ro "$dev" /mnt/seedlist || { echo SEED_MOUNT_FAIL; exit 12; }; L=/mnt/seedlist/installer-only-paths.txt; [ -f "$L" ] || { echo LIST_MISSING; exit 13; }; n=0; while IFS= read -r p; do case "$p" in ""|\\#*) continue;; esac; t="/target$p"; case "$t" in /target/|/target) echo EMPTY_PATH_SKIP; exit 14;; esac; case "$t" in /target/*) ;; *) echo BAD_PATH_SKIP; exit 15;; esac; rm -rf "$t" || { echo "RM_FAIL $t"; exit 16; }; n=$((n+1)); done <"$L"; R=$?; echo CMD2_PURGE_N=$n CMD2_PURGE_RC=$R; exit $R'"""

VERIFY_CMD = """    - sh -c 'mountpoint -q /mnt/seedlist || { dev=$(blkid -L CIDATA | head -n 1); [ -n "$dev" ] || { echo SEED_NOT_FOUND; exit 21; }; mkdir -p /mnt/seedlist; mount -o ro "$dev" /mnt/seedlist || { echo SEED_MOUNT_FAIL; exit 22; }; }; L=/mnt/seedlist/installer-only-paths.txt; [ -f "$L" ] || { echo LIST_MISSING; exit 23; }; rem=0; remnames=""; while IFS= read -r p; do case "$p" in ""|\\#*) continue;; esac; if [ -e "/target$p" ] || [ -L "/target$p" ]; then rem=$((rem+1)); case "$rem" in [1-9]|1?) remnames="$remnames /target$p";; esac; fi; done <"$L"; echo CMD5_REMAIN=$rem$remnames; echo CMD5_RC=0'"""


def main(argv):
    if len(argv) != 3 or "--help" in argv:
        print(__doc__, file=sys.stderr)
        return 2
    base_path, list_path, out_path = argv
    with open(base_path, encoding="utf-8") as f:
        base = f.read()
    with open(list_path, encoding="utf-8") as f:
        _ = f.read()  # 存在の確認だけ (内容は seed ISO 内の別ファイルで読む)

    head, sep, _ = base.partition("\n  late-commands:\n")
    if not sep:
        raise RuntimeError("late-commands not found in base")
    # 既存の sh -c 一行物だけを抜く (コメント行は落とす。番号は付け直す)。
    cmds = re.findall(r"^    - sh -c '.*'$", base, re.M)
    if len(cmds) != 7:
        raise RuntimeError("expected 7 sh -c lines, got %d" % len(cmds))

    def relabel(cmd, old, new):
        if old not in cmd:
            raise RuntimeError("marker %s not in: %s" % (old, cmd[:80]))
        return cmd.replace(old, new)

    purge = relabel(cmds[0], "CMD0_RC", "CMD0_RC")  # 据え置き
    confdel = relabel(cmds[1], "CMD1_RC", "CMD1_RC")  # 据え置き
    initramfs = relabel(cmds[2], "CMD2_RC", "CMD3_RC")
    nocasper = relabel(cmds[3], "CMD3_RC", "CMD4_RC")
    mask = [relabel(cmds[4], "CMD4_MASK_RC", "CMD6_MASK_RC"),
            relabel(cmds[5], "CMD5_WANTS_RC", "CMD7_WANTS_RC"),
            relabel(cmds[6], "CMD6_VERIFY_RC", "CMD8_VERIFY_RC")]
    # WANTS_GREP_RC は旧 CMD6 行の中にある。そのまま番号は変えない
    # (行内の記録名であり、他と衝突しないため)。
    out = head + "\n  late-commands:\n"
    out += purge + "\n" + confdel + "\n"
    out += BULK_CMD + "\n" + initramfs + "\n"
    out += nocasper + "\n" + VERIFY_CMD + "\n"
    out += "\n".join(mask) + "\n"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(out)
    print("wrote %s (%d bytes, 9 late-commands)" % (out_path, len(out)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
