#!/usr/bin/env python3
"""Ubuntu の設置用 APT 設定層と live 専用 kernel 設定層を合成入力で照合する。"""
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from inventory import pf_metadata

HERE = Path(__file__).resolve().parents[2]
SOURCE_PATH = 'etc/apt/sources.list.d/cdrom.sources'
LAYERS = ('common.dl.snap.ubuntu.apt.squashfs',
          'common.dl.snap.ubuntu.std.apt.squashfs')
KERNEL_LAYER = 'common.dl.snap.ubuntu.std.live.kernel.squashfs'
KERNEL_PATH = 'etc/subiquity/kernel-meta-package'
KERNEL_CONTENT = b'linux-generic-hwe-24.04\n'


def run(args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    work = Path(sys.argv[1]).resolve()
    work.mkdir()
    source = work / 'source'
    config = source / SOURCE_PATH
    config.parent.mkdir(parents=True)
    # 鍵の暗号検証ではなく、取り出すファイルとバイトの保持を調べる合成入力。
    content = b'Types: deb\nURIs: file:/cdrom\nSuites: resolute\nComponents: main\nSigned-By: /synthetic/server-key.gpg\n'
    config.write_bytes(content)
    (source / 'unrelated').write_text('not part of the configuration layer\n')
    config.chmod(0o600)
    for directory in (source, *config.parents):
        if directory == work:
            break
        directory.chmod(0o700)
    pseudo = work / 'source.pseudo'
    pseudo.write_text(SOURCE_PATH + ' x user.note=synthetic attribute\n')
    original = work / 'server.squashfs'
    run(['mksquashfs', source, original, '-comp', 'xz', '-b', '131072',
         '-force-uid', '123', '-force-gid', '456', '-all-time', '1000',
         '-mkfs-time', '1000', '-pf', pseudo, '-noappend', '-no-progress', '-processors', '2'])
    original_hash = digest(original)
    before, _ = pf_metadata(original)
    assert before[SOURCE_PATH]['mode'] == 0o600
    assert before[SOURCE_PATH]['uid'] == 123 and before[SOURCE_PATH]['gid'] == 456
    assert before[SOURCE_PATH]['mtime'] == 1000
    assert before[SOURCE_PATH]['x']['user.note'] == 'synthetic attribute'
    print('CONTROL: source mode=600, uid=123, gid=456, time=1000, xattr present', flush=True)
    digests = {name: [] for name in (*LAYERS, KERNEL_LAYER)}
    for index, mask in enumerate((0o077, 0o022)):
        root = work / ('run' + str(index))
        casper = root / 'casper'
        casper.mkdir(parents=True)
        server = casper / 'common.server.squashfs'
        shutil.copyfile(original, server)
        run(['sh', HERE / 'tools/ubuntu-merge/build-ubuntu-apt-stages.sh', root,
             root / 'extracted'], umask=mask)
        assert digest(server) == original_hash
        for name in digests:
            path, expected = (KERNEL_PATH, KERNEL_CONTENT) if name == KERNEL_LAYER else (SOURCE_PATH, content)
            layer = casper / name
            assert layer.stat().st_size == 4096
            assert run(['unsquashfs', '-cat', layer, path], capture_output=True).stdout == expected
            records, meta = pf_metadata(layer)
            assert set(records) == {path, *(str(parent) for parent in Path(path).parents if str(parent) != '.')}
            for entry, record in records.items():
                assert record['t'] == ('f' if entry == path else 'd')
                assert record['mode'] == (0o644 if entry == path else 0o755)
                assert record['uid'] == record['gid'] == record['mtime'] == 0
                assert not record.get('x')
            assert meta.splitlines()[0] == b'/ D 0 755 0 0'
            digests[name].append(digest(layer))
    assert digest(original) == original_hash
    assert all(len(set(values)) == 1 for values in digests.values()), digests
    assert digests[LAYERS[0]] == digests[LAYERS[1]]
    print('PASS: Ubuntu APT/kernel layers: content, paths, root ownership, modes, zero times, no xattrs, 4096 bytes each')
    print('PASS: identical APT leaves and repeated generation with umask 077 / 022: ' + digests[LAYERS[0]][0])
    print('PASS: repeated live kernel layer generation with umask 077 / 022: ' + digests[KERNEL_LAYER][0])


if __name__ == '__main__':
    main()
