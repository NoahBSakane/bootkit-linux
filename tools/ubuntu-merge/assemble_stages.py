#!/usr/bin/env python3
"""公式3ISOとR2aの9層からR2bを新規作成し、静的検証する。通信・VM起動なし。"""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import threading
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE / 'tools/ubuntu-merge'))
from stages_layout import INSTALL, CHAINS, write_chains, validate, validate_grub, lba_records

SRC = Path('/Users/nbs/Downloads/ubuntu-merge-research-20261029')
WORK = HERE / 'build/work/r2b'
ROOT = WORK / 'iso-root'
LOGS = HERE / 'build/work/logs'
OUT = HERE / 'build/ubuntu-merge-26.04.1-amd64-relayer.iso'
ISO = {'ubuntu': 'ubuntu-26.04.1-desktop-amd64.iso',
       'lubuntu': 'lubuntu-26.04.1-desktop-amd64.iso',
       'server': 'ubuntu-26.04.1-live-server-amd64.iso'}
LIVE = (
    ('ubuntu', 'minimal.standard.live', 'common.dl.snap.ubuntu.std.live', 793112576),
    ('lubuntu', 'minimal.standard.live', 'common.dl.snap.lubuntu.std.live', 28471296),
    ('server', 'ubuntu-server-minimal.ubuntu-server.installer', 'common.server.std.live', 27041792),
    ('server', 'ubuntu-server-minimal.ubuntu-server.installer.generic', 'common.server.std.live.generic', 98304),
)
APT_LAYERS = ('common.dl.snap.ubuntu.apt.squashfs',
              'common.dl.snap.ubuntu.std.apt.squashfs')
UBUNTU_LAYERS = (*APT_LAYERS, 'common.dl.snap.ubuntu.std.live.kernel.squashfs')
CONFIG_LAYERS = (*UBUNTU_LAYERS, 'common.dl.snap.lubuntu.std.live.install.squashfs')
lock = threading.Lock()


def space():
    free = shutil.disk_usage(HERE).free
    with lock, (LOGS / 'r2b-space.jsonl').open('a') as f:
        f.write(json.dumps({'time': time.time(), 'free_bytes': free}) + '\n')
    if free < 18 * 1024 ** 3:
        raise RuntimeError(f'free space below 18GiB: {free}')
    return free


def run(cmd, name='assemble', capture=False):
    space()
    print(time.strftime('%H:%M:%S'), name, ' '.join(map(str, cmd)), flush=True)
    with (LOGS / ('r2b-' + name + '.log')).open('ab') as log:
        # capture対象は小さな一覧だけ。長い処理の出力は直接ログへ。
        p = subprocess.Popen(list(map(str, cmd)), stdout=subprocess.PIPE if capture else log, stderr=log)
        if capture:
            data, _ = p.communicate()
            log.write(data)
        else:
            try:
                while p.poll() is None:
                    space()
                    time.sleep(1)
            except BaseException:
                p.terminate()
                try:
                    p.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait()
                raise
        if p.returncode:
            raise RuntimeError(f'{name}: exit={p.returncode}; see log')
    return data.decode() if capture else None


def sha(path, kind='sha256'):
    h = hashlib.new(kind)
    with path.open('rb') as f:
        while data := f.read(8 << 20):
            h.update(data)
            space()
    return h.hexdigest()


def extract(osname, source, dest, name='extract'):
    dest.parent.mkdir(parents=True, exist_ok=True)
    run(['xorriso', '-indev', SRC / ISO[osname], '-osirrox', 'on',
         '-overwrite', 'on', '-extract', source, dest], name)


def writable(path):
    for root, dirs, files in os.walk(path):
        Path(root).chmod(0o755)
        for name in files:
            p = Path(root) / name
            if not p.is_symlink():
                p.chmod(p.stat().st_mode | 0o200)


def manifest(path):
    return {str(p.relative_to(path)): sha(p) for p in sorted(path.rglob('*'))
            if p.is_file() and not p.is_symlink()}


def dump(name, data):
    (LOGS / ('r2b-' + name + '.json')).write_text(json.dumps(data, indent=2) + '\n')


