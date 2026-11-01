#!/usr/bin/env python3
"""ゲスト内で uinput ポインタを作り、動かして押す。`sudo python3` で実行する。

使い方 (DISPLAY と XAUTHORITY を sudo に渡すこと):
  sudo DISPLAY=:0 XAUTHORITY=/tmp/xauth_jjhhqn python3 /tmp/mclick.py park
  sudo DISPLAY=:0 XAUTHORITY=/tmp/xauth_jjhhqn python3 /tmp/mclick.py move <dx> <dy>
  sudo DISPLAY=:0 XAUTHORITY=/tmp/xauth_jjhhqn python3 /tmp/mclick.py click [left|right|middle]
  sudo DISPLAY=:0 XAUTHORITY=/tmp/xauth_jjhhqn python3 /tmp/mclick.py at <x> <y>
  sudo DISPLAY=:0 XAUTHORITY=/tmp/xauth_jjhhqn python3 /tmp/mclick.py tap <x> <y>
  sudo DISPLAY=:0 XAUTHORITY=/tmp/xauth_jjhhqn python3 /tmp/mclick.py tapkey <x> <y> space|enter|tab
  sudo DISPLAY=:0 XAUTHORITY=/tmp/xauth_jjhhqn python3 /tmp/mclick.py key space enter tab
  sudo DISPLAY=:0 XAUTHORITY=/tmp/xauth_jjhhqn python3 /tmp/mclick.py type sometext123
park/move/click は相対マウス (flat 化して 1:1 にする)。
at/tap は絶対タッチ (INPUT_PROP_DIRECT。加速度の影響を受けない)。
デバイスは毎回作って消す。標準ライブラリのみ。
"""
import fcntl
import os
import struct
import subprocess
import sys
import time

EV_SYN, EV_KEY, EV_REL, EV_ABS = 0, 1, 2, 3
SYN_REPORT = 0
REL_X, REL_Y, ABS_X, ABS_Y = 0, 1, 0, 1
BTN_LEFT, BTN_RIGHT, BTN_MIDDLE, BTN_TOUCH = 272, 273, 274, 330
BTN_TOOL_FINGER = 318
BUTTONS = {'left': BTN_LEFT, 'right': BTN_RIGHT, 'middle': BTN_MIDDLE}
INPUT_PROP_DIRECT = 2
UI_SET_EVBIT = 0x40045564
UI_SET_KEYBIT = 0x40045565
UI_SET_RELBIT = 0x40045566
UI_SET_ABSBIT = 0x40045567
UI_SET_PROPBIT = 0x40045568
UI_DEV_SETUP = 0x405c5503
UI_ABS_SETUP = 0x401c5504
UI_DEV_CREATE = 0x5501
UI_DEV_DESTROY = 0x5502
W, H = 1280, 800


def env():
    return {'PATH': '/usr/bin:/bin',
            'DISPLAY': os.environ.get('DISPLAY', ':0'),
            'XAUTHORITY': os.environ.get('XAUTHORITY', '')}


def ev(fd, kind, code, value):
    fd.write(struct.pack('qqHHi', 0, 0, kind, code, value))
    if kind != EV_SYN:
        fd.write(struct.pack('qqHHi', 0, 0, EV_SYN, SYN_REPORT, 0))


def flatten():
    try:
        dev_id = subprocess.check_output(
            ['xinput', '--list', '--id-only', 'probemouse'],
            env=env()).decode().split()[0]
        subprocess.check_call(
            ['xinput', 'set-prop', dev_id,
             'libinput Accel Profile Enabled', '0', '1', '0'], env=env())
        back = subprocess.check_output(
            ['xinput', 'list-props', dev_id], env=env()).decode()
        for line in back.split('\n'):
            if 'Accel Profile Enabled (' in line:
                print('flat: ' + line.strip())
    except (subprocess.CalledProcessError, IndexError, OSError) as error:
        print(f'flat 化に失敗: {error}', file=sys.stderr)


