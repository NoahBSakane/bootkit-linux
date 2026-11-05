#!/usr/bin/env python3
"""標的ディスク単独で起動し、再層化後の設置の追加検査 (混入・apt の整合・健全性) を行う。

手順: verify-installed.py と同じ QEMU 構成で qcow2 だけを起動し、
ログインして getcap・dpkg -l 全文・installer/live 混入の一覧を取る。
標準ライブラリのみ。接頭辞は短くすること (AF_UNIX の路長制限)。
"""
import re
import shlex
import socket
import subprocess
import sys
import time
from pathlib import Path


def parse_args():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disk', type=Path, required=True)
    parser.add_argument('--prefix', type=Path, required=True)
    parser.add_argument('--mem', type=int, default=2048)
    parser.add_argument('--smp', type=int, default=2)
    parser.add_argument('--timeout', type=float, default=1800)
    parser.add_argument('--user', default='ubuntu')
    parser.add_argument('--password', default='ubuntu')
    parser.add_argument('--kernel', type=Path, default=None)
    parser.add_argument('--initrd', type=Path, default=None)
    parser.add_argument('--append', default=None)
    args = parser.parse_args()
    if not args.disk.is_file():
        parser.error(f'ディスクがありません: {args.disk}')
    args.disk = args.disk.resolve()
    args.prefix = args.prefix.absolute()
    return args


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


def expect_prompt(expect, marks, timeout, label):
    try:
        return expect(marks[0], timeout, label)
    except TimeoutError:
        pass
    return expect(marks[1], timeout, label)