def main():
    assert Path.cwd().resolve() == HERE
    LOGS.mkdir(parents=True, exist_ok=True)
    if OUT.exists() or WORK.exists():
        raise RuntimeError('output/work already exists; inspect before retry')
    if space() < 32 * 1024 ** 3:
        raise RuntimeError('need 32GiB initially, retaining 18GiB throughout')
    WORK.mkdir()
    for sub in ('casper', 'boot/grub', 'EFI', '.disk'):
        (ROOT / sub).mkdir(parents=True, exist_ok=True)
    expected = {}
    for sums in SRC.glob('SHA256SUMS.*'):
        for line in sums.read_text().splitlines():
            digest, name = line.split(maxsplit=1)
            expected[name.lstrip('*')] = digest
    def check_iso(osname):
        name = ISO[osname]
        actual = sha(SRC / name)
        assert actual == expected[name], (name, actual)
        extract(osname, '/md5sum.txt', WORK / (osname + '-md5sum.txt'), 'input-' + osname)
        return {'os': osname, 'iso': name, 'sha256': actual}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        inputs = list(pool.map(check_iso, ISO))
    dump('inputs', inputs)
    r2a = {}
    for line in (LOGS / 'r2a-SHA256SUMS.layers').read_text().splitlines():
        digest, name = line.split(maxsplit=1)
        r2a[Path(name).name] = digest
    hashes = {}
    for layer in INSTALL:
        src = HERE / 'build/layers-stages' / (layer + '.squashfs')
        digest = sha(src)
        assert digest == r2a[src.name], src
        dest = ROOT / 'casper' / src.name
        os.link(src, dest)
        hashes[src.name] = digest
    live_evidence = []
    for osname, member, layer, size in LIVE:
        dest = ROOT / 'casper' / (layer + '.squashfs')
        extract(osname, '/casper/' + member + '.squashfs', dest, 'live')
        assert dest.stat().st_size == size, dest
        md5s = {}
        for line in (WORK / (osname + '-md5sum.txt')).read_text().splitlines():
            digest, path = line.split(maxsplit=1)
            md5s[path.lstrip('*').removeprefix('./')] = digest
        md5 = sha(dest, 'md5')
        assert md5 == md5s['casper/' + member + '.squashfs']
        hashes[dest.name] = sha(dest)
        live_evidence.append({'os': osname, 'source': member + '.squashfs',
                              'destination': dest.name, 'bytes': size,
                              'official_md5': md5, 'sha256': hashes[dest.name]})
    dump('live', live_evidence)
    for osname in ISO:
        extract(osname, '/casper/initrd', ROOT / 'casper' / ('initrd.' + osname), 'boot')
        extract(osname, '/.disk/casper-uuid-generic', ROOT / '.disk' / ('casper-uuid-' + osname), 'boot')
        dest = ROOT / 'casper/bootkit-meta' / {'ubuntu': 'desktop'}.get(osname, osname)
        run(['python3', '-I', HERE / 'tools/ubuntu-merge/stage-meta.py', SRC / ISO[osname], dest], 'meta')
    extract('ubuntu', '/casper/vmlinuz', ROOT / 'casper/vmlinuz', 'boot')
    extract('ubuntu', '/boot', ROOT / 'boot', 'boot')
    extract('ubuntu', '/EFI', ROOT / 'EFI', 'boot')
    writable(ROOT / 'boot')
    writable(ROOT / 'EFI')
    report = run(['xorriso', '-indev', SRC / ISO['ubuntu'], '-report_el_torito', 'plain'], 'official-boot', True)
    efi = re.search(r'El Torito boot img\s*:\s*2\s+UEFI\s+y\s+none\s+\S+\s+\S+\s+(\d+)\s+(\d+)', report)
    assert efi, report
    sectors512, lba = map(int, efi.groups())
    with (SRC / ISO['ubuntu']).open('rb') as f:
        mbr = f.read(432)
        f.seek(lba * 2048)
        image = f.read(sectors512 * 512)
    assert image[510:512] == b'\x55\xaa' and image[0] in (0xEB, 0xE9)
    (WORK / 'mbr.bin').write_bytes(mbr)
    (ROOT / 'boot/grub/efi.img').write_bytes(image)
    grub = run(['python3', '-I', HERE / 'tools/ubuntu-merge/grub_stages.py'], 'grub', True)
    validate_grub(grub)
    (ROOT / 'boot/grub/grub.cfg').write_text(grub)
    run(['python3', '-I', HERE / 'ventoy/ramsel/make-cpio.py', ROOT / 'casper/bootkit-ramsel.cpio.gz'], 'cpio')
    (ROOT / '.disk/info').write_text('Ubuntu Merge 26.04.1 LTS "Resolute Raccoon" - Release amd64 (20260826)\n')
    for name in ('base_installable', 'cd_type'):
        shutil.copyfile(ROOT / 'casper/bootkit-meta/desktop/disk' / name, ROOT / '.disk' / name)
    write_chains(ROOT / 'casper')
    catalog = ROOT / 'casper/install-sources.yaml'
    shutil.copyfile(HERE / 'tools/offline-install/install-sources-relayer.yaml', catalog)
    finish(hashes)


