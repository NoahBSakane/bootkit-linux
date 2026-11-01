#!/usr/bin/env python3
"""Lubuntu の leaf 層の whiteout (char/block 0,0) のうち、Server 層に
実体がある物を列挙する (NUL 区切りで標準出力へ出す)。

使い方: python3 -I tools/ubuntu-merge/lubuntu-whiteout-rescue.py <iso>
  <iso>: 複製 ISO (読むだけ)。LBAs は xorriso で問い合わせるため、
  追記の有無に依らず動く。標準ライブラリのみ。
"""
import re
import subprocess
import sys


def lba_map(iso):
    out = subprocess.run(
        ['xorriso', '-indev', iso, '-find', '/casper',
         '-name', '*.squashfs', '-exec', 'report_lba', '--'],
        capture_output=True, text=True, check=True)
    table = {}
    for line in out.stdout.split('\n'):
        m = re.search(r"File data lba:\s+\d+\s*,\s*(\d+)\s*,\s*\d+\s*,\s*\d+\s*,\s*'(/casper/\S+)'", line)
        if m:
            table[m.group(2)] = int(m.group(1)) * 2048
    return table


def listing(iso, off):
    out = subprocess.run(
        ['unsquashfs', '-o', str(off), '-ll', iso],
        capture_output=True, text=True, check=True)
    table = {}
    for line in out.stdout.split('\n'):
        if 'squashfs-root' not in line:
            continue
        path = '/' + line.split('squashfs-root', 1)[1].strip().lstrip('/')
        path = re.sub(r'\s+->\s+.*$', '', path)
        if path != '/':
            table[path] = line[0]
    return table


def main():
    iso = sys.argv[1]
    lbas = lba_map(iso)
    leaf = '/casper/common.dl.lubuntu.squashfs'
    server = '/casper/common.server.squashfs'
    lubuntu = listing(iso, lbas[leaf])
    real = listing(iso, lbas[server])
    rescue = sorted(
        path for path, typ in lubuntu.items()
        if typ in 'bc' and path in real and real[path] not in 'bc')
    missing = sorted(
        path for path, typ in lubuntu.items()
        if typ in 'bc' and path not in rescue)
    sys.stdout.write('\0'.join(p.lstrip('/') for p in rescue))
    sys.stderr.write(f'rescue={len(rescue)} missing={len(missing)}\n')
    for path in missing:
        sys.stderr.write(f'missing: {path}\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
