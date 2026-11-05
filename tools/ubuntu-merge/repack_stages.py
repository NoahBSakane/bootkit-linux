#!/usr/bin/env python3
"""段別の layers.json から設置用層を作る。

使い方: repack_stages.py LAYERSJSON ORIGDIR STAGEBASE OUTDIR
STAGEBASE は case-sensitive な作業領域。通常ファイルのリンク組は
共通の抽出元を選んで1回で展開する。特殊 inode は疑似定義で作る。
各層の計測は OUTDIR/build-stats.json に保存する。既存出力は上書きしない。
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inventory import escape_pf

MIN_FREE = 18 * 1024 ** 3


def check_space(path):
    free = shutil.disk_usage(path).free
    if free < MIN_FREE:
        raise RuntimeError(f"free space below 18 GiB: {path}: {free}")
    return free


def run(cmd, space_path):
    """出力は呼び出し元のログへ直接送る。容量制約は処理中も確認する。"""
    print('RUN ' + ' '.join(map(str, cmd)), flush=True)
    with subprocess.Popen(list(map(str, cmd))) as proc:
        try:
            while proc.poll() is None:
                check_space(space_path)
                time.sleep(1)
            if proc.returncode:
                raise RuntimeError(f"command exited {proc.returncode}: {cmd[0]}")
        except BaseException:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            raise


def check_case_sensitive(base):
    with tempfile.TemporaryDirectory(prefix='r2a-case-', dir=base) as tmp:
        upper = Path(tmp) / 'Case'
        upper.write_text('upper')
        lower = Path(tmp) / 'case'
        if lower.exists():
            raise RuntimeError(f"case-sensitive staging required: {base}")
        lower.write_text('lower')
        assert upper.read_text() != lower.read_text()


def validate_path(path):
    p = Path(path)
    if not path or p.is_absolute() or '..' in p.parts or '\n' in path:
        raise ValueError(f"unsafe relative path: {path!r}")


def source_groups(items):
    """リンク辺をまとめ、各組の全名前が存在する同一の抽出元を選ぶ。"""
    parent = {p: p for p in items}

    def find(p):
        while parent[p] != p:
            parent[p] = parent[parent[p]]
            p = parent[p]
        return p

    for p, r in items.items():
        target = r.get('linkto')
        if target:
            if target not in items:
                raise ValueError(f"hardlink outside layer: {p} -> {target}")
            parent[find(p)] = find(target)
    groups = {}
    for p in items:
        groups.setdefault(find(p), []).append(p)
    by_tag = {}
    for members in groups.values():
        candidates = set(items[members[0]]['src'].values())
        for p in members[1:]:
            candidates.intersection_update(items[p]['src'].values())
        if not candidates:
            raise ValueError(f"no common extraction source: {members[:5]}")
        tag = sorted(candidates)[0]
        for p in members:
            r = items[p]
            if r['t'] in ('d', 'c', 'b', 's', 'i'):
                continue
            if r.get('linkto') and items[r['linkto']]['t'] in ('c', 'b', 's', 'i'):
                continue
            by_tag.setdefault(tag, []).append(p)
    return by_tag


def pseudo_lines(items):
    meta, xattrs, special, links = [], [], [], []
    for p, r in sorted(items.items()):
        name = escape_pf(p, True)
        attrs = f"{r['mtime']} {r['mode']:o} {r['uid']} {r['gid']}"
        target = r.get('linkto')
        if target and items[target]['t'] in ('c', 'b', 's', 'i'):
            links.append(f"{name} L {escape_pf(target, False)}")
            continue
        if r['t'] in ('c', 'b'):
            major, minor = r['dev']
            special.append(f"{name} {r['t'].upper()} {attrs} {major} {minor}")
        elif r['t'] in ('s', 'i'):
            special.append(f"{name} I {attrs} {r.get('sub') or ('s' if r['t'] == 's' else 'f')}")
        else:
            meta.append(f"{name} M {attrs}")
        for key, value in sorted((r.get('x') or {}).items()):
            xattrs.append(f"{name} x {key}={value}")
    return meta + special + links + xattrs


def build_layer(layer, items, origdir, stagebase, outdir):
    validate_path(layer)
    if '/' in layer:
        raise ValueError('layer name contains slash')
    for path in items:
        validate_path(path)
    out = outdir / (layer + '.squashfs')
    if out.exists():
        raise FileExistsError(out)
    started = time.monotonic()
    free = check_space(outdir)
    by_tag = source_groups(items)
    pseudo = outdir / (layer + '.pseudo')
    pseudo.write_text('\n'.join(pseudo_lines(items)) + '\n', encoding='utf-8', errors='surrogateescape')
    # TemporaryDirectoryはこの呼出しが作った領域だけを削除する。
    with tempfile.TemporaryDirectory(prefix='r2a-' + layer + '-', dir=stagebase) as tmp:
        stage = Path(tmp) / 'root'
        stage.mkdir()
        for p, r in sorted(items.items()):
            if r['t'] == 'd':
                (stage / p).mkdir(parents=True, exist_ok=True)
        for tag, paths in sorted(by_tag.items()):
            validate_path(tag)
            listing = Path(tmp) / (tag + '.list')
            listing.write_text('\n'.join(sorted(paths)) + '\n', encoding='utf-8', errors='surrogateescape')
            run(['unsquashfs', '-processors', '4', '-no-progress', '-no-xattrs', '-no-wildcards', '-f', '-d', stage,
                 '-extract-file', listing, origdir / (tag + '.squashfs')], outdir)
        run(['mksquashfs', stage, out, '-noappend', '-comp', 'xz', '-b', '131072',
             '-processors', str(min(8, os.cpu_count() or 1)), '-mem', '512M',
             '-force-uid', '0', '-force-gid', '0', '-pseudo-override', '-pf', pseudo,
             '-no-progress', '-xattrs-exclude', '^com\\.apple\\.'], outdir)
    result = {'layer': layer, 'paths': len(items), 'bytes': out.stat().st_size,
              'seconds': round(time.monotonic() - started, 3), 'free_before': free,
              'free_after': check_space(outdir)}
    print('BUILT ' + json.dumps(result), flush=True)
    return result


def main(argv):
    if len(argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    layers_json, origdir, stagebase, outdir = map(Path, argv)
    stagebase.mkdir(parents=True, exist_ok=True)
    outdir.mkdir(parents=True, exist_ok=True)
    check_case_sensitive(stagebase)
    layers = json.loads(layers_json.read_text())
    results = []
    for layer, items in layers.items():
        results.append(build_layer(layer, items, origdir, stagebase, outdir))
        (outdir / 'build-stats.json').write_text(json.dumps(results, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
