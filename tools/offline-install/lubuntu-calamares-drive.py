#!/usr/bin/env python3
"""稼働中の install1 QEMU に接続し、プロンプトを突破して Calamares を起動する。

方針: カーソルを角へ寄せて原点を確定し、Install ボタン候補へ
mouse_move + click する。当たりは serial の pgrep で判定する。
Try に当たった場合はデスクトップから手動で calamares を起動する。
QEMU は残して終了する。標準ライブラリのみ。
"""
import argparse
import hashlib
import json
import re
import socket
import sys
import time
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', type=Path, required=True)
    parser.add_argument('--timeout', type=float, default=1800)
    parser.add_argument('--user', default='ubuntu')
    parser.add_argument('--password', default='ubuntu')
    args = parser.parse_args()
    args.prefix = args.prefix.absolute()
    return args


def clean_terminal(value):
    value = re.sub(r'\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)', '', value)
    value = re.sub(r'\x1bP.*?\x1b\\', '', value, flags=re.DOTALL)
    value = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', value)
    return value.replace('\r\n', '\n').replace('\r', '\n')


def main():
    args = parse_args()
    prefix = args.prefix
    monitor_path = prefix.parent / (prefix.name + '.mon')
    serial_path = prefix.parent / (prefix.name + '.ser')
    transcript_path = Path(str(prefix) + '.transcript.txt')
    lines = []
    if transcript_path.is_file():
        lines.append(transcript_path.read_text(encoding='utf-8'))

    def note(line):
        lines.append(line + '\n')

    deadline = time.monotonic() + args.timeout
    monitor = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    monitor.settimeout(30)
    monitor.connect(str(monitor_path))
    data = b''
    end = time.monotonic() + 30
    while not data.endswith(b'(qemu) '):
        if time.monotonic() >= end:
            raise RuntimeError('モニター応答なし')
        try:
            data += monitor.recv(65536)
        except socket.timeout:
            continue

    def hmp(command, label):
        monitor.sendall((command + '\n').encode())
        if command == 'quit':
            return ''
        data = b''
        end = time.monotonic() + 30
        while not data.endswith(b'(qemu) '):
            if time.monotonic() >= deadline:
                raise TimeoutError('期限切れ')
            try:
                part = monitor.recv(65536)
            except socket.timeout:
                continue
            if not part:
                raise RuntimeError('モニター切断')
            data += part
        result = data.decode('utf-8', errors='replace')
        note(f'[hmp] {label}: {command}')
        if re.search(r'(?im)^(?:error:|unknown command|invalid parameter|Could not|Error )', result):
            raise RuntimeError(f'HMP 異常: {result.strip()[-300:]}')
        return result

    def shot(name):
        path = Path(str(prefix) + f'-{name}.png')
        hmp(f'screendump {json.dumps(str(path))} -f png', f'撮影 {name}')
        note(f'[指紋] {name}: sha256={hashlib.sha256(path.read_bytes()).hexdigest()} size={path.stat().st_size}')

    serial = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    serial.settimeout(0.5)
    serial.connect(str(serial_path))
    serial_file = open(str(prefix) + '.serial2.log', 'wb')
    buffer = b''

    def drain(timeout):
        nonlocal buffer
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                part = serial.recv(65536)
            except socket.timeout:
                continue
            if not part:
                break
            serial_file.write(part)
            serial_file.flush()
            buffer += part

    def expect(needle, timeout, label):
        mark = needle.encode() if isinstance(needle, str) else needle
        end = time.monotonic() + timeout
        while True:
            if mark in buffer:
                note(f'[serial] {label}: 検出')
                return
            if time.monotonic() >= deadline:
                raise TimeoutError('期限切れ')
            if time.monotonic() >= end:
                raise TimeoutError(f'{label}: 待ち切れず')
            drain(0.5)

    def sendline(line, label):
        serial.sendall((line + '\n').encode())
        note(f'[host] {label}: {line}')
        time.sleep(0.5)

    def run(command_text, marker, timeout, label):
        nonlocal buffer
        buffer = b''
        sendline(command_text, label)
        end = time.monotonic() + timeout
        while ('\n' + marker + '\n') not in ('\n' + clean_terminal(buffer.decode('utf-8', errors='replace'))):
            if time.monotonic() >= deadline:
                raise TimeoutError('期限切れ')
            if time.monotonic() >= end:
                raise TimeoutError(label + ': 完了行なし')
            drain(0.5)
        note(f'[serial] {label}: 完了行 {marker}')
        return clean_terminal(buffer.decode('utf-8', errors='replace'))

    try:
        drain(2)
        sendline('', '改行')
        drain(2)
        if b'login:' in buffer[-4000:]:
            expect(b'login:', 120, 'ログイン待ち')
            sendline(args.user, 'ユーザー名')
            try:
                expect(b'Password:', 20, 'パスワード待ち')
                sendline(args.password, 'パスワード')
            except TimeoutError:
                note('[serial] パスワード不要で進行')
        else:
            note('[serial] 既存の shell を再利用する')
        run('echo SER_OK', 'SER_OK', 120, '応答確認')
        shot('drive-start')
        # 候補 (Install ボタン付近。原点は画面左上へ寄せて確定する)。
        targets = [(960, 460), (900, 460), (1020, 460), (960, 430), (960, 490)]
        launched = False
        for i, (mx, my) in enumerate(targets, 1):
            hmp('sendkey esc', f'esc {i}')
            time.sleep(1)
            hmp('mouse_move -2000 -2000', f'原点寄せ {i}a')
            time.sleep(1)
            hmp('mouse_move -2000 -2000', f'原点寄せ {i}b')
            time.sleep(1)
            hmp(f'mouse_move {mx} {my}', f'照準 {i} ({mx},{my})')
            time.sleep(2)
            shot(f'drive-aim-{i}')
            hmp('mouse_button 1', f'押下 {i}')
            time.sleep(1)
            hmp('mouse_button 0', f'解放 {i}')
            time.sleep(15)
            shot(f'drive-after-{i}')
            out = run('pgrep -af "[c]alamares|lxqt-session" | head -5; echo PGREP_DONE',
                      'PGREP_DONE', 120, f'稼働確認 {i}')
            note(f'[serial] pgrep {i}:\n' + out)
            if re.search(r'(?m)calamares', out):
                note(f'[判定] Install に命中 ({i})')
                launched = True
                break
            if re.search(r'(?m)lxqt-session', out):
                note(f'[判定] Try に命中 ({i}): デスクトップから起動する')
                run('for i in $(seq 1 60); do pgrep -x lxqt-session >/dev/null && break; sleep 5; done; echo LXQT_DONE',
                    'LXQT_DONE', 400, 'LXQt 待ち')
                time.sleep(20)
                shot('drive-lxqt')
                run('sudo DISPLAY=:0 XAUTHORITY=/home/ubuntu/.Xauthority nohup calamares --debug >/tmp/calamares.log 2>&1 & echo CAL_OK',
                    'CAL_OK', 120, 'calamares 手動起動')
                time.sleep(20)
                out = run('pgrep -af "[c]alamares" | head; echo PGREP2_DONE', 'PGREP2_DONE', 120, '手動起動確認')
                note('[serial] pgrep2:\n' + out)
                if re.search(r'(?m)calamares', out):
                    launched = True
                    break
        if not launched:
            raise RuntimeError('プロンプトを突破できなかった')
        time.sleep(10)
        shot('drive-calamares')
        note('[判定] drive 完了 (QEMU は残す)')
        return 0
    except (OSError, RuntimeError, TimeoutError, ValueError) as error:
        note(f'[異常] {error}')
        print(f'エラー: {error}', file=sys.stderr)
        return 1
    finally:
        try:
            monitor.close()
        except OSError:
            pass
        try:
            serial.close()
            serial_file.close()
        except OSError:
            pass
        with transcript_path.open('w', encoding='utf-8') as stream:
            stream.write(''.join(lines))


if __name__ == '__main__':
    sys.exit(main())
