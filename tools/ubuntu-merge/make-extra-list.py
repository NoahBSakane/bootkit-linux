#!/usr/bin/env python3
"""toram で設置するときに、元の媒体が無くても apt が引けるファイルの一覧を作る。

設置プログラム(Server の subiquity)は、設置先へ GRUB・shim などを `file:/cdrom`
の apt で入れる。toram は層だけを RAM へ写すため、媒体を取り外すと /cdrom/dists と
/cdrom/pool が無く、設置が止まる。この一覧(casper/bootkit-chains/<os>.extra)の
ファイルを、toram の複写が層と一緒に RAM へ写す。

一覧は、(1) dists の索引一式、(2) 設置時に入れる指定パッケージのうち、設置先
(その OS の層の manifest.full)に無いものと、その依存の閉包の deb。
標準ライブラリだけで動く。依存の選択は先頭の候補を使う簡易版で、取りこぼしは
実機の設置で検出する。
"""
import argparse
import re
import sys
from pathlib import Path


def parse_index(path):
    packages = {}
    text = Path(path).read_text(encoding='utf-8', errors='replace')
    for block in text.split('\n\n'):
        fields, key = {}, None
        for line in block.split('\n'):
            if line[:1] in ' \t' and key:
                fields[key] += ' ' + line.strip()
            elif ':' in line:
                key, value = line.split(':', 1)
                fields[key] = value.strip()
        if 'Package' in fields:
            packages.setdefault(fields['Package'], fields)
    return packages


def installed_names(manifest):
    return {line.split()[0].split(':')[0] for line in Path(manifest).read_text().splitlines() if line.strip()}


def closure(index, installed, seeds):
    provides = {}
    for name, fields in index.items():
        for item in re.split(r',\s*', fields.get('Provides', '')):
            item = item.split('(')[0].strip()
            if item:
                provides.setdefault(item, []).append(name)
    need, todo, unresolved = {}, list(seeds), []
    while todo:
        name = todo.pop()
        if name in need or name in installed:
            continue
        if name not in index:
            candidates = provides.get(name, [])
            if any(c in installed for c in candidates):
                continue
            if candidates:
                todo.append(candidates[0])
            else:
                unresolved.append(name)
            continue
        need[name] = index[name]
        deps = index[name].get('Depends', '') + ',' + index[name].get('Pre-Depends', '')
        for dep in re.split(r',\s*', deps):
            if not dep.strip():
                continue
            alts = [a.split('(')[0].split(':')[0].strip() for a in dep.split('|')]
            if any(a in installed or any(c in installed for c in provides.get(a, [])) for a in alts):
                continue
            todo.append(alts[0])
    return need, unresolved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', action='append', required=True, help='Packages(複数可。先のものを優先)')
    parser.add_argument('--manifest', required=True, help='設置先の dpkg 一覧(manifest.full)')
    parser.add_argument('--seed', action='append', required=True, help='設置時に入れる指定パッケージ(複数可)')
    parser.add_argument('--dists-file', action='append', default=[], help='一覧に入れる dists 以下のパス(複数可)')
    parser.add_argument('--root', help='指定すると、一覧の全ファイルがこの下に在ることを検査する')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    index = {}
    for path in args.index:
        for name, fields in parse_index(path).items():
            index.setdefault(name, fields)
    need, unresolved = closure(index, installed_names(args.manifest), args.seed)
    if unresolved:
        sys.exit('解決できない依存: ' + ' '.join(sorted(unresolved)))
    lines = list(args.dists_file) + sorted(f['Filename'] for f in need.values())
    if args.root:
        missing = [line for line in lines if not (Path(args.root) / line).is_file()]
        if missing:
            sys.exit('媒体に無いファイル: ' + ' '.join(missing))
    Path(args.output).write_text('\n'.join(lines) + '\n')
    total = sum(int(f['Size']) for f in need.values())
    print(f'{len(need)} debs, {total} bytes -> {args.output}')


if __name__ == '__main__':
    main()