def open_relative():
    fd = open('/dev/uinput', 'wb', buffering=0)
    fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)
    fcntl.ioctl(fd, UI_SET_EVBIT, EV_REL)
    for code in BUTTONS.values():
        fcntl.ioctl(fd, UI_SET_KEYBIT, code)
    for code in (REL_X, REL_Y):
        fcntl.ioctl(fd, UI_SET_RELBIT, code)
    dev = struct.pack('80sHHHHI', b'probemouse', 0x03, 0x1234, 0x5678, 0x0001, 0)
    dev += struct.pack('64i', *([0] * 64)) * 4
    fd.write(dev)
    fcntl.ioctl(fd, UI_DEV_CREATE)
    time.sleep(2.0)
    flatten()
    return fd


def open_absolute():
    fd = open('/dev/uinput', 'wb', buffering=0)
    fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)
    fcntl.ioctl(fd, UI_SET_EVBIT, EV_ABS)
    fcntl.ioctl(fd, UI_SET_KEYBIT, BTN_TOUCH)
    fcntl.ioctl(fd, UI_SET_KEYBIT, BTN_TOOL_FINGER)
    fcntl.ioctl(fd, UI_SET_ABSBIT, ABS_X)
    fcntl.ioctl(fd, UI_SET_ABSBIT, ABS_Y)
    fcntl.ioctl(fd, UI_SET_PROPBIT, INPUT_PROP_DIRECT)
    setup = struct.pack('HHHH80sI', 0x03, 0x1234, 0x5678, 0x0001,
                        b'probetouch', 0)
    fcntl.ioctl(fd, UI_DEV_SETUP, setup)
    fcntl.ioctl(fd, UI_ABS_SETUP, struct.pack('Hxx6i', ABS_X, 0, 0, W - 1, 0, 0, 0))
    fcntl.ioctl(fd, UI_ABS_SETUP, struct.pack('Hxx6i', ABS_Y, 0, 0, H - 1, 0, 0, 0))
    fcntl.ioctl(fd, UI_DEV_CREATE)
    time.sleep(2.0)
    return fd


def close(fd):
    time.sleep(0.5)
    fcntl.ioctl(fd, UI_DEV_DESTROY)
    fd.close()


KEYMAP = {
    'a': 30, 'b': 48, 'c': 46, 'd': 32, 'e': 18, 'f': 33, 'g': 34,
    'h': 35, 'i': 23, 'j': 36, 'k': 37, 'l': 38, 'm': 50, 'n': 49,
    'o': 24, 'p': 25, 'q': 16, 'r': 19, 's': 31, 't': 20, 'u': 22,
    'v': 47, 'w': 17, 'x': 45, 'y': 21, 'z': 44,
    '1': 2, '2': 3, '3': 4, '4': 5, '5': 6,
    '6': 7, '7': 8, '8': 9, '9': 10, '0': 11,
    ' ': 57, '-': 12, '.': 52, '_': 12,
}
KEY_SHIFT, KEY_ENTER, KEY_TAB, KEY_SPACE, KEY_ESC = 42, 28, 15, 57, 1
KEY_LEFTCTRL = 29
NAMED = {'enter': KEY_ENTER, 'tab': KEY_TAB, 'space': KEY_SPACE,
         'esc': KEY_ESC, 'shift': KEY_SHIFT, 'ctrl': KEY_LEFTCTRL}


def open_keyboard():
    fd = open('/dev/uinput', 'wb', buffering=0)
    fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)
    for code in set(KEYMAP.values()) | {KEY_SHIFT, KEY_ENTER, KEY_TAB,
                                            KEY_LEFTCTRL}:
        fcntl.ioctl(fd, UI_SET_KEYBIT, code)
    dev = struct.pack('80sHHHHI', b'probekey', 0x03, 0x1234, 0x5679, 0x0001, 0)
    dev += struct.pack('64i', *([0] * 64)) * 4
    fd.write(dev)
    fcntl.ioctl(fd, UI_DEV_CREATE)
    time.sleep(1.5)
    return fd


