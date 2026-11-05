#!/usr/bin/env python3
"""R2aの小さな実物層による回帰試験。作業領域は呼出し側が指定する。"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inventory import main as inventory
from repack_stages import main as repack, check_case_sensitive
from plan import key_of
from verify_built_stages import main as verify_built


def run(args):
    subprocess.run(list(map(str, args)), check=True)


def main(argv):
    base, work = map(Path, argv)
    check_case_sensitive(base)
    work.mkdir(parents=True)
    excluded = work / "exclude.list"
    excluded.write_text("whiteout\nwhiteout-peer\n")
    with tempfile.TemporaryDirectory(prefix='r2a-synthetic-', dir=base) as tmp:
        tmp = Path(tmp)
        src = tmp / 'src'
        src.mkdir()
        (src / 'Sys').mkdir()
        (src / 'sys').mkdir()
        (src / 'Sys' / 'item').write_text('upper\n')
        (src / 'sys' / 'item').write_text('lower\n')
        (src / 'first').write_text('linked\n')
        os.link(src / 'first', src / 'second')
        (src / 'independent1').write_text('same content\n')
        (src / 'independent2').write_text('same content\n')
        os.symlink('Sys/item', src / 'alias')
        pseudo = work / 'source.pseudo'
        pseudo.write_text('whiteout C 1000 0 0 0 0 0\nwhiteout-peer L whiteout\nfirst x user.note=hello world\n'
                          + r'first x security.capability=0t\001\000\000\002\000 \000\000\000\000\000\000\000\000\000\000\000\000\000\000' + '\n')
        orig = work / 'orig'
        orig.mkdir()
        sqfs = orig / 'd-minimal.squashfs'
        run(['mksquashfs', src, sqfs, '-comp', 'xz', '-b', '131072', '-no-progress', '-processors', '2', '-pf', pseudo,
             '-force-uid', '0', '-force-gid', '0', '-xattrs-exclude', '^com\\.apple\\.'])
        stage = tmp / 'original'
        run(['unsquashfs', '-no-xattrs', '-no-progress', '-processors', '2', '-d', stage, '-exclude-file', excluded, sqfs])
        assert inventory([str(sqfs), 'd-minimal', str(work / 'inv'), str(stage)]) == 0
        records = {r['p']: r for r in map(json.loads, (work / 'inv/d-minimal.jsonl').read_text().splitlines())}
        # 既知の2条件は内容が別で、リンク組は同じinodeである。
        assert records['Sys/item']['sha256'] != records['sys/item']['sha256']
        assert records['first']['grp'] == records['second']['grp'] is not None
        print('CONTROL case paths: distinct hashes; hardlinks: identical inode group', flush=True)
        plan = {}
        for p, r in records.items():
            plan[p] = dict(r, src={'ubuntu': 'd-minimal'}, os=['ubuntu'])
        planpath = work / 'layers.json'
        planpath.write_text(json.dumps({'common': plan}))
        output = work / 'built'
        assert repack([str(planpath), str(orig), str(tmp), str(output)]) == 0
        newstage = tmp / 'new'
        run(['unsquashfs', '-no-xattrs', '-no-progress', '-processors', '2', '-d', newstage,
             '-exclude-file', excluded, output / 'common.squashfs'])
        assert inventory([str(output / 'common.squashfs'), 'common', str(work / 'inv-built'), str(newstage)]) == 0
        new = {r['p']: r for r in map(json.loads, (work / 'inv-built/common.jsonl').read_text().splitlines())}
        assert records.keys() == new.keys()
        assert all(key_of(r) == key_of(new[p]) for p, r in records.items())
        assert new['first']['grp'] == new['second']['grp'] is not None
        assert os.stat(newstage / 'first').st_ino == os.stat(newstage / 'second').st_ino
        assert os.stat(newstage / 'independent1').st_ino != os.stat(newstage / 'independent2').st_ino
        assert new['whiteout']['t'] == 'c' and new['whiteout']['dev'] == [0, 0]
        assert new['whiteout-peer']['linkto'] == 'whiteout'
        assert new['first']['x']['user.note'] == 'hello world'
        plandir = work / 'plan'
        plandir.mkdir()
        (plandir / 'layers.json').write_text(planpath.read_text())
        (plandir / 'chains.json').write_text(json.dumps({'ubuntu': {'minimal': ['common'], 'normal': ['common']}}))
        (plandir / 'ochains.json').write_text(json.dumps({'ubuntu': {'minimal': ['d-minimal'], 'standard': ['d-minimal']}}))
        assert verify_built([str(work / 'inv'), str(plandir), str(work / 'inv-built'), str(work / 'verified.json')]) == 0
        print(f'R2A synthetic OK: {len(new)} paths; differences=0; hardlink inode, whiteout and case paths OK', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
