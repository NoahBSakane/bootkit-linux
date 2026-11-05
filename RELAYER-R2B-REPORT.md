# R2b 報告: 再層化した統合ISOの組み立てと静的検証

確認日: 2026-11-05。CCから委譲されたCodexが、この作業ツリー内で実行した。

## 変更点

新ISO `build/ubuntu-merge-26.04.1-amd64-relayer.iso` を生成した。**8,847,738,880 バイト** (8.240099 GiB)。依頼文の現行ISO 9,655,549,952 バイトに対して **-807,811,072 バイト** (-8.366%)。

SHA-256: `78e19917ceb0373f1037f9b937149fce612bfb82d2020f0f304a6417b61cad35`

静的検証1〜6はすべて合格。`make test` も通常パスと空白・ピリオドを含むパスの両方で合格した。

### ISOの内容と層の同一性

- 設置用9層はR2aの完成物をハードリンクでstagingへ置いた。再圧縮していない。
- 公式live・installer 4層は公式ISOからxorrisoで抽出し、再圧縮せずに収録した。
- 公式3 ISO全体のSHA-256を入力フォルダの公式SHA256SUMS原本と再照合し、一致した。
- live 4層は公式ISO内のmd5sum.txtとも照合し、一致した。下表のSHA-256を記録した。
- ISOから14層を順に実抽出し、設置用9層・live 4層・新設定層のSHA-256がstaging原本と全件一致した。

| 公式由来の層 | バイト | SHA-256 |
| --- | ---: | --- |
| common.dl.snap.ubuntu.std.live.squashfs | 793,112,576 | `247e5d1e254bf330c016f8ef03d8c6a680c9a30cb8966d38acf382895c8a39d4` |
| common.dl.snap.lubuntu.std.live.squashfs | 28,471,296 | `30c5efea15785345d87da46940ad1a214d1625fdbecf3e0db392f358c893b2db` |
| common.server.std.live.squashfs | 27,041,792 | `e4979d60b157762250a731f8b9421dc7a95772c3f76950951caac7f160f9f67e` |
| common.server.std.live.generic.squashfs | 98,304 | `88eb0e16bda194f8df95baccecba7fd72ae26b0b05c6b2c58bfa2f57361912ad` |

全14層のハッシュとサイズは `build/work/logs/r2b-roundtrip.json`。
公式ISOのSHA-256は `r2b-inputs.json`、公式MD5とlive層のSHA-256は `r2b-live.json` に保存した。

### Lubuntuの設定層

設定層 `common.dl.snap.lubuntu.std.live.install.squashfs` は **4,517,888 バイト**。
unpackfsは common、common.dl、snap、lubuntu、std の順。
common・common.dl・lubuntuは無条件、snap・stdは `installation_data.unpack_regular` が真のときだけ展開する。
live層と設定層は設置先へ展開しない。白抜き蘇生とxattr補正は含めていない。

bootrepoの実行手順 `bootrepo-apt.sh` と `before_bootloader_context.conf` は既存スクリプトの原文とバイト一致した。
最小repoは公式Lubuntu ISO由来の5 deb。各debの公式MD5も一致した。
**既存手順との相違:** 指定されていた6本目の `grub2-common_2.14-2ubuntu2.1_amd64.deb` は公式Lubuntu ISOのpoolに存在しなかった。
このdebだけをrepoから除いた。`grub2-common 2.14-2ubuntu2.1` が設置用Lubuntu std層のdpkg状態で
`install ok installed` であること、および既存の依存検査が前提とする18パッケージすべての導入済み状態を実物から確認した。
repoの依存検査は合格した。実際のapt導入はR4で確認する。
設定層のファイル構成・5 deb・2設定原文・導入済み依存の版は `r2b-extra-verification.json` に保存した。

### カタログ・親・GRUB

- 3 OSのleafからドットを削った親が全て実在し、chainsの各行と親順が一致した。
- カタログ4項目をRuby/PsychでYAMLとして解析し、pathと設置用連鎖の実測合計が一致した。
- `ubuntu-server` だけがdefault。Lubuntuはカタログに含めていない。
- GRUBは3 OS × 通常・safe graphics・toramの9起動項目。元の生成器とleaf以外の文全体が一致した。
- `bootkit.os`、initrd、toramだけの追加cpio、`$bootkit_extra`、既存のUEFI補助2項目を保持した。
- .diskの3 OS UUIDは公式からの抽出原本とISOからの再抽出物がバイト一致した。

