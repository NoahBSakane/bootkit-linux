#!/usr/bin/env python3
"""qcow2/raw 内の ext4 を読み取り専用で読む (sudo・macFUSE 不要)。

使い方:
  target-ls.py DISKRAW... (qcow2 可。raw へは各自変換)
  コマンドは stdin の 1 行ずつ: LS <dir> | CAT <file> | STAT <path> |
  FIND <dir> <name-substr> | DU <dir> | QUIT
  出力は 1 件 1 行 (CAT はバイト数を出し続けて生で書く)。

ext4 の extent 木・linear/dir-index 両対応。xattr は読まない。
GPT には対応せず、ディスク像全体を 1MiB 刻みで走査して
ext4 マジック (0x53EF) を探す。見つかった各 FS を番号で選ぶ。
"""
import os
import struct
import sys

BLK = 4096


class FS:
    def __init__(self, fp, base):
        self.fp = fp
        self.base = base
        sb = self.read(self.base + 1024, 1024)
        (self.inodes_count, self.blocks_count, self.r_blocks_count,
         self.free_blocks, self.free_inodes, self.first_data_block,
         self.log_block_size, _log_cluster, self.blocks_per_group,
         _frags, self.inodes_per_group, _mtime, _wtime,
         _mnt, _maxmnt) = struct.unpack('<13I2H', sb[:56])
        self.magic = struct.unpack('<H', sb[56:58])[0]
        assert self.magic == 0xEF53, hex(self.magic)
        self.block_size = 1024 << self.log_block_size
        feat_incompat = struct.unpack('<I', sb[96:100])[0]
        assert feat_incompat & 0x40, "extent flag missing"
        self.desc_size = 64 if (feat_incompat & 0x80) else 32
        ngrp = (self.blocks_count + self.blocks_per_group - 1) \
            // self.blocks_per_group
        gdt = self.read(self.block_off(
            self.first_data_block + 1), ngrp * self.desc_size)
        self.groups = []
        for i in range(ngrp):
            d = gdt[i * self.desc_size:(i + 1) * self.desc_size]
            bbit, ibit, itab = struct.unpack('<3I', d[:12])
            self.groups.append((bbit, ibit, itab))

    def block_off(self, blk):
        return self.base + blk * self.block_size

    def read(self, off, n):
        self.fp.seek(off)
        return self.fp.read(n)

    def inode(self, ino):
        grp = (ino - 1) // self.inodes_per_group
        idx = (ino - 1) % self.inodes_per_group
        _, _, itab = self.groups[grp]
        raw = self.read(self.block_off(itab) + idx * 256, 256)
        mode, uid, size_lo, atime, ctime, mtime, dtime, gid, nlink, \
            blocks_lo, flags, _ver = struct.unpack(
                '<2H5I2H3I', raw[:40])
        size = size_lo | (struct.unpack('<I', raw[108:112])[0] << 32)
        extent = raw[40:100]
        return {"mode": mode, "uid": uid, "gid": gid, "size": size,
                "mtime": mtime, "nlink": nlink, "extent": extent}

    def extents(self, extent):
        magic, entries, _max, depth, _gen = struct.unpack('<5H', extent[:10])
        assert magic == 0xF30A
        out = []
        if depth == 0:
            for i in range(entries):
                e = extent[12 + i * 12:24 + i * 12]
                lblk, ln, start_hi, start_lo = struct.unpack(
                    '<IHHI', e)
                blk = lblk
                out.append((blk, (start_hi << 32) | start_lo, ln))
        else:
            for i in range(entries):
                e = extent[12 + i * 12:24 + i * 12]
                lblk, leaf_lo, leaf_hi, _ = struct.unpack('<IIHH', e)
                leaf = (leaf_hi << 32) | leaf_lo
                hdr = self.read(self.block_off(leaf), 4096)
                out += self.extents(hdr)
        return out

    def data(self, ino):
        st = self.inode(ino)
        if st["mode"] & 0o170000 == 0o120000:
            # symlink: 短い相手は inode 内に直置き。
            if st["size"] < 60:
                return st["extent"][:st["size"]]
        want = st["size"]
        buf = bytearray()
        for _lblk, phys, ln in self.extents(st["extent"]):
            if len(buf) >= want:
                break
            n = min(ln * self.block_size, want - len(buf))
            buf += self.read(self.block_off(phys), n)
        return bytes(buf)

    def listdir(self, ino):
        raw = self.data(ino)
        out = []
        p = 0
        while p + 8 <= len(raw):
            ino_e, reclen, nlen, ftype = struct.unpack(
                '<IHBB', raw[p:p + 8])
            if reclen < 8 or p + reclen > len(raw):
                break
            if ino_e and nlen:
                out.append((raw[p + 8:p + 8 + nlen].decode(
                    'utf-8', 'surrogateescape'), ino_e, ftype))
            p += reclen if reclen else len(raw) - p
        return out

    def resolve(self, path):
        ino = 2
        if path == '/':
            return ino
        for comp in [c for c in path.split('/') if c]:
            hit = None
            for name, child, _ft in self.listdir(ino):
                if name == comp:
                    hit = child
                    break
            if hit is None:
                return None
            ino = hit
        return ino


