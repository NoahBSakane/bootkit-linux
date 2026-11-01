#!/usr/bin/env python3
"""統合 ISO から Lubuntu を Calamares で標的ディスクへ入れる (第1起動)。

手順: 統合 ISO + 空 qcow2 で QEMU を起動し、GRUB の Lubuntu 通常項目
(0 始まり 3) を選ぶ。LXQt が上がったら calamares を起動し、画面ごとに
撮影しながら sendkey で自動操作して完走させ、poweroff で QEMU を終える。
標準ライブラリのみ。画面の指紋は各 PNG の SHA-256 を記録する。
"""
import argparse
import hashlib
import json
import re
import shlex
import signal
import socket
import subprocess
import sys
import time
import threading
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iso', type=Path, required=True)
    parser.add_argument('--disk', type=Path, required=True)
    parser.add_argument('--prefix', type=Path, required=True)
    parser.add_argument('--mem', type=int, default=4096)
    parser.add_argument('--smp', type=int, default=4)
    parser.add_argument('--entry', type=int, default=3)
    parser.add_argument('--timeout', type=float, default=10800)
    parser.add_argument('--user', default='ubuntu')
    parser.add_argument('--password', default='ubuntu')
    parser.add_argument('--extra', default='console=tty0 console=ttyS0,115200')
    args = parser.parse_args()
    for name in ('iso', 'disk'):
        if not getattr(args, name).is_file():
            parser.error(f'{name} がありません: {getattr(args, name)}')
    args.iso = args.iso.resolve()
    args.disk = args.disk.resolve()
    args.prefix = args.prefix.absolute()
    return args


class Monitor:
    def __init__(self, connection, process, deadline):
        self.connection = connection
        self.process = process
        self.deadline = deadline
        self.lock = threading.RLock()

    def check_time(self):
        if time.monotonic() >= self.deadline:
            raise TimeoutError('実行期限を超えました')
        if self.process.poll() is not None:
            raise RuntimeError(f'QEMU が終了しました (exit {self.process.returncode})')

    def response(self):
        data = b''
        end = time.monotonic() + 30
        while not data.endswith(b'(qemu) '):
            self.check_time()
            if time.monotonic() >= end:
                raise TimeoutError('QEMU モニターの応答がありません')
            try:
                part = self.connection.recv(65536)
            except socket.timeout:
                continue
            if not part:
                raise RuntimeError('QEMU モニターが切断されました')
            data += part
        return data.decode('utf-8', errors='replace')

    def send(self, command, note, transcript):
        with self.lock:
            self.check_time()
            self.connection.sendall((command + '\n').encode())
            if command == 'quit':
                transcript.append('[hmp] 終了: quit\n')
                return ''
            result = self.response()
            clean = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', result).replace('\r', '')
            transcript.append(f'[hmp] {note}: {command}\n{clean}\n')
            if re.search(r'(?im)^(?:error:|unknown command|invalid parameter|Could not|Error )', result):
                raise RuntimeError(f'QEMU モニター: {result.strip()}')
            return result


def keyboard(monitor, line, transcript, key_delay=0.15):
    keys = {' ': 'spc', '=': 'equal', '-': 'minus', '.': 'dot',
            '/': 'slash', ':': 'shift-semicolon', ',': 'comma',
            '_': 'shift-minus', '@': 'shift-2', "'": 'apostrophe'}
    for char in line:
        key = keys.get(char, char)
        if char.isupper():
            key = 'shift-' + char.lower()
        monitor.send('sendkey ' + key, 'calamares 入力', transcript)
        time.sleep(key_delay)
    monitor.send('sendkey ret', 'calamares 入力確定', transcript)
    time.sleep(1.0)


def wait_connect(path, process, deadline, label):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    try:
        end = time.monotonic() + 60
        while True:
            if process.poll() is not None:
                raise RuntimeError(f'QEMU が起動直後に終了しました (exit {process.returncode})')
            if time.monotonic() >= min(end, deadline):
                raise TimeoutError(f'{label} の接続を待てませんでした')
            try:
                sock.connect(str(path))
                return sock
            except (FileNotFoundError, ConnectionRefusedError):
                time.sleep(0.2)
    except Exception:
        sock.close()
        raise


def clean_terminal(value):
    value = re.sub(r'\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)', '', value)
    value = re.sub(r'\x1bP.*?\x1b\\', '', value, flags=re.DOTALL)
    value = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', value)
    return value.replace('\r\n', '\n').replace('\r', '\n')