| 設置カタログ | leaf | 連鎖の合計バイト |
| --- | --- | ---: |
| ubuntu-server-minimal | common.server.squashfs | 1,335,111,680 |
| ubuntu-server (default) | common.server.std.squashfs | 1,491,410,944 |
| ubuntu-desktop-minimal | common.dl.snap.ubuntu.squashfs | 3,432,247,296 |
| ubuntu-desktop | common.dl.snap.ubuntu.std.squashfs | 4,022,300,672 |

### 起動の連鎖とRAM複写量

層本体だけの合計。すべて公式比+5%以内。ramselの余裕64MiB等は含まない。

| OS | 層数 | 実測バイト | 公式バイト | 差 | 公式比 |
| --- | ---: | ---: | ---: | ---: | ---: |
| ubuntu | 6 | 4,815,413,248 | 4,815,302,656 | +110,592 | +0.002297% |
| lubuntu | 7 | 3,762,163,712 | 3,757,625,344 | +4,538,368 | +0.120778% |
| server | 5 | 1,518,551,040 | 1,518,555,136 | -4,096 | -0.000270% |

### LBAと起動情報

`-find … -exec sort_weight 100 --` で起動ファイルを優先し、その他を0とした。
合成ISOの既知の正常な2ファイルで、優先度100はLBA 33、優先度0はLBA 34となることを先に実測した。
実ISOの優先ファイル792件は、最初の大きな層のLBA **165,665** より前に全領域が収まった。
以下は2048バイト/sector、終了LBAは占有する最後のsector。

| 対象 | 開始LBA | 終了LBA |
| --- | ---: | ---: |
| /boot/ (非空ファイルの範囲) | 1,278 | 8,146 |
| /EFI/ (非空ファイルの範囲) | 163,602 | 165,664 |
| /.disk/ (非空ファイルの範囲) | 1,273 | 1,277 |
| /boot/grub/grub.cfg | 5,031 | 5,032 |
| /boot/grub/efi.img | 1,278 | 3,851 |
| /boot/grub/i386-pc/eltorito.img | 5,267 | 5,282 |
| /casper/vmlinuz | 155,156 | 163,601 |
| /casper/initrd.ubuntu | 108,530 | 155,154 |
| /casper/initrd.lubuntu | 11,744 | 59,858 |
| /casper/initrd.server | 59,859 | 108,529 |
| /casper/bootkit-ramsel.cpio.gz | 9,535 | 9,537 |
| /casper/common.dl.snap.lubuntu.std.live.install.squashfs | 9,538 | 11,743 |

全ファイルのLBAは `r2b-lba.json` と `r2b-lba.log`。
El ToritoはBIOS=5267、UEFI=1278。boot.catalogの1 sector、validation checksum、BIOS bootableフラグを確認した。
GRUB2 MBRの位置値は21072、GRUB内部の位置値は21073で、実際のBIOSイメージLBAと一致。
boot-info-tableの位置・長さ・チェックサムも一致した。
公式から持ち込んだ起動関係629ファイルは、位置補正が必要なBIOSイメージの該当部分を除いてSHA-256が一致した。
BIOSイメージは補正箇所以外のバイト一致も確認した。

PVDはlittle/big endianとも4,320,185 sectors、実ファイル 8,847,738,880 バイトと完全一致した。
offset=16の副PVDとの整合も確認した。`fix-pvd.py` は実行したが、今回の新規ISOには補正不要だった。
ボリューム名は `Ubuntu-Merge 26.04.1 amd64`。system areaはGRUB2 MBR。
El ToritoのBIOS・UEFIイメージは存在する。GPTは作成されていない。
`r2b-iso-structure.log`、`r2b-boot-catalog.json`、`r2b-grub-pointers.json`、`r2b-casper-list.log` が証拠。

### poolとServer dists

poolは3公式ISOの和集合358ファイル、2,389,027,846バイト。同一パスで内容が衝突する物は0。
ISO内の全358ファイルの実データを公式md5sum.txtと照合し、一致した。
各ファイルのMD5・SHA-256・サイズは `r2b-pool-roundtrip.json` に保存した。
distsはServer公式の原本だけを収録し、署名を含む通常ファイル全件のSHA-256と、
`stable -> resolute`・`unstable -> resolute` の両symlinkが一致した。
desktop・LubuntuのdistsはISO直下に入れていない。