def scan(fp, size):
    found = []
    off = 0
    while off + 2048 <= size:
        fp.seek(off + 1024 + 56)
        if fp.read(2) == b'\x53\xef':
            found.append(off)
        off += 1 << 20
    return found


def fmt_mode(mode):
    t = mode & 0o170000
    c = {0o040000: 'd', 0o100000: 'f', 0o120000: 'l',
         0o020000: 'c', 0o060000: 'b', 0o010000: 'i',
         0o140000: 's'}.get(t, '?')
    return c


def main(argv):
    disk = argv[0]
    size = os.path.getsize(disk)
    fp = open(disk, 'rb')
    bases = scan(fp, size)
    print("FS: %s" % ["@%d" % b for b in bases])
    if not bases:
        return 1
    fs = FS(fp, bases[0] if len(bases) == 1 else int(argv[1]))
    for line in sys.stdin:
        line = line.rstrip('\n')
        if not line or line == 'QUIT':
            break
        cmd, _, arg = line.partition(' ')
        try:
            if cmd == 'LS':
                ino = fs.resolve(arg or '/')
                if ino is None:
                    print("NOFILE")
                    continue
                for name, child, _ft in fs.listdir(ino):
                    st = fs.inode(child)
                    print("%s %8d %d %s" % (
                        fmt_mode(st["mode"]), st["size"], child, name))
                print("END")
            elif cmd == 'STAT':
                ino = fs.resolve(arg)
                if ino is None:
                    print("NOFILE")
                    continue
                st = fs.inode(ino)
                print("ino=%d mode=%o uid=%d gid=%d size=%d mtime=%d "
                      "nlink=%d" % (ino, st["mode"], st["uid"],
                                    st["gid"], st["size"], st["mtime"],
                                    st["nlink"]))
            elif cmd == 'CAT':
                ino = fs.resolve(arg)
                if ino is None:
                    print("NOFILE")
                    continue
                data = fs.data(ino)
                sys.stdout.write("BYTES %d\n" % len(data))
                sys.stdout.flush()
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.write(b"\nEND\n")
                sys.stdout.flush()
            elif cmd == 'FIND':
                top, _, sub = arg.partition(' ')
                stack = [top or '/']
                n = 0
                while stack and n < 5000:
                    d = stack.pop()
                    ino = fs.resolve(d)
                    if ino is None:
                        continue
                    for name, child, _ft in fs.listdir(ino):
                        if name in ('.', '..'):
                            continue
                        full = d.rstrip('/') + '/' + name
                        st = fs.inode(child)
                        if fmt_mode(st["mode"]) == 'd':
                            stack.append(full)
                        if sub in name:
                            print("%s %d" % (full, st["size"]))
                            n += 1
                print("END")
            elif cmd == 'DU':
                total, count = 0, 0
                stack = [arg or '/']
                while stack:
                    d = stack.pop()
                    ino = fs.resolve(d)
                    if ino is None:
                        continue
                    for name, child, _ft in fs.listdir(ino):
                        if name in ('.', '..'):
                            continue
                        full = d.rstrip('/') + '/' + name
                        st = fs.inode(child)
                        if fmt_mode(st["mode"]) == 'd':
                            stack.append(full)
                        else:
                            total += st["size"]
                            count += 1
                print("bytes=%d files=%d" % (total, count))
            else:
                print("UNKNOWN")
        except Exception as e:  # noqa: BLE001
            print("ERROR %r" % (e,))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
