#!/usr/bin/env python3
"""実物の層の棚卸しと公式6ビュー・割り当て・ハードリンクを照合する。

使い方: verify_built_stages.py INVDIR PLANDIR BUILTINVDIR REPORT.json
実物はinventory.pyで棚卸しする。grpは展開後のinodeに由来する。
特殊inodeの別名はpfのL行も検査する。既存verify_stages.pyは変更しない。
"""
from collections import defaultdict
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plan import build_flat, key_of
from inventory import unescape_pf
from verify_stages import dot_order, stack


def read_inventory(directory, name):
    with open(Path(directory) / (name + '.jsonl'), encoding='utf-8') as stream:
        return {r['p']: r for r in map(json.loads, stream)}


def compare(a, b):
    return {'only_orig': sorted(a.keys() - b.keys()),
            'only_new': sorted(b.keys() - a.keys()),
            'different': [{'path': p, 'orig': a[p], 'new': b[p]}
                          for p in sorted(a.keys() & b.keys()) if key_of(a[p]) != key_of(b[p])]}


def count(result):
    return sum(len(v) for v in result.values())


def hardlinks(expected, built, origin):
    errors = []
    checked = 0
    for layer, items in expected.items():
        actual = built[layer]
        for p, r in items.items():
            target = r.get('linkto')
            if not target:
                continue
            checked += 1
            a, b = actual.get(p, {}), actual.get(target, {})
            if r['t'] == 'f':
                ok = (a.get('grp') is not None and a.get('grp') == b.get('grp')
                      and a.get('nlink', 0) >= 2 and b.get('nlink', 0) >= 2)
            else:
                # macOSではデバイスは展開せずpfを一次記録にする。
                ok = a.get('linkto') == target
            if not ok:
                errors.append({'layer': layer, 'path': p, 'target': target,
                               'reason': 'inode group or pseudo hardlink differs'})
    # 組の過不足も比較する。内容が同じでも独立inodeのファイルは結合しない。
    exact_groups_checked = 0
    for layer, items in expected.items():
        expected_groups = defaultdict(set)
        for p, r in items.items():
            if r['t'] != 'f' or not r.get('linkto'):
                continue
            target = r['linkto']
            seen = {p}
            while items[target].get('linkto'):
                if target in seen:
                    raise ValueError(f'cyclic hardlink: {layer}/{p}')
                seen.add(target)
                target = items[target]['linkto']
            expected_groups[target].update((p, target))
        actual_groups = defaultdict(set)
        for p, r in built[layer].items():
            if r['t'] == 'f' and r.get('grp') is not None:
                actual_groups[r['grp']].add(p)
        wanted = {frozenset(v) for v in expected_groups.values()}
        actual = {frozenset(v) for v in actual_groups.values()}
        exact_groups_checked += len(wanted)
        for reason, groups in (('missing inode group', wanted - actual),
                               ('unexpected inode group', actual - wanted)):
            for group in groups:
                errors.append({'layer': layer, 'reason': reason, 'members': sorted(group)})
    # 公式のinodeグループの全名前が、実物でも同じ層・同じinodeに在ること。
    groups_checked = 0
    for osname, views in origin['chains'].items():
        for view, tags in (('minimal', origin['ochains'][osname]['minimal']),
                           ('normal', origin['ochains'][osname]['standard'])):
            grouped = defaultdict(list)
            for r in origin['inventories'][tags[-1]].values():
                if r.get('grp') is not None:
                    grouped[r['grp']].append(r['p'])
            for members in grouped.values():
                groups_checked += 1
                tops = []
                for p in members:
                    top = next((name for name in reversed(dot_order(views[view])) if p in built[name]), None)
                    rec = built[top].get(p, {}) if top else {}
                    tops.append((top, rec.get('grp')))
                if len(set(tops)) != 1 or tops[0][0] is None or tops[0][1] is None:
                    errors.append({'os': osname, 'view': view, 'members': members, 'tops': tops})
    return {'link_edges_checked': checked, 'official_groups_checked': groups_checked, 'exact_layer_groups_checked': exact_groups_checked, 'errors': errors}


def main(argv):
    if len(argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    invdir, plandir, builtdir, reportpath = argv
    plandir = Path(plandir)
    expected = json.loads((plandir / 'layers.json').read_text())
    chains = json.loads((plandir / 'chains.json').read_text())
    ochains = json.loads((plandir / 'ochains.json').read_text())
    tags = {t for spec in ochains.values() for names in spec.values() for t in names}
    official = {t: read_inventory(invdir, t) for t in tags}
    built = {layer: read_inventory(builtdir, layer) for layer in expected}
    report = {'layers': {}, 'views': {}}
    for layer, items in expected.items():
        result = compare(items, built[layer])
        report['layers'][layer] = result
        print(f"LAYER {layer}: planned={len(items)} built={len(built[layer])} differences={count(result)}")
    for osname, views in chains.items():
        for view, names in views.items():
            tags = ochains[osname]['minimal' if view == 'minimal' else 'standard']
            orig, _, _ = build_flat({t: {p: (t, r) for p, r in official[t].items()} for t in tags}, tags)
            actual = stack(built, names)
            result = compare(orig, actual)
            report['views'][osname + '/' + view] = result
            print(f"VIEW {osname}/{view}: orig={len(orig)} built={len(actual)} differences={count(result)}")
    report['capabilities'] = {}
    for kind, layers in (('official', official), ('built', built)):
        lengths = defaultdict(int)
        for records in layers.values():
            for r in records.values():
                value = r.get('x', {}).get('security.capability')
                if value is not None:
                    if not value.startswith('0t'):
                        raise ValueError(f'unsupported capability encoding: {value!r}')
                    lengths[len(unescape_pf(value[2:]))] += 1
        report['capabilities'][kind] = dict(lengths)
    print('CAPABILITY BYTE LENGTHS ' + json.dumps(report['capabilities']))
    report['hardlinks'] = hardlinks(expected, built, {'chains': chains, 'ochains': ochains, 'inventories': official})
    errors = sum(count(r) for r in report['layers'].values()) + sum(count(r) for r in report['views'].values()) + len(report['hardlinks']['errors'])
    report['differences'] = errors
    Path(reportpath).write_text(json.dumps(report, indent=2, ensure_ascii=True) + '\n')
    print('HARDLINKS ' + json.dumps(report['hardlinks']))
    print(f"VERIFY-BUILT-STAGES {'OK' if not errors else 'FAILED'}: differences={errors}")
    return int(bool(errors))


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
