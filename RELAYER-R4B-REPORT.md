# R4b 報告: 新しい統合 ISO の設置の検証

確認日: 2026-11-05。作業ツリー `~/.worktrees/bootkit-linux/relayer`(ブランチ `work/relayer`)。

## 結論

新しい統合 ISO(再層化版)から、Server・Lubuntu の Normal と Minimal の計 4 通りを、オフラインで最後まで設置できた。設置後のディスクだけで起動し、Lubuntu はログイン画面とデスクトップまで出た。設置後の `dpkg --audit` は 4 通りとも空で、live・installer の残りはない。

設置の検証中に、Lubuntu の Calamares がブートローダー準備で失敗する欠陥が見つかり、修正して再設置で解消した。

未実施: Ubuntu デスクトップの設置(subiquity)と、toram 項目からの設置。

## 対象 ISO

| 項目 | 値 |
| --- | --- |
| ファイル | `build/ubuntu-merge-26.04.1-amd64-relayer.iso` |
| 大きさ | 8,847,738,880 バイト |
| SHA-256 | `fe3bcfbece3e262bf3fea9720d3f47e44fe183afe0a808be7f6afec911342f14` |

## 結果表

| 対象 | 設置の完了 | 設置後の単独起動 | `dpkg --audit` | 備考 |
| --- | --- | --- | --- | --- |
| Server Normal | 完了 | 起動 | 空 | `apt-get check` 異常なし(cloud-init のロック解放後) |
| Server Minimal | 完了 | 起動 | 空 | 同上 |
| Lubuntu Normal | 43/43 完了 | SDDM とデスクトップに到達 | 空 | 後述のパニック観察あり |
| Lubuntu Minimal | 43/43 完了 | SDDM とデスクトップに到達 | 空 | 起動は 1 回とも正常 |
| Ubuntu デスクトップ | 未実施 | - | - | 次の段階 |
| toram からの設置 | 未実施 | - | - | 任意項目 |

Server の設置後の確認(Normal・Minimal 共通): subiquity・casper・calamares・ubuntu-desktop・gnome-shell が無い。`getcap` の結果が正しい。`systemctl` が degraded になるのは wait-online だけで、`-net none` で起動したための想定どおりの状態。

## Lubuntu の設置後の中身(Normal と Minimal の比較)

証拠: `build/evidence/relayer-r4b/lubuntu-installed-inspection.txt`。方法は、live ISO を起動して設置後のディスクを読み取り専用でマウントし、`dpkg --admindir` で問い合わせた。

| 項目 | Normal | Minimal |
| --- | --- | --- |
| パッケージ数(ii) | 1,972 | 1,658 |
| snapd と seed の snap | あり(8 個) | なし |
| grub-efi-amd64-signed・shim-signed・efibootmgr | あり | あり |
| sddm・lxqt-core・cloud-init | あり | あり |
| casper・calamares・subiquity・ubuntu-desktop・gdm3・gnome-shell | なし | なし |
| ユーザー | test のみ | test のみ |
| `/pool`・`/dists`・`/etc/calamares`・`/cdrom`・`/rofs` | なし | なし |
| SDDM の表示 | ユーザー TEST のみ・セッション Lubuntu | 同左 |

## 失敗と対処

1. 現象: Lubuntu の Normal・Minimal とも、Calamares が 35/43 で停止した。`sh: 0: cannot open /etc/calamares/bootrepo-apt.sh`。
2. 原因: ブートローダー準備の `contextualprocess` は既定で設置先の中(chroot)で実行される。しかし設定層は live 環境にだけ在り、設置先には無い。
3. 対処: `before_bootloader_context.conf` に `dontChroot: true` を指定し、`bootrepo-apt.sh` を `${ROOT}` を引数に live 側から実行する形にした。スクリプトは、live の `/pool`・`/dists` を設置先へ bind マウントし、`chroot "$ROOT" apt-get` で `file:///` の署名なし(`Trusted: yes`)の repo からブートローダー関連の deb を入れ、終了時にマウントを解除する。変更は `tools/ubuntu-merge/build-lubuntu-stages.sh` と `test_stages_layout.py`。
4. 確認: ISO を作り直し、Normal・Minimal とも新規に再設置して 43/43 で完了した。失敗時の証拠は `lubuntu-*/fail1/`(原因は `CAUSE.txt`)。

## 観察: Normal の初回起動でのカーネルパニック

Lubuntu Normal の設置後ディスクを、通常の GRUB 項目(`quiet splash`)で起動すると、1 回目と 2 回目で約 4 分後に「KERNEL PANIC! Fatal exception in interrupt」(カーネルの drm panic 画面)が出た。

| 起動 | 結果 | 証拠(`lubuntu-normal/boot-alone/`) |
| --- | --- | --- |
| 通常項目 1 回目 | パニック | `default-entry-panic-1.png` |
| 通常項目 2 回目 | パニック | `default-entry-panic-2.png` |
| GRUB コマンドラインから(`quiet splash` なし、`console=ttyS0`) | 正常に SDDM へ | `grub-cmdline.png`、`serial-direct-boot.raw` |
| 再起動後 | 正常に SDDM とデスクトップへ | `sddm-login.png`、`lxqt-desktop.png` |
| 通常項目 3 回目 | 正常に SDDM へ(約 1 時間 22 分後にキー入力で画面が復帰) | `default-entry-3-sddm-login.png` |

Minimal の通常項目は 1 回の起動で正常だった。原因は未検証。仮説は 2 つで、(1) TCG のマルチスレッド実行の不安定さ、(2) 設置直後の初回起動に固有の何か。(2) は、設置を再実行しないと再現を試せない。実機での確認が要る項目として残す。

## 未実施の項目

- Ubuntu デスクトップの設置(subiquity、`ubuntu-desktop`・`ubuntu-desktop-minimal`)。
- toram 項目からの設置。
- Calamares が「Install Now」の直後にまれに異常終了した(Minimal で 1 回。再起動して続行)。タッチ操作の自動化による可能性を疑ったが、未検証。

## 変更点

- `tools/ubuntu-merge/build-lubuntu-stages.sh`: bootloader 準備を `dontChroot` と bind マウントの形に変更。
- `tools/ubuntu-merge/test_stages_layout.py`: 上記の形の検査を追加。
- `tools/offline-install/verify-installed-r4b.py`: 設置後ディスクの検証用(新規)。
- 証拠: `build/evidence/relayer-r4b/`。設置後ディスクの qcow2(Normal 約 8.7GB、Minimal 約 5.9GB)は再生成できるので、証拠の確定後に削除する。

## 影響範囲

Lubuntu の設置経路(設定層 `common.dl.snap.lubuntu.std.live.install.squashfs`)だけが変わる。ほかの層・grub・カタログは変わらない。ISO の SHA-256 は、この修正後の値。