def press(fd, code):
    ev(fd, EV_KEY, code, 1)
    time.sleep(0.15)
    ev(fd, EV_KEY, code, 0)
    time.sleep(0.15)


def type_text(fd, text):
    for ch in text:
        if ch == '_':
            ev(fd, EV_KEY, KEY_SHIFT, 1)
            time.sleep(0.1)
            press(fd, KEYMAP['-'])
            ev(fd, EV_KEY, KEY_SHIFT, 0)
            time.sleep(0.1)
        elif ch in KEYMAP:
            press(fd, KEYMAP[ch])
        else:
            raise SystemExit(f'type 不可: {ch!r}')


def main():
    cmd = sys.argv[1]
    if cmd == 'park':
        fd = open_relative()
        for _ in range(6):
            ev(fd, EV_REL, REL_X, -4000)
            ev(fd, EV_REL, REL_Y, -4000)
            time.sleep(0.2)
        close(fd)
    elif cmd == 'move':
        fd = open_relative()
        ev(fd, EV_REL, REL_X, int(sys.argv[2]))
        ev(fd, EV_REL, REL_Y, int(sys.argv[3]))
        close(fd)
    elif cmd == 'click':
        name = sys.argv[2] if len(sys.argv) > 2 else 'left'
        fd = open_relative()
        ev(fd, EV_KEY, BUTTONS[name], 1)
        time.sleep(0.5)
        ev(fd, EV_KEY, BUTTONS[name], 0)
        close(fd)
    elif cmd in ('at', 'tap'):
        x, y = int(sys.argv[2]), int(sys.argv[3])
        fd = open_absolute()
        ev(fd, EV_ABS, ABS_X, x)
        ev(fd, EV_ABS, ABS_Y, y)
        time.sleep(0.5)
        if cmd == 'tap':
            ev(fd, EV_KEY, BTN_TOOL_FINGER, 1)
            ev(fd, EV_KEY, BTN_TOUCH, 1)
            time.sleep(0.5)
            ev(fd, EV_KEY, BTN_TOUCH, 0)
            ev(fd, EV_KEY, BTN_TOOL_FINGER, 0)
        close(fd)
    elif cmd == 'tapkey':
        x, y, name = int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
        tfd = open_absolute()
        ev(tfd, EV_ABS, ABS_X, x)
        ev(tfd, EV_ABS, ABS_Y, y)
        time.sleep(0.5)
        ev(tfd, EV_KEY, BTN_TOOL_FINGER, 1)
        ev(tfd, EV_KEY, BTN_TOUCH, 1)
        time.sleep(0.5)
        ev(tfd, EV_KEY, BTN_TOUCH, 0)
        ev(tfd, EV_KEY, BTN_TOOL_FINGER, 0)
        time.sleep(0.5)
        close(tfd)
        kfd = open_keyboard()
        press(kfd, NAMED[name])
        close(kfd)
    elif cmd == 'key':
        kfd = open_keyboard()
        for name in sys.argv[2:]:
            if '+' in name:
                mods, base = name.split('+', 1)
                codes = [NAMED[m] for m in mods.split(',')]
                for code in codes:
                    ev(kfd, EV_KEY, code, 1)
                    time.sleep(0.1)
                press(kfd, NAMED[base])
                for code in codes:
                    ev(kfd, EV_KEY, code, 0)
                    time.sleep(0.1)
            else:
                press(kfd, NAMED[name])
        close(kfd)
    elif cmd == 'type':
        kfd = open_keyboard()
        type_text(kfd, sys.argv[2])
        close(kfd)
    else:
        raise SystemExit(f'unknown: {cmd}')


if __name__ == '__main__':
    main()
