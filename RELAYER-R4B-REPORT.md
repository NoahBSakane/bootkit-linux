# R4b 報告: 新しい統合 ISO の設置の検証

確認日: 2026-11-05〜06。作業ツリー `~/.worktrees/bootkit-linux/relayer`(ブランチ `work/relayer`)。

## 結論

新しい統合 ISO(再層化版)から、Server・Lubuntu の Normal と Minimal の計 4 通りを、オフラインで最後まで設置できた。設置後のディスクだけで起動し、Lubuntu はログイン画面とデスクトップまで出た。設置後の `dpkg --audit` は 4 通りとも空で、live・installer の残りはない。

設置の検証中に、Lubuntu の Calamares がブートローダー準備で失敗する欠陥が見つかり、修正して再設置で解消した。

2026-11-06 に、Ubuntu デスクトップの設置(subiquity、Normal・Minimal)も、
最終 ISO でオフライン・UEFI で最後まで通した。設置の過程で見つかった 2 つの欠陥(下記)を、
Ubuntu 用の設定層 3 本で解消し、ISO を組み立て直した。

未実施: toram 項目からの設置、画面付きの対話での Ubuntu デスクトップの設置。

## 対象 ISO

| 項目 | Server・Lubuntu の検証時 | 最終(Ubuntu の設定層 3 本を追加) |
| --- | --- | --- |
| ファイル | `build/ubuntu-merge-26.04.1-amd64-relayer.pre-aptfix.iso`(旧名 `...-relayer.iso`) | `build/ubuntu-merge-26.04.1-amd64-relayer.iso` |
| 大きさ | 8,847,738,880 バイト | 8,847,755,264 バイト |
| SHA-256 | `fe3bcfbece3e262bf3fea9720d3f47e44fe183afe0a808be7f6afec911342f14` | `6f08bc1564c0d659af0826453740ae84cd87cebbd5f7ac4aeec2fc28aa6caebc` |

Server・Lubuntu の設置は左の ISO で行った。最終 ISO との差は Ubuntu の設定層 3 本とカタログ
(Ubuntu の 2 項目の path と size)、起動の鎖(Ubuntu のみ 6 → 7 層)で、Server・Lubuntu の
層・鎖は同じである。最終 ISO では静的検証が全て合格し(全 17 層の再抽出ハッシュ・pool 358 件の
照合・LBA)、`make test` も全て成功した。Server・Lubuntu の設置を最終 ISO で
やり直してはいない。

## 結果表

| 対象 | 設置の完了 | 設置後の単独起動 | `dpkg --audit` | 備考 |
| --- | --- | --- | --- | --- |
| Server Normal | 完了 | 起動 | 空 | `apt-get check` 異常なし(cloud-init のロック解放後) |
| Server Minimal | 完了 | 起動 | 空 | 同上 |
| Lubuntu Normal | 43/43 完了 | SDDM とデスクトップに到達 | 空 | 後述のパニック観察あり |
| Lubuntu Minimal | 43/43 完了 | SDDM とデスクトップに到達 | 空 | 起動は 1 回とも正常 |
| Ubuntu デスクトップ Normal | 完了(約 31 分、最終 ISO、UEFI) | GDM のログイン画面に到達(UEFI) | 空 | 設置済み 1,769 パッケージ、`rc grub-pc` のみ |
| Ubuntu デスクトップ Minimal | 完了(約 25 分、最終 ISO、UEFI) | GDM のログイン画面に到達(UEFI) | 空 | 設置済み 1,541 パッケージ、`ubuntu-desktop` なし |
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

## Ubuntu デスクトップの失敗と対処

autoinstall(`source: {id: ubuntu-desktop}` / `ubuntu-desktop-minimal`)で、ネットワークなしで設置した。
設置開始の確認(`/meta/confirm`)は、画面の無い検証環境でクライアントが送れなかったため、手で送った。

1. 失敗 1(`configure_apt`): `The repository 'file:/cdrom resolute Release' is not signed`
   (`NO_PUBKEY 5DC2DBA365C15AD9`)。
   - 原因: デスクトップ層の `cdrom.sources` は、デスクトップ公式 ISO 固有の一回限りの鍵
     (`C67C0F15FE1AEBB1`)だけを信頼する。統合 ISO の `/dists` は Server 公式の原本で、
     鍵は `5DC2DBA365C15AD9`。3 つの公式 ISO の Release の鍵は全て別(desktop `C67C…`・
     server `5DC2…`・lubuntu `EF2C…`)。
   - 対処: Ubuntu の設置木の最上位に、`cdrom.sources` を Server 層の同一内容で上書きする
     小さな層を 2 本足した(`common.dl.snap.ubuntu.apt`・`common.dl.snap.ubuntu.std.apt`、
     各 4,096 バイト)。カタログの Ubuntu 2 項目の path をこの 2 本へ変えた。
