#!/usr/bin/env python3
"""統合 ISO の 3 OS × 3 項目を生成する (通常・safe graphics・toram)。"""
import os
import sys


# Lubuntu の leaf は既定で土台層に戻す。統合層を追記した ISO だけ、
# 追記スクリプトが BOOTKIT_LUBUNTU_LEAF で統合層の leaf を渡す。
# assemble.sh が素で組む ISO は従来どおり起動できる。
LUBUNTU_LEAF = os.environ.get('BOOTKIT_LUBUNTU_LEAF',
                              'common.dl.lubuntu.squashfs')


def config():
    lines = ['set timeout=30', 'loadfont unicode',
             'set menu_color_normal=white/black',
             'set menu_color_highlight=black/light-gray']
    for osname, title, leaf in (
        ('ubuntu', 'Ubuntu', 'common.dl.ubuntu.squashfs'),
        ('lubuntu', 'Lubuntu', LUBUNTU_LEAF),
        ('server', 'Ubuntu Server', 'common.server.squashfs'),
    ):
        for suffix, extra in (('', ''), (' (safe graphics)', ' nomodeset'),
                              (' (copy to RAM)', ' toram')):
            label = title + suffix if suffix else 'Try or Install ' + title
            archive = ' /casper/bootkit-ramsel.cpio.gz' if extra == ' toram' else ''
            quiet = ' quiet splash' if osname != 'server' else ''
            lines.extend([f'menuentry "{label}" {{', '    set gfxpayload=keep',
                          f'    linux /casper/vmlinuz bootkit.os={osname} layerfs-path={leaf}{extra} ---{quiet} $bootkit_extra',
                          f'    initrd /casper/initrd.{osname}{archive}', '}'])
    lines.extend(['if [ "$grub_platform" = "efi" ]; then',
                  "menuentry 'Boot from next volume' { exit 1; }",
                  "menuentry 'UEFI Firmware Settings' { fwsetup; }", 'fi', ''])
    return '\n'.join(lines)


if __name__ == '__main__':
    sys.stdout.write(config())