def finish(hashes):
    catalog = ROOT / 'casper/install-sources.yaml'
    layer = ROOT / 'casper/common.dl.snap.lubuntu.std.live.install.squashfs'
    run(['sh', HERE / 'tools/ubuntu-merge/build-lubuntu-stages.sh', SRC / ISO['lubuntu'],
         WORK / 'install', HERE / 'tools/offline-install/lubuntu-unpackfs-stages.conf', layer], 'install')
    hashes[layer.name] = sha(layer)
    run(['sh', HERE / 'tools/ubuntu-merge/build-ubuntu-apt-stages.sh', ROOT,
         WORK / 'ubuntu-apt'], 'ubuntu-apt')
    for name in UBUNTU_LAYERS:
        hashes[name] = sha(ROOT / 'casper' / name)
    totals = validate(ROOT / 'casper', catalog)
    dump('chains', totals)
    dump('expected-layers', hashes)
    for osname in ISO:
        extract(osname, '/pool', ROOT / 'pool', 'pool-' + osname)
        writable(ROOT / 'pool')
    extract('server', '/dists', ROOT / 'dists', 'dists')
    # toram の設置で、元の媒体を外した後も apt が引くファイルの一覧(OSごと)。
    # 設置先の層(manifest.full)に無い GRUB・shim などとその依存、dists の索引、
    # Ubuntu は設置用の apt 層(casper/ 直下)も入れる。
    extra_sources = {
        'server': ('server/casper/ubuntu-server-minimal.manifest.full', ()),
        'ubuntu': ('desktop/casper/minimal.manifest.full',
                   ('casper/common.dl.snap.ubuntu.std.apt.squashfs',
                    'casper/common.dl.snap.ubuntu.apt.squashfs')),
        'lubuntu': ('lubuntu/casper/minimal.manifest.full', ()),
    }
    for osname, (manifest, literals) in extra_sources.items():
        run(['python3', '-I', HERE / 'tools/ubuntu-merge/make-extra-list.py',
             '--index', ROOT / 'dists/resolute/main/binary-amd64/Packages',
             '--index', ROOT / 'dists/resolute/restricted/binary-amd64/Packages',
             '--manifest', ROOT / 'casper/bootkit-meta' / manifest,
             '--seed', 'efibootmgr', '--seed', 'grub-efi-amd64', '--seed', 'grub-efi-amd64-signed',
             '--seed', 'shim-signed',
             *(arg for literal in literals for arg in ('--literal', literal)),
             *(arg for name in ('Release', 'Release.gpg', 'main/binary-amd64/Packages',
                                'main/binary-amd64/Packages.gz', 'restricted/binary-amd64/Packages',
                                'restricted/binary-amd64/Packages.gz')
               for arg in ('--dists-file', 'dists/resolute/' + name)),
             '--root', ROOT, '--output', ROOT / 'casper/bootkit-chains' / (osname + '.extra')],
            'extra-list-' + osname)
    # 同一パスのdebも公式のいずれかに由来することをmd5原本で検査。
    pool_md5 = {}
    for osname in ISO:
        for line in (WORK / (osname + '-md5sum.txt')).read_text().splitlines():
            digest, path = line.split(maxsplit=1)
            path = path.lstrip('*').removeprefix('./')
            if path.startswith('pool/'):
                pool_md5.setdefault(path, set()).add(digest)
    assert {str(p.relative_to(ROOT)) for p in (ROOT / 'pool').rglob('*') if p.is_file()} == set(pool_md5)
    for path, digests in pool_md5.items():
        assert sha(ROOT / path, 'md5') in digests, path
    dump('pool', {'files': len(pool_md5), 'bytes': sum((ROOT / p).stat().st_size for p in pool_md5),
                  'conflicting_paths': {p: sorted(d) for p, d in pool_md5.items() if len(d) > 1}})
    dump('pool-md5', {p: sorted(v) for p, v in pool_md5.items()})
    dump('dists-links', {str(p.relative_to(ROOT / 'dists')): p.readlink().as_posix()
                         for p in (ROOT / 'dists').rglob('*') if p.is_symlink()})
    dists = manifest(ROOT / 'dists')
    dump('dists', dists)
    boot_hashes = {}
    for prefix in ('boot', 'EFI', '.disk'):
        boot_hashes.update({f'/{prefix}/{p}': h for p, h in manifest(ROOT / prefix).items()})
    for name in ('vmlinuz', 'initrd.ubuntu', 'initrd.lubuntu', 'initrd.server', 'bootkit-ramsel.cpio.gz'):
        boot_hashes['/casper/' + name] = sha(ROOT / 'casper' / name)
    dump('boot-hashes', boot_hashes)
    # 読取専用の抽出モードをISO全体の-rで正規化。優先度は大きいほど前。
    cmd = ['xorriso', '-as', 'mkisofs', '-o', OUT, '-V', 'Ubuntu-Merge 26.04.1 amd64',
           '-r', '-J', '-joliet-long', '-l', '-iso-level', '3', '-partition_offset', '16',
           '-c', 'boot.catalog', '-b', 'boot/grub/i386-pc/eltorito.img', '-no-emul-boot',
           '-boot-load-size', '4', '-boot-info-table', '--grub2-boot-info', '-eltorito-alt-boot',
           '-e', 'boot/grub/efi.img', '-no-emul-boot', '--grub2-mbr', WORK / 'mbr.bin',
           '-isohybrid-gpt-basdat', ROOT, '--', '-find', '/', '-type', 'f', '-exec', 'sort_weight', '0', '--']
    for path in ('/boot', '/EFI', '/.disk', '/casper/vmlinuz', '/casper/initrd.ubuntu',
                 '/casper/initrd.lubuntu', '/casper/initrd.server', '/casper/bootkit-ramsel.cpio.gz',
                 '/casper/bootkit-chains', '/casper/bootkit-meta', '/casper/install-sources.yaml',
                 *('/casper/' + name for name in CONFIG_LAYERS)):
        cmd += ['-find', path, '-type', 'f', '-exec', 'sort_weight', '100', '--']
    cmd += ['-commit']
    run(cmd, 'mkisofs')
    run(['python3', '-I', HERE / 'tools/ubuntu-merge/fix-pvd.py', OUT], 'pvd')
    verify(hashes, boot_hashes, dists, totals)
    # 入力は保持し、今回作成したstagingだけを検証成功後に消す。
    cleanup = {'path': str(WORK.relative_to(HERE)), 'iso': str(OUT.relative_to(HERE))}
    writable(WORK)
    shutil.rmtree(WORK)
    dump('cleanup', cleanup)
    print('R2B STATIC PASS', flush=True)