def main():
    args = parse_args()
    prefix = args.prefix
    prefix.parent.mkdir(parents=True, exist_ok=True)
    monitor_path = prefix.parent / (prefix.name + '.mon')
    serial_path = prefix.parent / (prefix.name + '.ser')
    log_path = Path(str(prefix) + '.qemu.log')
    serial_raw = Path(str(prefix) + '.serial.log')
    transcript_path = Path(str(prefix) + '.transcript.txt')
    transcript = []

    def note(line):
        transcript.append(line + '\n')

    def shot(monitor, name):
        path = Path(str(prefix) + f'-{name}.png')
        monitor.send(f'screendump {json.dumps(str(path))} -f png', f'撮影 {name}', transcript)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        note(f'[指紋] {name}: sha256={digest} size={path.stat().st_size}')
        return path

    for stale in (monitor_path, serial_path):
        if stale.exists() or Path(str(stale)).is_symlink():
            raise FileExistsError(f'ソケットのパスが使用中です: {stale}')
    process = None
    monitor_conn = None
    monitor = None
    serial_conn = None
    serial_file = None
    variables = prefix.parent / (prefix.name + '.vars.fd')
    deadline = time.monotonic() + args.timeout
    code = Path(subprocess.check_output(['brew', '--prefix'], text=True).strip()) / 'share/qemu/edk2-x86_64-code.fd'
    vars_template = Path(subprocess.check_output(['brew', '--prefix'], text=True).strip()) / 'share/qemu/edk2-i386-vars.fd'

    def drive(path):
        return str(path).replace(',', ',,')

    try:
        subprocess.run(['cp', str(vars_template), str(variables)], check=True)
        command = ['qemu-system-x86_64', '-machine', 'q35',
                   '-accel', 'tcg,thread=multi', '-cpu', 'Westmere,-aes',
                   '-smp', str(args.smp), '-m', str(args.mem),
                   '-drive', f'if=pflash,format=raw,readonly=on,file={drive(code)}',
                   '-drive', f'if=pflash,format=raw,file={drive(variables)}',
                   '-drive', f'id=cd0,if=none,media=cdrom,readonly=on,file={drive(args.iso)}',
                   '-device', 'ide-cd,drive=cd0',
                   '-drive', f'file={drive(args.disk)},if=virtio,format=qcow2',
                   '-vga', 'std', '-usb', '-device', 'usb-kbd',
                   '-boot', 'd', '-display', 'none',
                   '-monitor', f'unix:{monitor_path},server=on,wait=off',
                   '-serial', f'unix:{serial_path},server=on,wait=off',
                   '-net', 'none']
        note('[qemu] ' + shlex.join(command))
        print(shlex.join(command), flush=True)
        log = open(log_path, 'wb')
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        Path(str(prefix) + '.pid').write_text(str(process.pid) + '\n')
        monitor_conn = wait_connect(monitor_path, process, deadline, 'monitor')
        monitor_conn.settimeout(30)
        monitor = Monitor(monitor_conn, process, deadline)
        monitor.response()
        serial_conn = wait_connect(serial_path, process, deadline, 'serial')
        serial_conn.settimeout(0.5)
        serial_file = open(serial_raw, 'wb')
        buffer = b''

        def drain(timeout):
            nonlocal buffer
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                try:
                    part = serial_conn.recv(65536)
                except socket.timeout:
                    continue
                if not part:
                    break
                serial_file.write(part)
                serial_file.flush()
                buffer += part
                if b'\x1b[6n' in part:
                    serial_conn.sendall(b'\x1b[24;80R' * part.count(b'\x1b[6n'))

        def expect(needle, timeout, label):
            mark = needle if isinstance(needle, bytes) else needle.encode()
            end = time.monotonic() + timeout
            while True:
                if mark in buffer:
                    note(f'[serial] {label}: 検出 {needle!r}')
                    return
                if process.poll() is not None:
                    raise RuntimeError(f'{label} の前に QEMU が終了しました')
                if time.monotonic() >= deadline:
                    raise TimeoutError('実行期限を超えました')
                if time.monotonic() >= end:
                    tail = buffer[-2000:].decode('utf-8', errors='replace')
                    raise TimeoutError(f'{label}: 待ち切れませんでした。末尾:\n{tail}')
                drain(0.5)

        def sendline(line, label):
            serial_conn.sendall((line + '\n').encode())
            serial_file.write(b'[host] ' + (line + '\n').encode())
            serial_file.flush()
            note(f'[host] {label}: {line}')
            time.sleep(0.5)

        def run(command_text, marker, timeout, label):
            nonlocal buffer
            buffer = b''
            sendline(command_text, label)
            end = time.monotonic() + timeout
            while ('\n' + marker + '\n') not in ('\n' + clean_terminal(buffer.decode('utf-8', errors='replace'))):
                if process.poll() is not None:
                    raise RuntimeError(f'{label} の前に QEMU が終了しました')
                if time.monotonic() >= deadline:
                    raise TimeoutError('実行期限を超えました')
                if time.monotonic() >= end:
                    raise TimeoutError(label + ': 完了行を取得できない')
                drain(0.5)
            note(f'[serial] {label}: 完了行 {marker}')
            return clean_terminal(buffer.decode('utf-8', errors='replace'))

        expect('Try or Install Lubuntu', 900, 'grub メニュー待ち')
        monitor.send('sendkey c', 'grub コンソール', transcript)
        time.sleep(2)
        keyboard(monitor, "set bootkit_extra='" + args.extra + "'", transcript)
        monitor.send('sendkey esc', 'grub メニューへ戻る', transcript)
        time.sleep(2)
        shot(monitor, 'grub')
        for _ in range(args.entry):
            monitor.send('sendkey down', 'grub 移動', transcript)
            time.sleep(3)
        monitor.send('sendkey ret', 'grub 決定', transcript)
        time.sleep(10)
        shot(monitor, 'boot')
        expect(b'login:', 2400, 'ログイン待ち')
        sendline(args.user, 'ユーザー名')
        try:
            expect(b'Password:', 20, 'パスワード待ち')
            sendline(args.password, 'パスワード')
        except TimeoutError:
            note('[serial] パスワード不要で進行')
        run('echo SER_OK', 'SER_OK', 120, 'serial 応答確認')
        # 起動プロンプト (Try / Install) が出るまで待つ。
        out = run('for i in $(seq 1 120); do pgrep -af "[i]nstaller-prompt|lubuntu-installer" | head -3; pgrep -af "[i]nstaller-prompt" >/dev/null && break; sleep 5; done; echo PROMPT_DONE',
                  'PROMPT_DONE', 700, 'プロンプト待ち')
        note('[serial] prompt:\n' + out)
        time.sleep(10)
        shot(monitor, 'prompt')
        # Install Lubuntu をマウスで押す (閉ループ: 外れたら screenshot で補正)。
        for attempt in range(1, 4):
            monitor.send('mouse_move 305 175', f'照準 {attempt}', transcript)
            time.sleep(2)
            path = Path(str(prefix) + f'-aim-{attempt}.png')
            monitor.send(f'screendump {json.dumps(str(path))} -f png', f'照準撮影 {attempt}', transcript)
            note(f'[指紋] aim-{attempt}: sha256={hashlib.sha256(path.read_bytes()).hexdigest()}')
            monitor.send('mouse_button 1', f'押下 {attempt}', transcript)
            time.sleep(1)
            monitor.send('mouse_button 0', f'解放 {attempt}', transcript)
            time.sleep(10)
            shot(monitor, f'after-click-{attempt}')
            out = run('pgrep -af "[c]alamares" | head; echo PGREP_DONE', 'PGREP_DONE', 120,
                      f'calamares 稼働確認 {attempt}')
            note(f'[serial] pgrep {attempt}:\n' + out)
            if re.search(r'(?m)calamares', out):
                break
            monitor.send('mouse_move -60 -15', f'補正 {attempt}', transcript)
            time.sleep(2)
        else:
            raise RuntimeError('Install ボタンが押せなかった')
        time.sleep(20)
        shot(monitor, 'calamares-welcome')
        note('[操作] ここから先は画面を見て進める。初回は指紋だけ残す。')
        note('[判定] 第1起動の自動操作は画面確認待ち (calamares 起動まで完了)')
        return 0
    except (OSError, RuntimeError, TimeoutError, ValueError, subprocess.SubprocessError) as error:
        note(f'[異常] {error}')
        print(f'エラー: {error}', file=sys.stderr)
        return 1
    finally:
        try:
            if process is not None and process.poll() is None:
                pass  # QEMU は残す (後続の操作のため)。終了は呼び出し側で行う。
        finally:
            with transcript_path.open('w', encoding='utf-8') as stream:
                stream.write(''.join(transcript))


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt))
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('中断しました', file=sys.stderr)
        sys.exit(130)
