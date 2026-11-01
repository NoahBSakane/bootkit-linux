#!/usr/bin/env python3
"""稼働中の QEMU に monitor+serial で接続し、ゲストの現状を読む (起動はしない)。

使い方: python3 -I tools/offline-install/lubuntu-guest-probe.py --prefix build/evidence/lubuntu-install/install1 --shot probe-now
  任意の shell コマンド列を --cmd '...' で複数回指定できる (読むだけが既定)。
  画面も 1 枚撮り、SHA-256 を標準出力へ出す。QEMU は残して終了する。
  標準ライブラリのみ。
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
    parser.add_argument('--shot', default='probe-now')
    parser.add_argument('--timeout', type=float, default=600)
    parser.add_argument('--cmd', action='append', default=[])
    parser.add_argument('--hmp', action='append', default=[])
    parser.add_argument('--sendkey', action='append', default=[])
    parser.add_argument('--mousemove', action='append', default=[])
    parser.add_argument('--click', action='store_true')
    parser.add_argument('--send-file', action='append', default=[],
                        help='host のファイルを guest の /tmp/ へ送る (heredoc)')
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

    def hmp(command):
        monitor.sendall((command + '\n').encode())
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
        return data.decode('utf-8', errors='replace')

    path = Path(str(prefix) + f'-{args.shot}.png')
    hmp(f'screendump {json.dumps(str(path))} -f png')
    print(f'[shot] {path.name}: sha256={hashlib.sha256(path.read_bytes()).hexdigest()} size={path.stat().st_size}')

    serial = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    serial.settimeout(0.5)
    serial.connect(str(serial_path))
    log_file = open(str(prefix) + '.serial3.log', 'ab')
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
            log_file.write(part)
            log_file.flush()
            buffer += part

    def run(command_text, marker, timeout):
        nonlocal buffer
        unique = f'{marker}-{int(time.monotonic() * 100) % 100000:05d}'
        buffer = b''
        serial.sendall((command_text + f'; echo {unique}\n').encode())
        time.sleep(0.5)
        end = time.monotonic() + timeout
        while True:
            cleaned = '\n' + clean_terminal(buffer.decode('utf-8', errors='replace'))
            if ('\n' + unique + '\n') in cleaned or cleaned.rstrip().endswith('\n' + unique):
                break
            if time.monotonic() >= deadline:
                raise TimeoutError('期限切れ')
            if time.monotonic() >= end:
                tail = clean_terminal(buffer.decode('utf-8', errors='replace'))[-800:]
                print(f'[debug] 応答なし({command_text}): 末尾 {tail!r}')
                buffer = b''
                serial.sendall((f'echo {unique}\n').encode())
                time.sleep(0.5)
                end = time.monotonic() + timeout
                while True:
                    cleaned = '\n' + clean_terminal(buffer.decode('utf-8', errors='replace'))
                    if ('\n' + unique + '\n') in cleaned or cleaned.rstrip().endswith('\n' + unique):
                        break
                    if time.monotonic() >= deadline:
                        raise TimeoutError('期限切れ')
                    if time.monotonic() >= end:
                        tail = clean_terminal(buffer.decode('utf-8', errors='replace'))[-800:]
                        print(f'[debug] 再送も応答なし({command_text}): 末尾 {tail!r}')
                        raise TimeoutError(command_text + ': 完了行なし')
                    drain(0.5)
                break
            drain(0.5)
        return clean_terminal(buffer.decode('utf-8', errors='replace'))

    try:
        for command in args.hmp:
            result = hmp(command)
            print(f'[hmp] {command}\n{result.strip()[-500:]}')
        for key in args.sendkey:
            result = hmp(f'sendkey {key}')
            print(f'[sendkey] {key} ok')
            time.sleep(1)
        for coords in args.mousemove:
            hmp(f'mouse_move {coords}')
            print(f'[mousemove] {coords} ok')
            time.sleep(2)
        if args.click:
            hmp('mouse_button 1')
            time.sleep(1)
            hmp('mouse_button 0')
            print('[click] ok')
            time.sleep(3)
        if args.hmp or args.sendkey or args.mousemove or args.click:
            after = Path(str(prefix) + f'-{args.shot}-after.png')
            hmp(f'screendump {json.dumps(str(after))} -f png')
            print(f'[shot-after] {after.name}: sha256={hashlib.sha256(after.read_bytes()).hexdigest()} size={after.stat().st_size}')
        drain(2)
        serial.sendall(b'\n')
        time.sleep(0.5)
        drain(2)
        out = run('echo PROBE_OK', 'PROBE_OK', 120)
        print('[serial] shell 応答あり')
        for source in args.send_file:
            text = Path(source).read_text(encoding='utf-8')
            assert '\nUEOF\n' not in text, f'UEOF を含む: {source}'
            dest = f'/tmp/{Path(source).name}'
            serial.sendall(f"cat > {dest} <<'UEOF'\n".encode())
            time.sleep(0.5)
            for line in text.split('\n'):
                serial.sendall((line + '\n').encode())
                time.sleep(0.02)
            serial.sendall(b'UEOF\n')
            time.sleep(1.0)
            drain(3)
            print(f'[send-file] {source} -> {dest} ({len(text)} bytes)')
        commands = list(args.cmd) or [
            'pgrep -af "installer-prompt|calamares|lubuntu" | head -10; echo DONE1',
            'pgrep -af "Xorg|Xwayland|lxqt-session|openbox|sddm|lightdm" | head -10; echo DONE2',
            'ls -la /tmp/.X11-unix/ 2>&1; echo "DISPLAY=$DISPLAY"; echo DONE3',
            'ls -la /tmp/calamares.log /root/.cache/calamares/session.log 2>&1; echo DONE4',
        ]
        for command in commands:
            marker = command.rsplit('; echo ', 1)[-1] if '; echo ' in command else 'DONE'
            out = run(command, marker, 120)
            print(f'$ {command}\n{out.strip()}\n---')
        return 0
    except (OSError, RuntimeError, TimeoutError, ValueError) as error:
        print(f'エラー: {error}', file=sys.stderr)
        return 1
    finally:
        try:
            monitor.close()
        except OSError:
            pass
        try:
            serial.close()
            log_file.close()
        except OSError:
            pass


if __name__ == '__main__':
    sys.exit(main())