### 回帰試験と実行

`tests/test-ubuntu-merge.sh` にR2bの合成試験を追加した。
GRUBと旧版のleaf以外の一致、chainsとドット親、4項目のYAML・合計、Lubuntuの5展開条件、bootrepo原文流用を検査する。
`make test` の終了値は0。通常と空白・ピリオド入りのコピーの双方で合格した。
`ventoy/ramsel/verify-qemu.py` は期待表の層名と実測サイズだけ更新した。QEMUは実行していない。

```sh
sh tools/ubuntu-merge/assemble_stages.sh > build/work/logs/r2b-run-final.log 2>&1
TMPDIR="$PWD/build/work/tmp" PYTHONDONTWRITEBYTECODE=1 \
  python3 -u -I .agent-handoff/verify-r2b-extra.py \
  > build/work/logs/r2b-extra.log 2>&1
TMPDIR="$PWD/build/work/tmp" PYTHONDONTWRITEBYTECODE=1 \
  BOOTKIT_CASE_STAGE="$PWD/build/work/cs" make test \
  > build/work/logs/r2b-make-test.log 2>&1
```

### 失敗と対処

1. 設定層の初回生成は、既存手順が参照するgrub2-commonのdebが公式Lubuntu ISOに無く停止した。
   公式のmd5sum.txtとpool一覧で欠落を裏取りし、実物のdpkg状態で導入済みの同じ版を確認した。
   このdebだけを除いた5本で再生成し成功した。設定2原文は変更していない。
2. 初回ISOの追加確認で、GRUB2の位置値が不整合と判明した。公式GRUB2 MBRへ既存手順の
   `-isohybrid-mbr` (SYSLINUX用) を使ったため、MBR位置値21068は必要な21072と異なり、
   GRUB内部も公式元の2697のままだった。xorrisoのローカルhelpで専用指定を確認し、
   `--grub2-mbr` と `--grub2-boot-info` に変更した。初回のISOは削除してから作り直した。
   最終ISOは位置値・チェックサムを追加検査して合格した。

それぞれ1回の失敗後に原因を裏取りして修正。同じ原因の連続失敗はない。
初回の証拠は `r2b-install-attempt1.log`、`r2b-run-attempt1.log`、`r2b-bios-attempt1.json`、
`r2b-attempt1-*` に保存した。最終ISOは1個だけ残した。

### 容量管理と後始末

1秒間隔とハッシュの各読取ブロックで空きを検査した。観測最小は **24,780,800,000 バイト** (**23.078918 GiB**) で、下限18GiBを上回った。
記録は `r2b-space.jsonl`。pool・抽出live・initrd・設定層の生成staging・再抽出物を含む
`build/work/r2b/` と追加照合用の `build/work/r2b-extra/` は、成功後に削除した。
合成ISOと疎ファイルfixtureも削除した。ログ・設置用9層・最終ISO・手順は保持した。

## 残課題

R4の起動・設置検証は未実施。通常・safe graphics・toram、BIOS・UEFI、各設置選択、
Lubuntuのaptとbootloader、媒体検出の実動作は未確認。
今回の合格は静的検証まで。QEMU・USBへの書き込みは行っていない。

## 影響範囲

- 新規: `assemble_stages.sh`、`assemble_stages.py`、`stages_layout.py`、`grub_stages.py`、
  `build-lubuntu-stages.sh`、`test_stages_layout.py` (いずれも `tools/ubuntu-merge/`)。
- 新規: `tools/offline-install/install-sources-relayer.yaml`、`lubuntu-unpackfs-stages.conf`、この報告。
- 変更: `tests/test-ubuntu-merge.sh` のR2b試験追加、`ventoy/ramsel/verify-qemu.py` の期待表。
- 生成: 最終ISO、`build/work/logs/r2b-*`、`.agent-handoff/` の計画・追加照合・報告生成手順。
- 既存の `assemble.sh` の出力名・場所・挙動は変更していない。R1/R1b/R2a由来の変更は保持した。
- 作業ツリー外への書き込み、ネットワーク通信、QEMU、USB書き込み、git add、git commitは行っていない。