def verify_priority(records, hashes):
    """小さな設定層を含む優先ファイルが、大きな層より前にあることを調べる。"""
    large_start = min(records['/casper/' + name]['lba'] for name in hashes
                      if name not in CONFIG_LAYERS)
    priority = [path for path in records if path.startswith(('/boot/', '/EFI/', '/.disk/', '/casper/bootkit-'))
                or path.startswith('/casper/initrd.') or path in ('/casper/vmlinuz', '/casper/install-sources.yaml')
                or path.removeprefix('/casper/') in CONFIG_LAYERS]
    for path in priority:
        row = records[path]
        assert row['lba'] + row['blocks'] <= large_start, (path, row, large_start)
    return large_start, priority


def verify(hashes, boot_hashes, dists, totals):
    layout_text = run(['xorriso', '-indev', OUT, '-find', '/', '-type', 'f', '-exec', 'report_lba', '--'], 'lba', True)
    records = lba_records(layout_text)
    dump('lba', records)
    rt = WORK / 'roundtrip'
    rt.mkdir()
    checks = {}
    for name, expected in hashes.items():
        dest = rt / name
        run(['xorriso', '-indev', OUT, '-osirrox', 'on', '-extract', '/casper/' + name, dest], 'roundtrip')
        actual = sha(dest)
        assert actual == expected, name
        checks[name] = {'bytes': dest.stat().st_size, 'sha256': actual}
        dest.unlink()
    dump('roundtrip', checks)
    verify_pool(records)
    # メタデータはISOから実際に取り出して解釈する。
    for path in ('/casper/bootkit-chains', '/casper/install-sources.yaml', '/boot/grub/grub.cfg', '/.disk', '/dists'):
        dest = rt / path.lstrip('/')
        dest.parent.mkdir(parents=True, exist_ok=True)
        run(['xorriso', '-indev', OUT, '-osirrox', 'on', '-extract', path, dest], 'roundtrip-meta')
    casper = rt / 'casper'
    # 層本体は再抽出ハッシュ照合済み。カタログ検査用は疎ファイルでサイズを表す。
    for name, row in checks.items():
        with (casper / name).open('wb') as f:
            f.truncate(row['bytes'])
    assert validate(casper, casper / 'install-sources.yaml') == totals
    validate_grub((rt / 'boot/grub/grub.cfg').read_text())
    assert manifest(rt / 'dists') == dists
    links = {str(p.relative_to(rt / 'dists')): p.readlink().as_posix()
             for p in (rt / 'dists').rglob('*') if p.is_symlink()}
    assert links == json.loads((LOGS / 'r2b-dists-links.json').read_text())
    assert (rt / '.disk/info').read_bytes() == (ROOT / '.disk/info').read_bytes()
    for osname in ISO:
        assert (rt / '.disk' / ('casper-uuid-' + osname)).read_bytes() == (WORK / 'iso-root/.disk' / ('casper-uuid-' + osname)).read_bytes()
    # LBA範囲のバイト照合はboot-info-tableを書き換えるBIOSイメージを除く。
    boot_checks = {}
    with OUT.open('rb') as f:
        for path, digest in boot_hashes.items():
            row = records[path]
            f.seek(row['lba'] * 2048)
            data = f.read(row['bytes'])
            if path == '/boot/grub/i386-pc/eltorito.img':
                original = (ROOT / path.lstrip('/')).read_bytes()
                assert data[:8] == original[:8] and data[64:2548] == original[64:2548] and data[2556:] == original[2556:]
                assert struct.unpack_from('<Q', data, 2548)[0] == row['lba'] * 4 + 5
                assert struct.unpack_from('<I', data, 8)[0] == 16
                assert struct.unpack_from('<I', data, 12)[0] == row['lba']
                assert struct.unpack_from('<I', data, 16)[0] == row['bytes']
                payload = data[64:]
                payload += b'\0' * (-len(payload) % 4)
                assert sum(struct.unpack('<' + 'I' * (len(payload) // 4), payload)) % (1 << 32) == struct.unpack_from('<I', data, 20)[0]
                boot_checks[path] = 'boot-info-table and GRUB2 pointer/checksum valid; remainder identical'
            else:
                assert hashlib.sha256(data).hexdigest() == digest, path
                boot_checks[path] = digest
    dump('boot-roundtrip', boot_checks)
    large_start, priority = verify_priority(records, hashes)
    report = run(['xorriso', '-indev', OUT, '-report_el_torito', 'plain', '-report_system_area', 'plain'], 'iso-structure', True)
    assert re.search(r'El Torito boot img\s*:\s*1\s+BIOS\s+y', report)
    assert re.search(r'El Torito boot img\s*:\s*2\s+UEFI\s+y', report)
    assert 'El Torito cat path : /boot.catalog' in report
    with OUT.open('rb') as f:
        f.seek(16 * 2048)
        pvd = f.read(2048)
        f.seek(32 * 2048)
        second = f.read(2048)
    with OUT.open('rb') as f:
        mbr = f.read(512)
    bios_lba = records['/boot/grub/i386-pc/eltorito.img']['lba']
    assert mbr[510:512] == b'\x55\xaa'
    assert struct.unpack_from('<Q', mbr, 432)[0] == bios_lba * 4 + 4
    dump('grub-pointers', {'bios_lba': bios_lba, 'mbr_pointer': bios_lba * 4 + 4,
                            'core_pointer': bios_lba * 4 + 5, 'checksum': 'PASS'})
    assert pvd[:7] == second[:7] == b'\x01CD001\x01'
    sectors = struct.unpack_from('<I', pvd, 80)[0]
    assert sectors == struct.unpack_from('>I', pvd, 84)[0]
    secondary = struct.unpack_from('<I', second, 80)[0]
    assert secondary == struct.unpack_from('>I', second, 84)[0]
    assert sectors == secondary + 16
    assert sectors * 2048 == OUT.stat().st_size, (sectors * 2048, OUT.stat().st_size)
    assert pvd[40:72].rstrip(b' ') == b'Ubuntu-Merge 26.04.1 amd64'
    match = re.search(r'El Torito catalog\s*:\s*(\d+)\s+(\d+)', report)
    assert match and int(match[2]) == 1
    catalog_lba = int(match[1])
    with OUT.open('rb') as f:
        f.seek(catalog_lba * 2048)
        boot_catalog = f.read(2048)
    assert boot_catalog[0] == 1 and boot_catalog[30:32] == b'\x55\xaa'
    assert sum(struct.unpack('<16H', boot_catalog[:32])) % 65536 == 0
    assert boot_catalog[32] == 0x88
    dump('boot-catalog', {'lba': catalog_lba, 'bytes': len(boot_catalog),
                          'validation_checksum': 'PASS', 'bios_bootable': True})
    run(['xorriso', '-indev', OUT, '-find', '/casper', '-exec', 'lsdl', '--'], 'casper-list')
    summary = {'static': 'PASS', 'iso': str(OUT.relative_to(HERE)), 'bytes': OUT.stat().st_size,
               'difference_from_current': OUT.stat().st_size - 9655549952,
               'sha256': sha(OUT), 'layers_verified': len(hashes), 'chains': totals,
               'pvd_sectors': sectors, 'first_large_layer_lba': large_start,
               'priority_files': len(priority), 'boot_files_verified': len(boot_checks)}
    dump('verification', summary)
    print(json.dumps(summary, indent=2), flush=True)


def verify_pool(records=None):
    """poolの全358ファイルをISOの実データ範囲で公式MD5と照合する。"""
    if records is None:
        records = json.loads((LOGS / 'r2b-lba.json').read_text())
    expected = json.loads((LOGS / 'r2b-pool-md5.json').read_text())
    assert {p for p in records if p.startswith('/pool/')} == {'/' + p for p in expected}
    results = {}
    with OUT.open('rb') as f:
        for path, digests in expected.items():
            row = records['/' + path]
            f.seek(row['lba'] * 2048)
            remaining = row['bytes']
            md5, sha256 = hashlib.md5(), hashlib.sha256()
            while remaining:
                data = f.read(min(8 << 20, remaining))
                assert data
                remaining -= len(data)
                md5.update(data)
                sha256.update(data)
                space()
            assert md5.hexdigest() in digests, path
            results[path] = {'bytes': row['bytes'], 'md5': md5.hexdigest(),
                             'sha256': sha256.hexdigest()}
    dump('pool-roundtrip', results)
    print('POOL ROUNDTRIP PASS', len(results), flush=True)


if __name__ == '__main__':
    main()