2. 失敗 2(`installing-kernel`): `E: Unable to locate package linux-generic`。
   - 原因: 統合カタログの `kernel.default` は Server 由来の `linux-generic`。デスクトップ公式は
     `linux-generic-hwe-24.04` で、デスクトップ設置木には `linux-generic` が無く、
     Server の `/dists` 索引にも無い。subiquity は live 側の
     `/etc/subiquity/kernel-meta-package` をカタログより優先する。
   - 対処: Ubuntu の live の鎖の最上位に、このファイル(内容 `linux-generic-hwe-24.04`)だけの
     層を 1 本足した(`common.dl.snap.ubuntu.std.live.kernel`、4,096 バイト)。
     Server のカタログ・設置木は変えない。
3. 確認: 失敗 1 の対処と、失敗 2 の対処(live にファイルを手で置いた)を試験用 ISO で通した
   あと、層をツールチェーンへ取り込んで ISO を組み立て直し、最終 ISO で Normal・Minimal を
   設置し直して通した。設置後は、UEFI で単独起動して GDM のログイン画面まで届き、
   読み取り専用で接続した live から `dpkg --audit`・残り物・利用者を調べた
   (`ubuntu-final/{normal,minimal}/installed-inspection.txt`)。
   失敗時の証拠は `ubuntu-desktop/fail1-apt-not-signed.txt` と `run2-progress.log`。

最終 ISO での GRUB 起動(UEFI)は、Ubuntu の toram・通常、Server の通常、Lubuntu の通常の 4 項目を
再確認し、期待どおりだった(`build/evidence/relayer-r5/`、詳細は
[docs/ubuntu-merge-relayer.md](docs/ubuntu-merge-relayer.md) の「最終 ISO での GRUB 起動の再確認」)。

検証の限界: 画面付きの対話の設置は未検証。設置は OVMF の UEFI と直接カーネル指定の live で行い、
GRUB メニューの Ubuntu 項目から起動した live での設置は未実施。Ubuntu の live を同じ構成で
起動した 1 回が約 1 時間ログイン前に停止した(原因は未検証、証拠は
`ubuntu-final/minimal/inspection-live-hang.*`)。

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

- 画面付きの対話での Ubuntu デスクトップの設置。
- toram 項目からの設置。
- Calamares が「Install Now」の直後にまれに異常終了した(Minimal で 1 回。再起動して続行)。タッチ操作の自動化による可能性を疑ったが、未検証。

## 変更点

- `tools/ubuntu-merge/build-lubuntu-stages.sh`: bootloader 準備を `dontChroot` と bind マウントの形に変更。
- `tools/ubuntu-merge/test_stages_layout.py`: 上記の形の検査を追加。
- `tools/ubuntu-merge/build-ubuntu-apt-stages.sh`・`test_ubuntu_apt_stages.py`(新規)、
  `assemble_stages.py`・`stages_layout.py`・`grub_stages.py`・`tests/test-ubuntu-merge.sh`・
  `tools/offline-install/install-sources-relayer.yaml`・`ventoy/ramsel/verify-qemu.py`:
  Ubuntu の設定層 3 本(APT 設定 2 本、live kernel 設定 1 本)の生成・検査・カタログ・起動の鎖。
- `tools/offline-install/verify-installed-r4b.py`: 設置後ディスクの検証用(新規)。
- 証拠: `build/evidence/relayer-r4b/`。設置後ディスクの qcow2(Normal 約 8.7GB、Minimal 約 5.9GB)は再生成できるので、証拠の確定後に削除する。

## 影響範囲

Lubuntu の修正は、設置経路(設定層 `common.dl.snap.lubuntu.std.live.install.squashfs`)だけが変わる。
Ubuntu の設定層 3 本の追加は、Ubuntu の設置カタログ 2 項目と Ubuntu の起動の鎖・GRUB の 3 項目の
`layerfs-path` が変わり、Server・Lubuntu の層・鎖・カタログは変わらない。最終 ISO の
SHA-256 は上表の値。
