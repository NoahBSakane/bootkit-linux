"""R2bの連鎖・カタログの整合検査。実ISOと合成試験で共用する。"""
import json
import re
import subprocess

INSTALL = (
    'common', 'common.dl', 'common.dl.snap', 'common.dl.snap.ubuntu',
    'common.dl.snap.ubuntu.std', 'common.dl.snap.lubuntu',
    'common.dl.snap.lubuntu.std', 'common.server', 'common.server.std',
)
CHAINS = {
    'ubuntu': ('common', 'common.dl', 'common.dl.snap', 'common.dl.snap.ubuntu',
               'common.dl.snap.ubuntu.std', 'common.dl.snap.ubuntu.std.live',
               'common.dl.snap.ubuntu.std.live.kernel'),
    'lubuntu': ('common', 'common.dl', 'common.dl.snap', 'common.dl.snap.lubuntu',
                'common.dl.snap.lubuntu.std', 'common.dl.snap.lubuntu.std.live',
                'common.dl.snap.lubuntu.std.live.install'),
    'server': ('common', 'common.server', 'common.server.std',
               'common.server.std.live', 'common.server.std.live.generic'),
}
CATALOG = {
    'ubuntu-server-minimal': ('common.server', 1335111680),
    'ubuntu-server': ('common.server.std', 1491410944),
    'ubuntu-desktop-minimal': ('common.dl.snap.ubuntu.apt', 3432251392),
    'ubuntu-desktop': ('common.dl.snap.ubuntu.std.apt', 4022304768),
}
OFFICIAL_TOTAL = {'ubuntu': 4815302656, 'lubuntu': 3757625344, 'server': 1518555136}


def parents(leaf):
    parts = leaf.removesuffix('.squashfs').split('.')
    return ['.'.join(parts[:n]) + '.squashfs' for n in range(1, len(parts) + 1)]


def write_chains(casper):
    dest = casper / 'bootkit-chains'
    dest.mkdir(parents=True, exist_ok=True)
    for osname, chain in CHAINS.items():
        (dest / (osname + '.list')).write_text(''.join(x + '.squashfs\n' for x in chain))


def read_catalog(path):
    # PyYAMLが無いmacOSでは標準Ruby/PsychでYAML全体を解析する。
    try:
        import yaml
    except ImportError:
        return json.loads(subprocess.check_output([
            'ruby', '-ryaml', '-rjson', '-e',
            'puts JSON.generate(YAML.safe_load(File.read(ARGV[0])))', str(path)], text=True))
    return yaml.safe_load(path.read_text())


def validate(casper, catalog_path):
    catalog = read_catalog(catalog_path)
    assert catalog['version'] == 2
    entries = catalog['sources']
    assert len(entries) == 4
    assert {e['id'] for e in entries} == set(CATALOG)
    assert [e['id'] for e in entries if e.get('default', False)] == ['ubuntu-server']
    for entry in entries:
        leaf, expected = CATALOG[entry['id']]
        assert entry['path'] == leaf + '.squashfs'
        assert entry['type'] == 'fsimage-layered'
        total = sum((casper / p).stat().st_size for p in parents(entry['path']))
        assert total == entry['size'] == expected, (entry['id'], total, entry['size'])
    totals = {}
    for osname, chain in CHAINS.items():
        names = [p + '.squashfs' for p in chain]
        actual = (casper / 'bootkit-chains' / (osname + '.list')).read_text().splitlines()
        assert actual == names == parents(names[-1]), (osname, actual)
        total = sum((casper / p).stat().st_size for p in names)
        assert total * 100 <= OFFICIAL_TOTAL[osname] * 105, (osname, total)
        totals[osname] = {'bytes': total, 'official_bytes': OFFICIAL_TOTAL[osname],
                          'difference': total - OFFICIAL_TOTAL[osname],
                          'percent': (total / OFFICIAL_TOTAL[osname] - 1) * 100}
    return totals


def validate_grub(text):
    linux = [s.strip() for s in text.splitlines() if s.strip().startswith('linux ')]
    initrds = [s.strip() for s in text.splitlines() if s.strip().startswith('initrd ')]
    assert len(linux) == len(initrds) == 9
    for i, (osname, chain) in enumerate(CHAINS.items()):
        for j in range(3):
            line, initrd = linux[i * 3 + j], initrds[i * 3 + j]
            leaf = chain[-1] + '.squashfs'
            extra = ('', ' nomodeset', ' toram')[j]
            quiet = ' quiet splash' if osname != 'server' else ''
            assert line == (f'linux /casper/vmlinuz bootkit.os={osname} '
                            f'layerfs-path={leaf}{extra} ---{quiet} $bootkit_extra')
            archive = ' /casper/bootkit-ramsel.cpio.gz' if j == 2 else ''
            assert initrd == f'initrd /casper/initrd.{osname}{archive}'
    assert text.isascii()


def lba_records(text):
    records = {}
    for line in text.splitlines():
        match = re.match(r"File data lba:\s*0\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*'(.*)'$", line)
        if match:
            lba, blocks, size, path = match.groups()
            records[path] = {'lba': int(lba), 'blocks': int(blocks), 'bytes': int(size)}
    return records
