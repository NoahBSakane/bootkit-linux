#!/usr/bin/env python3
"""実ISOを使わない、R2bのGRUB・連鎖・カタログの合成試験。"""
import importlib.util
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE / 'tools/ubuntu-merge'))
from stages_layout import CHAINS, validate, validate_grub, write_chains, read_catalog


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / 'tools/ubuntu-merge' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    work = Path(sys.argv[1])
    work.mkdir()
    sizes = {
        'common': 1138008064, 'common.dl': 393572352, 'common.dl.snap': 1303564288,
        'common.dl.snap.ubuntu': 597102592, 'common.dl.snap.ubuntu.std': 590053376,
        'common.dl.snap.lubuntu': 506413056, 'common.dl.snap.lubuntu.std': 387616768,
        'common.server': 197103616, 'common.server.std': 156299264,
        'common.dl.snap.ubuntu.std.live': 793112576,
        'common.dl.snap.lubuntu.std.live': 28471296,
        'common.dl.snap.lubuntu.std.live.install': 4096,
        'common.server.std.live': 27041792, 'common.server.std.live.generic': 98304,
    }
    for name, size in sizes.items():
        with (work / (name + '.squashfs')).open('wb') as f:
            f.truncate(size)
    write_chains(work)
    catalog = HERE / 'tools/offline-install/install-sources-relayer.yaml'
    totals = validate(work, catalog)
    assert totals['ubuntu']['bytes'] == 4815413248
    assert totals['lubuntu']['bytes'] == 3757649920
    assert totals['server']['bytes'] == 1518551040
    assert read_catalog(catalog)['sources'][1]['default'] is True
    text = load('grub_stages').config()
    validate_grub(text)
    # 元の生成器の9個のlinux/initrd行と、leaf以外の全体も一致する。
    old = load('grub').config()
    for source, target in (
        ('common.dl.ubuntu.squashfs', CHAINS['ubuntu'][-1] + '.squashfs'),
        ('common.dl.lubuntu.squashfs', CHAINS['lubuntu'][-1] + '.squashfs'),
        ('common.server.squashfs', CHAINS['server'][-1] + '.squashfs'),
    ):
        old = old.replace(source, target)
    assert text == old
    unpack = read_catalog(HERE / 'tools/offline-install/lubuntu-unpackfs-stages.conf')['unpack']
    assert [e['source'] for e in unpack] == ['/cdrom/casper/' + x + '.squashfs' for x in CHAINS['lubuntu'][:5]]
    assert [e['condition'] for e in unpack] == [True, True, 'installation_data.unpack_regular', True, 'installation_data.unpack_regular']
    assert all(e['sourcefs'] == 'squashfs' and e['destination'] == '' for e in unpack)
    # 流用部分は原文そのものを保持し、蘇生とxattr補正は入らない。
    old = (HERE / 'tools/ubuntu-merge/add-lubuntu-install-layer.sh').read_text()
    body = old[old.index('# bootloader の deb と efibootmgr'):old.index('# xattr 補正 11 パス:')]
    helper = (HERE / 'tools/ubuntu-merge/build-lubuntu-stages.sh').read_text()
    body = body.replace('pool/main/g/grub2/grub2-common_2.14-2ubuntu2.1_amd64.deb\n', '').replace('assert len(pool) == 6,', 'assert len(pool) == 5,')
    body = '# grub2-commonのdebは公式Lubuntu ISOに無いため含めない。既設の依存として扱う。\n' + body
    assert body in helper
    # 設定層は live 専用(標的へ展開されない)ので、bootloader 準備は
    # dontChroot で標的の root を受け取り、live の repo を一時 bind して標的の chroot で apt を動かす。
    assert 'dontChroot: true' in helper
    assert 'command: sh /etc/calamares/bootrepo-apt.sh ${ROOT}' in helper
    assert 'mount --bind /pool "$R/pool"' in helper and 'chroot "$R" apt-get' in helper
    assert 'lubuntu-whiteout-rescue.py' not in helper and 'lubuntu-xfix-official.json' not in helper
    print('PASS: R2b GRUB, chains, YAML catalogs, unpack conditions, bootrepo reuse')


if __name__ == '__main__':
    main()