EXTRA_COMMANDS = [
    ('wait', 'echo WAIT_BEGIN; for i in $(seq 1 120); do pgrep -x apt-get >/dev/null || break; sleep 5; done; echo "WAIT_ITER=$i"; echo WAIT_DONE'),
    ('audit', 'echo AUDIT_BEGIN; dpkg --audit; echo "AUDIT_RC=$?"; echo AUDIT_DONE'),
    ('apt', 'echo APT_BEGIN; echo ubuntu | sudo -S apt-get check; echo "APT_RC=$?"; echo APT_DONE'),
    ('pkgs', 'echo PKGS_BEGIN; echo "TOTAL=$(dpkg-query -W -f=\'${db:Status-Abbrev}\\n\' | grep -c ^ii)"; '
             'dpkg-query -W -f=\'${Package}\\n\' | grep -E "^(subiquity|casper|ubiquity|calamares|lubuntu-live|ubuntu-desktop|gdm3|gnome-shell|lxqt-core|sddm|snapd|cloud-init|grub2-common|grub-efi-amd64)" | tr "\\n" " "; echo; echo PKGS_DONE'),
    ('mounts', 'echo MOUNTS_BEGIN; findmnt -no SOURCE,FSTYPE,TARGET /; cat /etc/fstab | grep -v "^#"; '
               'ls -d /cdrom /casper /snap/subiquity /var/lib/snapd/seed /etc/calamares /var/log/installer 2>&1; echo MOUNTS_DONE'),
    ('users', 'echo USERS_BEGIN; getent passwd | awk -F: \'$3>=1000||/installer|ubuntu|lubuntu|live/{print $1":"$3":"$7}\'; '
              'ls /etc/sddm.conf /etc/sddm.conf.d 2>&1; grep -rE "^(User|Session|Autologin)" /etc/sddm.conf /etc/sddm.conf.d 2>/dev/null; '
              'ls /usr/share/xsessions /usr/share/wayland-sessions 2>&1; cat /etc/lsb-release | head -3; echo USERS_DONE'),
    ('health', 'echo HEALTH_BEGIN; systemctl is-system-running; systemctl --failed --no-legend | head; '
               'dmesg | grep -iE "squashfs|overlayfs|I/O error|EXT4-fs error" | head -5; '
               'grep -c . /var/lib/dpkg/status; echo HEALTH_DONE'),
    ('getcap', 'echo GETCAP_BEGIN; getcap /usr/bin/ping /usr/bin/mtr-packet 2>&1; echo GETCAP_DONE'),
]


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

    deadline = time.monotonic() + args.timeout
    code = Path(subprocess.check_output(['brew', '--prefix'], text=True).strip()) / 'share/qemu/edk2-x86_64-code.fd'
    vars_template = Path(subprocess.check_output(['brew', '--prefix'], text=True).strip()) / 'share/qemu/edk2-i386-vars.fd'
    variables = prefix.parent / (prefix.name + '.vars.fd')
    process = None
    monitor_conn = None
    serial_conn = None
    serial_file = None
    try:
        command = ['qemu-system-x86_64', '-machine', 'q35',
                   '-accel', 'tcg,thread=multi', '-cpu', 'Westmere,-aes',
                   '-smp', str(args.smp), '-m', str(args.mem)]
        if args.kernel is not None:
            if args.initrd is None or args.append is None:
                raise ValueError('--kernel には --initrd と --append が要る')
            command += ['-kernel', str(args.kernel),
                        '-initrd', str(args.initrd),
                        '-append', args.append]
        else:
            subprocess.run(['cp', str(vars_template), str(variables)], check=True)
            command += ['-drive', f'if=pflash,format=raw,readonly=on,file={code}',
                        '-drive', f'if=pflash,format=raw,file={variables}',
                        '-boot', 'c']
        command += ['-drive', f'file={args.disk},if=virtio,format=qcow2',
                    '-vga', 'std', '-usb', '-device', 'usb-kbd',
                    '-display', 'none',
                    '-monitor', f'unix:{monitor_path},server=on,wait=off',
                    '-serial', f'unix:{serial_path},server=on,wait=off',
                    '-net', 'none']
        note('[qemu] ' + shlex.join(command))
        print(shlex.join(command), flush=True)
        log = open(log_path, 'wb')
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        Path(str(prefix) + '.pid').write_text(str(process.pid) + '\n')
        monitor_conn = wait_connect(monitor_path, process, deadline, 'monitor')
        monitor_conn.settimeout(0.5)
        data = b''
        end = time.monotonic() + 30
        while not data.endswith(b'(qemu) '):
            if time.monotonic() >= end:
                raise TimeoutError('QEMU モニターの応答がありません')
            try:
                data += monitor_conn.recv(65536)
            except socket.timeout:
                continue
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

        expect('login:', 1500, 'ログイン待ち')
        sendline(args.user, 'ユーザー名')
        try:
            expect('Password:', 30, 'パスワード待ち')
            sendline(args.password, 'パスワード')
        except TimeoutError:
            note('[serial] パスワード不要で進行')
        prompt = expect_prompt(expect, ['$ ', '# '], 60, 'プロンプト待ち')
        out = {}
        for key, cmd in EXTRA_COMMANDS:
            out[key] = run(cmd, key.upper() + '_DONE', 300, key)
        (prefix.parent / (prefix.name + '.extra.txt')).write_text(
            '\n\n'.join(f'=== {key} ===\n{value}' for key, value in out.items()), encoding='utf-8')
        note('[判定] 追加検査が成功')
        monitor_conn.sendall(b'quit\n')
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.terminate()
        return 0
    except (OSError, RuntimeError, TimeoutError, ValueError, subprocess.SubprocessError) as error:
        note(f'[異常] {error}')
        print(f'エラー: {error}', file=sys.stderr)
        return 1
    finally:
        try:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        finally:
            for conn in (monitor_conn, serial_conn):
                if conn is not None:
                    try:
                        conn.close()
                    except OSError:
                        pass
            if serial_file is not None:
                try:
                    serial_file.close()
                except OSError:
                    pass
            transcript_path.write_text(''.join(transcript), encoding='utf-8')
            for stale in (monitor_path, serial_path):
                try:
                    stale.unlink()
                except OSError:
                    pass
            try:
                variables.unlink()
            except OSError:
                pass
            try:
                Path(str(prefix) + '.pid').unlink()
            except OSError:
                pass


if __name__ == '__main__':
    sys.exit(main())
