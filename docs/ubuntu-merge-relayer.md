# Ubuntu Merge: 再層化版の統合 ISO

公式の Ubuntu Desktop・Lubuntu・Ubuntu Server 26.04.1 amd64 を、設置用の
9 層を共有する 1 つの ISO に統合する。設置する内容と live 環境でだけ使う内容を
分け、公式の Minimal と Normal を再構成できる構造にしている。
Server と Lubuntu は、Normal・Minimal の計 4 通りでオフライン設置と設置後の
単独起動を確認した。Ubuntu Desktop の設置は未実施である。

確認日は 2026-11-05。以下の数値は圧縮後のファイルサイズをバイト単位で示す。
非圧縮の内容量とは区別する。

| 項目 | 値 |
| --- | --- |
| ISO | `build/ubuntu-merge-26.04.1-amd64-relayer.iso` |
| 大きさ | 8,847,738,880 バイト、8.240099 GiB |
| SHA-256 | `fe3bcfbece3e262bf3fea9720d3f47e44fe183afe0a808be7f6afec911342f14` |
| 設置用の層 | 9 本、合計 5,269,733,376 バイト |
| 起動専用の追加層 | 公式 live・installer 4 本と Lubuntu 設定層 1 本 |

ISO のサイズと SHA-256 は実物で再確認した。R2b 報告の SHA-256
`78e19917ceb0373f1037f9b937149fce612bfb82d2020f0f304a6417b61cad35` は、
Lubuntu のブートローダー準備を直す前の値である。上表は R4b 報告と実物が一致する
修正後の値で、サイズは修正前後で同じである。生成時刻などを固定する仕組みはなく、
再生成した ISO 全体がこのハッシュになることを保証する手順ではない。

旧 B2 設計は [旧設計の文書](ubuntu-merge.md)を参照する。
再層化版の設置層・カタログ・起動の鎖は、この文書と `*_stages` 系の道具を使う。

## 層の設計

### 設置用の 9 層

SquashFS は圧縮された読み取り専用ファイルシステムである。複数の層を下から
重ね、上の層の内容で同じパスを上書きする。ここでは各 OS の公式 minimal を
第 1 段、standard の差分を第 2 段として分ける。Server の第 2 段の公式名は
`ubuntu-server-minimal.ubuntu-server` である。

第 1 段の共有では、パス・種別・内容・モード・所有者・拡張属性(xattr)・
シンボリックリンク先・デバイス番号が同じものをまとめる。第 2 段は OS 別に
保持し、Normal だけに要る内容を Minimal の共通層へ混ぜない。

以下の層名にはすべて `.squashfs` が付く。設置用 9 本のサイズは実物を再確認した。

| 層名 | 内容 | 実測バイト |
| --- | --- | ---: |
| `common` | 3 OS の第 1 段で共通の内容 | 1,138,008,064 |
| `common.dl` | Ubuntu・Lubuntu の第 1 段で共通の内容 | 393,572,352 |
| `common.dl.snap` | Ubuntu の第 1 段と Lubuntu の第 2 段に共通の snap | 1,303,564,288 |
| `common.dl.snap.ubuntu` | Ubuntu の第 1 段の残り | 597,102,592 |
| `common.dl.snap.ubuntu.std` | Ubuntu の第 2 段 | 590,053,376 |
| `common.dl.snap.lubuntu` | Lubuntu の第 1 段の残り | 506,413,056 |
| `common.dl.snap.lubuntu.std` | Lubuntu の第 2 段から共有 snap を除いた内容 | 387,616,768 |
| `common.server` | Server の第 1 段の残り。Server 用 snap も含む | 197,103,616 |
| `common.server.std` | Server の第 2 段 | 156,299,264 |
| 合計 | 設置用 9 本 | 5,269,733,376 |

snap はアプリケーションの配布形式である。共有対象は bare・core24・firefox・
firmware-updater・gnome-46-2404・gtk-common-themes・mesa-2404・snapd の 8 組。
各 snap の `var/lib/snapd/snaps/` と `var/lib/snapd/seed/snaps/` は、同じ実体を
指すハードリンクになっている。全 16 パスを組ごと同じ層に入れ、実体 1 部の
合計 1,574,879,232 バイトを共有する。表の 1,303,564,288 バイトは層の圧縮後の値。

通常ファイルのハードリンクとデバイスの別名は、全メンバーを同じ層に置く。
OS ごとに組の構成が異なる場合は、無理に共有せず OS 別に組を保持する。
Server の snap は公式 minimal 側に在るため、`common.server` に保持する。
Server の鎖には `common.dl.snap` を入れない。

削除を表す特殊なエントリである whiteout(char 0,0)も、公式の standard の
各層に在るものは `.std` 層に保持する。「設置用の層に whiteout が一切無い」
という設計ではない。公式 live 層に在る whiteout を設置元へ混ぜずに済むことと、
公式設置元が持つ削除の意味を保持することを分けて扱う。

### 公式 live・installer 層と Lubuntu 設定層

live は試用環境、installer は設置プログラムの実行環境を指す。
次の 4 本は公式 ISO から抽出し、名前だけを変えて収録する。再圧縮はしない。
入力 ISO 全体の公式 SHA-256、各層の公式 `md5sum.txt`、収録後の再抽出物を照合済みで、
公式層とバイト単位で一致する。

| 公式の `/casper/` 内の層名 | 統合 ISO の層名 | 実測バイト |
| --- | --- | ---: |
| Ubuntu `minimal.standard.live` | `common.dl.snap.ubuntu.std.live` | 793,112,576 |
| Lubuntu `minimal.standard.live` | `common.dl.snap.lubuntu.std.live` | 28,471,296 |
| Server `ubuntu-server-minimal.ubuntu-server.installer` | `common.server.std.live` | 27,041,792 |
| Server `ubuntu-server-minimal.ubuntu-server.installer.generic` | `common.server.std.live.generic` | 98,304 |
| 合計 | 公式の 4 本 | 848,723,968 |

各層の SHA-256 は `build/work/logs/r2b-live.json` と R2b 報告にある。
さらに Lubuntu の最上層へ `common.dl.snap.lubuntu.std.live.install.squashfs`
(4,517,888 バイト)を足す。内容は Calamares の展開設定・ブートローダー準備の
設定とスクリプト・5 個の deb と小さな APT 索引で、設置先へは展開しない。
旧版の白抜き蘇生処理や xattr 補正層は使わない。

### casper のドット規則と 3 つの起動の鎖

casper は Ubuntu 系 live 環境の起動処理である。`layerfs-path` で最上層(leaf)を
指定すると、名前の末尾をドット単位で削って親を導く。たとえば
`common.server.std.live.generic` の親は `common.server.std.live`、
`common.server.std`、`common.server`、`common` となる。
同じ `/casper/` 内に親をそろえ、短い名前を下、長い名前を上に重ねる。

`casper/bootkit-chains/<os>.list` は、RAM 選択複写が読む起動層の一覧である。
各行は `.squashfs` 付きのファイル名、順序は下から上。ISO 内の一覧も照合済みである。

```text
# ubuntu.list
common.squashfs
common.dl.squashfs
common.dl.snap.squashfs
common.dl.snap.ubuntu.squashfs
common.dl.snap.ubuntu.std.squashfs
common.dl.snap.ubuntu.std.live.squashfs

# lubuntu.list
common.squashfs
common.dl.squashfs
common.dl.snap.squashfs
common.dl.snap.lubuntu.squashfs
common.dl.snap.lubuntu.std.squashfs
common.dl.snap.lubuntu.std.live.squashfs
common.dl.snap.lubuntu.std.live.install.squashfs

# server.list
common.squashfs
common.server.squashfs
common.server.std.squashfs
common.server.std.live.squashfs
common.server.std.live.generic.squashfs
```

上のコメントは 3 ファイルの区切りを示すもので、実ファイルには含まれない。
Lubuntu Minimal の設置だけは Calamares の明示的な展開一覧を使い、途中の
snap 層を省く。casper のドット規則で Minimal 用の起動を作るわけではない。
live 起動はどの OS も Normal の設置層まで含み、設置時の選択とは独立している。

| OS | 起動層数 | 起動の鎖の合計 | 公式主要層の合計 | 差 |
| --- | ---: | ---: | ---: | ---: |
| Ubuntu | 6 | 4,815,413,248 | 4,815,302,656 | +110,592 |
| Lubuntu | 7 | 3,762,163,712 | 3,757,625,344 | +4,538,368 |
| Server | 5 | 1,518,551,040 | 1,518,555,136 | -4,096 |

いずれも公式の合計の +5% 以内である。これは層本体の合計で、OS の実行用 RAM や
RAM 選択複写が確保する余裕は含まない。選択複写の仕組みは
[RAM 選択複写](ubuntu-ramsel.md)を参照する。

## 作り方

### 入力と作業領域

プロジェクト直下から実行する。必要な道具は Python 3、xorriso、squashfs-tools の
`unsquashfs`・`mksquashfs`、`ar`、`unzstd`、YAML 解析用の PyYAML または Ruby/Psych。
出力は `build/` に置く。`assemble_stages.py` の入力先 `SRC` は現在
`~/Downloads/ubuntu-merge-research-20261029` に固定されており、
別の環境ではこの定数を入力先に合わせる。コマンドラインの入力先指定はない。

| 入力 ISO | 照合済みの SHA-256 |
| --- | --- |
| `ubuntu-26.04.1-desktop-amd64.iso` | `601e30fbf5d97759367c632e2c33630665039b7e2158fd068403da3ccf1bda1f` |
| `lubuntu-26.04.1-desktop-amd64.iso` | `a8038585420f2270845549c6f493e0ec98e68d4b2c49571cbe500a4b5fab3062` |
| `ubuntu-26.04.1-live-server-amd64.iso` | `cc8a95cde20f6ced61a322420de00f10cc3c90ced545daa46cb9c1a117f1d927` |

入力フォルダには公式の `SHA256SUMS.*` も置く。組み立て時に ISO 全体を照合する。
根拠は `build/work/logs/r2b-inputs.json`。組み立て開始時は空き 32 GiB 以上が必要で、
層生成・組み立てとも処理中の空きが 18 GiB を下回ると停止する。

展開・層生成には大文字小文字を区別する(case-sensitive)作業領域が要る。
Linux の `Sys/` と `sys/` のような別パスを、大文字小文字を区別しない macOS の
領域に展開すると衝突するためである。`build/work/cs` をその領域として用意する。
`repack_stages.py` は実際に大文字小文字の違う 2 ファイルを作って条件を検査し、
満たさなければ止まる。通常のディレクトリをその名前で作るだけでは代用できない。

一連の処理を棚卸し・割り当て・生成・検証・組み立ての順に行う。
途中で差分や読み取り不能が出たら、その段階の原因を直してから先へ進む。
既存の `build/work/inv`・`plan`・出力層は、入力と一致するか確かめずに流用しない。

### 1. 設置元 6 層を抽出・棚卸しする

live・installer 層は割り当て計算へ入れない。下表の 6 本だけを `xorriso` で
`build/work/orig/<tag>.squashfs` に抽出する。

| 入力 ISO | `/casper/` 内の名前(拡張子省略) | tag |
| --- | --- | --- |
| Ubuntu | `minimal` | `d-minimal` |
| Ubuntu | `minimal.standard` | `d-standard` |
| Lubuntu | `minimal` | `l-minimal` |
| Lubuntu | `minimal.standard` | `l-standard` |
| Server | `ubuntu-server-minimal` | `s-minimal` |
| Server | `ubuntu-server-minimal.ubuntu-server` | `s-server` |

棚卸しは `inventory.py SQUASHFS TAG OUTDIR STAGEDIR` を使う。
通常ファイルの SHA-256 などを展開物から読み、所有者・モード・xattr・特殊 inode
などを SquashFS の疑似ファイル出力(`unsquashfs -pf`)から読む。macOS の展開先で
表せないデバイスとその別名は、`pf2pseudo.py --exclude-file` の一覧で展開から除く。
メタデータは元の SquashFS から保持する。

以下は `d-minimal` 1 本の操作例である。同じ手順を上表の 6 本に適用する。
作業用の展開先は毎回未使用のパスを指定する。

```sh
mkdir -p build/work/orig build/work/inv build/work/logs build/work/tmp
export TMPDIR="$PWD/build/work/tmp"
export PYTHONDONTWRITEBYTECODE=1
src=$HOME/Downloads/ubuntu-merge-research-20261029
sqfs="$PWD/build/work/orig/d-minimal.squashfs"
inv="$PWD/build/work/inv"
stage="$PWD/build/work/cs/inventory-d-minimal"
xorriso -indev "$src/ubuntu-26.04.1-desktop-amd64.iso" -osirrox on \
  -extract /casper/minimal.squashfs "$sqfs"
unsquashfs -pf - "$sqfs" > "$inv/d-minimal.pfmeta"
python3 -I tools/ubuntu-merge/pf2pseudo.py \
  --exclude-file "$inv/d-minimal.excl" \
  "$inv/d-minimal.pfmeta" "$inv/d-minimal.pseudo"
unsquashfs -processors 4 -no-progress -no-xattrs -d "$stage" \
  -exclude-file "$inv/d-minimal.excl" "$sqfs"
python3 -I tools/ubuntu-merge/inventory.py "$sqfs" d-minimal "$inv" "$stage"
```

出力は `<tag>.jsonl`・`.pf`・`.stats`。`.stats` の `missing_meta` が空で、
パス数が `pf_entries` と一致することを 6 本とも確かめる。
上の `.pfmeta` は通常ファイルのデータ部も含む大きな中間物なので、変換後は
保持を要しない。展開物も棚卸しが完了した層から片付け、容量を管理する。

R1 で使った `build/work/run-inventory-r1.sh` は、大文字小文字を区別しない領域で
棚卸ししたあとに `fixup_casefold.py SQUASHFS TAG INVDIR` で衝突分を取り直す
補助手順である。これは層生成用の case-sensitive 領域の代わりにはならない。
既存の `run-inventory.sh` は旧版の主要 10 層を対象にするため、そのままでは使わない。

### 2. 段ごとの割り当てと自己検証

```sh
python3 -I tools/ubuntu-merge/plan_stages.py build/work/inv build/work/plan
python3 -I tools/ubuntu-merge/verify_stages.py build/work/inv build/work/plan
```

`plan_stages.py` は `layers.json`(層ごとのパス・抽出元・メタデータ)、
`chains.json`(Minimal・Normal の鎖)、`ochains.json`(公式の対応)、`report.txt` を出す。
`verify_stages.py` は各ビューをドット規則の順で再構成し、公式の 6 ビューと
差 0、ハードリンクの層またぎ 0 を確認する。圧縮後サイズの見積もりは完成層の
実測ではないので、ISO のサイズやカタログの `size` には使わない。

### 3. 設置用の層を生成する

```sh
python3 -u -I tools/ubuntu-merge/repack_stages.py \
  build/work/plan/layers.json build/work/orig build/work/cs build/layers-stages \
  > build/work/logs/repack-stages.log 2>&1
```

必要なパスだけを元の層から展開し、疑似定義で所有者・デバイス・xattr を戻して
圧縮する。xz、ブロックサイズ 131,072 バイトで、通常ファイルのハードリンクは
組ごと共通の抽出元を選んで保つ。macOS の `com.apple.*` 属性は除く。
出力は 9 本の `.squashfs`、疑似定義の `.pseudo`、実測の `build-stats.json`。
既存の出力層は上書きしない。

R2a の実測は、部分展開・疑似定義・圧縮・生成用展開物の削除までの合計で
618.068 秒。棚卸しと回帰試験を並行した、その環境での値である。
処理中はログの更新とプロセスの状態を監視する。

### 4. 完成した層を棚卸しして比較する

完成した 9 層にも手順 1 と同じ棚卸しを行い、出力先を `build/work/inv-built`、
tag を拡張子なしの層名にする。特殊 inode は疑似出力で確認し、通常ファイルの
ハードリンクは case-sensitive 領域への展開後の inode でも確認する。
R2a の実行用補助は `.agent-handoff/inventory-r2a.py` に保存されているが、
この補助は当時の生成進捗ファイルを待つ作りなので、汎用の一括棚卸しとは区別する。

```sh
python3 -I tools/ubuntu-merge/verify_built_stages.py \
  build/work/inv build/work/plan build/work/inv-built \
  build/work/logs/verification-stages.json
shasum -a 256 build/layers-stages/*.squashfs \
  > build/work/logs/r2a-SHA256SUMS.layers
```

合格条件は、割り当てと完成層の差 0、公式との 6 ビューの差 0、リンクの層またぎ・
inode 不一致・余分な結合 0。最後のハッシュ一覧は組み立て側の入力にもなる。

### 5. live・設定・カタログ・起動設定を組み立てる

```sh
sh tools/ubuntu-merge/assemble_stages.sh \
  > build/work/logs/assemble-stages.log 2>&1
```

`assemble_stages.sh` は `assemble_stages.py` を呼ぶ。設置用 9 層のハッシュを
照合して組み立て領域へハードリンクし、公式 live・installer 層を抽出する。
`build-lubuntu-stages.sh` で設定層を作り、`stages_layout.py` で鎖とカタログを検査、
`grub_stages.py` で GRUB を生成する。設定層だけを生成する場合の引数は次の順。

```sh
sh tools/ubuntu-merge/build-lubuntu-stages.sh \
  "$src/lubuntu-26.04.1-desktop-amd64.iso" \
  build/work/lubuntu-config \
  tools/offline-install/lubuntu-unpackfs-stages.conf \
  build/work/lubuntu-config.squashfs
```

組み立ては完成 ISO と `build/work/r2b` が無い状態で始める。既存物があれば停止する。
出力は冒頭の ISO、検査記録は `build/work/logs/r2b-*`。
ISO 内から全 14 層を再抽出してハッシュを照合し、pool・dists・起動ファイル・
LBA・ボリューム情報も検査する。成功後は組み立て用の一時領域を削除する。

```sh
BOOTKIT_CASE_STAGE="$PWD/build/work/cs" make test
shasum -a 256 build/ubuntu-merge-26.04.1-amd64-relayer.iso
```

`make test` は通常パスと空白・ピリオド入りのパスで合成試験を行う。
case-sensitive 領域を環境変数で渡すのは、後者でも同じ有効な領域を使うためである。
旧版用の `make verify-ubuntu-merge` を、再層化版の 6 ビュー検証の代わりにはしない。

## ISO の構成

`/casper/` に全 14 層、共通の `vmlinuz`、OS ごとの `initrd.ubuntu`・
`initrd.lubuntu`・`initrd.server`、追加アーカイブ `bootkit-ramsel.cpio.gz`、
`bootkit-chains/`、公式のメタデータを保存した `bootkit-meta/` を置く。
`.disk/` は 3 OS の casper UUID を個別に保持する。UUID 照合を無効にせず、
各公式 initrd が元媒体を見つけられるようにする。

### 設置カタログ・dists・pool

`tools/offline-install/install-sources-relayer.yaml` を
`/casper/install-sources.yaml` に置く。4 項目とも `type: fsimage-layered` で、
`path` は設置用の最上層、`size` はドット規則で導かれる設置層の合計である。
`ubuntu-server` だけが既定。Lubuntu はこのカタログを使わない。

| ID | path | size |
| --- | --- | ---: |
| `ubuntu-server-minimal` | `common.server.squashfs` | 1,335,111,680 |
| `ubuntu-server` | `common.server.std.squashfs` | 1,491,410,944 |
| `ubuntu-desktop-minimal` | `common.dl.snap.ubuntu.squashfs` | 3,432,247,296 |
| `ubuntu-desktop` | `common.dl.snap.ubuntu.std.squashfs` | 4,022,300,672 |

ISO 直下の `/dists` は Server 公式の署名を含む原本だけを収録する。
`stable -> resolute`・`unstable -> resolute` も保持し、通常ファイルの全ハッシュを
照合している。Desktop・Lubuntu の dists は混ぜない。`/pool` は 3 ISO の和集合で、
358 ファイル・2,389,027,846 バイト。同一パスの内容衝突は 0、全ファイルの実データを
公式 MD5 と照合済みである。Lubuntu 設定層の `/dists`・`/pool` は、これとは別の
小さなブートローダー用リポジトリである。

### GRUB と起動ファイルの配置

GRUB の OS 起動項目は 3 OS × 通常・safe graphics・copy to RAM の 9 項目。
safe graphics は `nomodeset` を足す。copy to RAM は `toram` を足し、公式 initrd の
後ろへ追加 cpio を連結する。通常・safe graphics は追加 cpio を読まない。
`bootkit.os=<os>`、各 live 最上層への `layerfs-path`、対応 initrd、診断用の
`$bootkit_extra` を保持する。UEFI の場合は、このほかに次のボリュームへの移行と
ファームウェア設定の補助 2 項目がある。メニュー文字列は ASCII の英語である。

LBA は ISO 内の論理ブロックの番号で、ここでは 1 ブロック 2,048 バイト。
起動関係を優先度 100、それ以外を 0 として、大きな層より手前へ置く。
最初の大きな層 `common.squashfs` は LBA 165,665 から始まり、優先ファイル
792 件の占有領域はすべてその前に収まる。実物と `r2b-lba.json` を照合した。

| 対象 | 開始 LBA | 終了 LBA(占有する最後のブロック) |
| --- | ---: | ---: |
| `/.disk/` の非空ファイル全体 | 1,273 | 1,277 |
| `/boot/` の非空ファイル全体 | 1,278 | 8,146 |
| `/boot/grub/efi.img` | 1,278 | 3,851 |
| `/boot/grub/grub.cfg` | 5,031 | 5,032 |
| `/boot/grub/i386-pc/eltorito.img` | 5,267 | 5,282 |
| `/casper/bootkit-ramsel.cpio.gz` | 9,535 | 9,537 |
| Lubuntu 設定層 | 9,538 | 11,743 |
| `/casper/initrd.lubuntu` | 11,744 | 59,858 |
| `/casper/initrd.server` | 59,859 | 108,529 |
| `/casper/initrd.ubuntu` | 108,530 | 155,154 |
| `/casper/install-sources.yaml` | 155,155 | 155,155 |
| `/casper/vmlinuz` | 155,156 | 163,601 |
| `/EFI/` の非空ファイル全体 | 163,602 | 165,664 |

BIOS と UEFI の El Torito 起動イメージ、GRUB2 MBR を持つ。GRUB2 用の
`--grub2-mbr`・`--grub2-boot-info` で位置値を補正し、boot-info-table の
位置・長さ・チェックサムも検査する。実物には GPT は無い。
`fix-pvd.py` はボリュームサイズの整合を調べるが、今回の新規生成物は補正不要だった。
PVD(主ボリューム記述子)のサイズ 4,320,185 ブロックは、実ファイルサイズと一致する。

## 設置の仕組み

### Server

subiquity は設置カタログの ID を選び、その最上層までを展開する。
検証時の autoinstall は `source: {id: ubuntu-server}` または
`source: {id: ubuntu-server-minimal}` を指定した。
前者は `common`・`common.server`・`common.server.std`、後者は先頭の 2 層。
installer 2 層は live 起動には使うが、設置元には含めない。

検証用の seed は `build/evidence/relayer-r4b/server-*/user-data` にあり、
旧版の installer 専用パスの一括除去、casper purge、subiquity の mask といった
`late-commands` の後処理は含まない。ISO 直下の Server dists と pool を使い、
ネットワークなしで設置した。

### Lubuntu

Calamares は `lubuntu-unpackfs-stages.conf` を設定層の
`/etc/calamares/modules/unpackfs.conf` として読み、次の 5 展開元を順に処理する。
展開先はすべて設置先のルートである。

| 順番 | `/cdrom/casper/` 内の展開元 | 条件 |
| --- | --- | --- |
| 1 | `common.squashfs` | 常に展開 |
| 2 | `common.dl.squashfs` | 常に展開 |
| 3 | `common.dl.snap.squashfs` | `installation_data.unpack_regular` が真 |
| 4 | `common.dl.snap.lubuntu.squashfs` | 常に展開 |
| 5 | `common.dl.snap.lubuntu.std.squashfs` | `installation_data.unpack_regular` が真 |

Normal は 5 層すべて、Minimal は snap と std を除く 3 層を展開する。
その設置元の合計は Normal 3,729,174,528、Minimal 2,037,993,472 バイト。
live 層と設定層はどちらの選択でも展開しないため、設置プログラム自体や live 用の
設定・リポジトリを設置先へ持ち込まない。

ブートローダー準備の `before_bootloader_context.conf` は `dontChroot: true` を
指定し、live 側で `sh /etc/calamares/bootrepo-apt.sh ${ROOT}` を実行する。
chroot は指定ディレクトリをルートとしてコマンドを動かす仕組みだが、ここで
Calamares の既定どおり設置先へ入ると、展開していない設定層のスクリプトが見えない。

スクリプトは設置先を引数で受け取り、live 側の `/pool` と `/dists` を設置先へ
一時的に bind マウントする。同じファイルを別の場所から参照できるようにしたうえで、
`chroot` 内の APT に `file:///` の専用設定を渡す。リポジトリは `Trusted: yes` の
署名なしローカルリポジトリであり、ISO 直下の署名付き Server dists とは異なる。
終了時の処理でマウントと一時設定を取り除く。

収録する deb は `grub-efi-amd64-signed`・`grub-efi-amd64-bin`・
`grub-efi-amd64-unsigned`・`shim-signed`・`efibootmgr` の 5 本。
公式 Lubuntu ISO に deb が無い `grub2-common` は既設のものを使う。
依存パッケージの存在確認に加え、Normal・Minimal の再設置完了と設置後の
ブートローダー関連パッケージの存在を確認した。この手順の BIOS 分岐は何もしない設定で、
Lubuntu の BIOS 設置の実動作は未確認である。

## 検証の結果

### 静的検証

R1b の割り当て検証と R2a の完成層検証は、次の 6 ビューですべて差 0。
比較はパス集合・種別・モード・uid/gid・xattr の値全体・リンク先・通常ファイルの
SHA-256・デバイス番号。時刻とルートエントリは同一性の合否に含めない。

| ビュー | 公式パス数 | 完成層の再構成パス数 | 差 |
| --- | ---: | ---: | ---: |
| Ubuntu Minimal | 174,600 | 174,600 | 0 |
| Ubuntu Normal | 226,649 | 226,649 | 0 |
| Lubuntu Minimal | 271,261 | 271,261 | 0 |
| Lubuntu Normal | 292,847 | 292,847 | 0 |
| Server Minimal | 79,984 | 79,984 | 0 |
| Server Normal | 106,719 | 106,719 | 0 |

リンク辺 585 件と公式の通常ファイルのリンク組 53 件を確認し、不一致は 0。
完成層内の通常ファイルの 45 組はメンバー集合も一致した。
`security.capability` は公式 16 エントリ・完成層 12 エントリで、共有化による件数差を
含めビューとして一致し、値はすべて 20 バイトだった。

ISO の静的検証は全 14 層の再抽出ハッシュ、公式 live 4 層のバイト一致、
カタログ 4 項目、ドット規則と鎖、pool・dists、GRUB、LBA、起動イメージの位置値、
PVD の整合が合格。最終 ISO の値は `build/work/logs/r2b-verification.json` にある。
R4b 修正後の回帰試験は `r4b-space-test.log` の末尾で全試験成功・`exit=0`。
先行する `r4b-make-test.log` は case-sensitive 領域を渡さず失敗した記録なので、
成功の証拠とは区別する。

設置用 6 ビューの差 0 と公式 live 層のバイト一致は確認済みだが、再層化後の
live 全体を再棚卸しし、公式との 3 ビューの差 0 を直接示した記録は未確認である。
Lubuntu の live 全体には意図した設定層の追加もある。

### オフライン設置と設置後の中身

QEMU・UEFI、`-net none` で検証した。結果は R4b 報告、
`build/evidence/relayer-r4b/` の設置ログ・単独起動画面・検査記録に基づく。

| 対象 | 設置完了 | 設置後ディスクだけでの起動 | `dpkg --audit` | 追加確認 |
| --- | --- | --- | --- | --- |
| Server Normal | 完了 | 起動・ログイン | 空 | `apt-get check` 終了 0 |
| Server Minimal | 完了 | 起動・ログイン | 空 | `apt-get check` 終了 0 |
| Lubuntu Normal | 43/43 完了 | SDDM・LXQt に到達 | 空 | 通常項目の 3 回中 2 回でパニック |
| Lubuntu Minimal | 43/43 完了 | SDDM・LXQt に到達 | 空 | 通常項目の 1 回の起動は正常 |

Server の Normal・Minimal の設置済みパッケージ数はそれぞれ 713・508。
両方とも subiquity・casper・calamares・ubuntu-desktop・gnome-shell は無く、
GUI のセッションも無い。snapd と seed は Minimal にも在る。
Normal の `ping`・`mtr-packet` は `cap_net_raw=ep`、Minimal では両ファイルが無い。
`systemctl` の失敗サービスはネットワークなしでの wait-online のみ。
検査時の一般ユーザーからの `dmesg` は権限不足で読めていない。
根拠は `verify/sn.extra.txt` と `verify/sm.extra.txt`。

Lubuntu の比較は `lubuntu-installed-inspection.txt` による。live ISO から
設置後ディスクを読み取り専用でマウントし、`dpkg --admindir` で問い合わせた。

| 項目 | Normal | Minimal |
| --- | --- | --- |
| 設置済みパッケージ数(ii) | 1,972 | 1,658 |
| snapd・seed の snap | あり、8 個 | なし |
| grub-efi-amd64-signed・shim-signed・efibootmgr | あり | あり |
| sddm・lxqt-core・cloud-init | あり | あり |
| casper・calamares・subiquity・ubuntu-desktop・gdm3・gnome-shell | なし | なし |
| 作成した利用者 | test のみ、installer 利用者なし | 同左 |
| `/pool`・`/dists`・`/etc/calamares`・`/cdrom`・`/rofs` | なし | なし |
| SDDM | TEST のみ、セッション Lubuntu | 同左 |
| `ping` の capability | `cap_net_raw=ep` | `cap_net_raw=ep` |

通常の Lubuntu・lxqt・openbox セッションは在るが、live 専用セッションは無い。
Server に在る `/var/log/installer` の設置ログや `/cdrom` などまで含めて、
すべての設置関連パスが無いという意味ではない。

### 起動と RAM 選択複写

R4a 報告書自体は Codex の事前確認で止まった記録である。
以下は CC が後続で残した `build/evidence/relayer-r4a/` の serial 原本、
transcript、画面と `build/work/logs/r4a-*.log` を読んで確認できる範囲を示す。
環境は QEMU x86_64、q35、TCG マルチスレッド、4 CPU、UEFI、CD-ROM、
ネットワークなし。診断用の serial console を GRUB の追加引数で指定している。

| OS・項目 | RAM(MiB) | 証拠の接頭辞 | 到達・画面の確認 | 媒体取り外し後 |
| --- | ---: | --- | --- | --- |
| Ubuntu 通常 | 8,192 | `ubuntu-normal` | shell・gnome-shell の PID。保存画像は黒画面 | コマンド読み出しが I/O エラー |
| Ubuntu toram | 8,192 | `ubuntu-toram` | shell・GNOME のログイン画面 | 6 層の全体読出し成功、Python・APT 成功 |
| Lubuntu 通常 | 4,096 | `lubuntu-normal2` | shell。保存画像は起動メッセージ | コマンド読み出しが I/O エラー |
| Lubuntu toram | 6,144 | `lubuntu-toram2` | shell。保存画像は起動メッセージ | 7 層の全体読出し成功、Python・APT 成功 |
| Server 通常 | 4,096 | `server-normal2` | shell・subiquity の言語選択画面 | コマンド読み出しが I/O エラー |
| Server toram | 4,096 | `server-toram` | shell・subiquity の言語選択画面 | 5 層の全体読出し成功、Python・APT 成功 |

各 OS の `/proc/cmdline`、overlay の `lowerdir`、loop の参照先は期待した鎖に一致する。
通常は `/cdrom` が `/dev/sr0` の ISO、toram は tmpfs で、他 OS の層や pool は
複写されていない。tmpfs は RAM 上のファイルシステムである。

| OS | 層本体の合計 | toram の `/cdrom` 使用量(`df -B1`) | 差 |
| --- | ---: | ---: | ---: |
| Ubuntu | 4,815,413,248 | 4,815,437,824 | +24,576 |
| Lubuntu | 3,762,163,712 | 3,762,188,288 | +24,576 |
| Server | 1,518,551,040 | 1,518,575,616 | +24,576 |

QEMU の `eject -f cd0` 後、`info block` の `cd0: [not inserted]` を記録している。
toram ではキャッシュを落として各 loop を全体読み出しし、`READ_LAYER_COUNT` が
6・7・5、`MEDIA_READ_RC=0`、Python の `PY_OK`、`APT_RC=0` を確認した。
通常は `losetup`・`awk` 自体が読み出せず、`READ_LAYER_COUNT=0`・
`MEDIA_READ_RC=1`・`APT_RC=126` となる。通常項目の各層を全体読み出しできた
記録ではなく、元媒体への依存が残ることの対照である。

R4a の Lubuntu 初回実行には LXQt プロセス待ちの失敗があり、`normal2`・`toram2` の
画像でも LXQt には到達していない。live GUI の成功とは判定しない。
Ubuntu toram の画像もログイン画面で、live デスクトップへのログイン完了とは区別する。
設置後の Lubuntu デスクトップの確認は、別の R4b の結果である。

R4a は R4b の設定層修正前の起動記録として扱う。各起動ログには ISO 全体の
SHA-256 が記録されておらず、最終ハッシュの ISO で同じ 6 条件を再実行した証拠は
未確認である。また、旧 B2 の safe graphics・SeaBIOS・Ventoy の結果を、
再層化版の検証済み項目へ移して数えない。

## 既知の制約と未検証

- Ubuntu Desktop の設置は `ubuntu-desktop`・`ubuntu-desktop-minimal` とも未実施。
  カタログの静的整合と live 起動の記録が、設置成功を意味するわけではない。
- toram 項目からの設置は未実施。媒体取り外し後の全層読出し・Python・APT の確認は、
  設置プログラムが追加データを要求する経路の検証を含まない。
- Lubuntu Normal の設置後ディスクを通常の GRUB 項目(`quiet splash`)で起動した
  3 回のうち 2 回で、約 4 分後に `KERNEL PANIC! Fatal exception in interrupt`
  が出た。3 回目は SDDM に到達し、別途 `quiet splash` を外して serial を足した
  起動と、その後の再起動では SDDM・LXQt に到達した。原因は未検証。
  TCG の実行や設置直後の状態との関係は仮説であり、確定原因ではない。
  証拠は `relayer-r4b/lubuntu-normal/boot-alone/`。
- Lubuntu Minimal の通常起動は 1 回のみ正常を確認した。Normal のパニックが
  Minimal や実機では起こらないとは判断できない。
- Calamares が Install Now 直後に終了した例が Minimal で 1 回ある。
  再起動して設置を完了したが、原因は未検証。
- R4a の live GUI 到達には上記の未確認がある。safe graphics、SeaBIOS、実機、
  Ventoy、Secure Boot 有効時の起動と設置は、この再層化版では未確認。
- 言語・enhanced-secureboot の派生層は収録せず、明示した主要層の鎖だけを使う。
  日本語 GUI 表示・入力や言語別の設置経路は未確認。派生層の意味と旧版での調査は
  [旧設計の「言語・enhanced-secureboot 派生層」](ubuntu-merge.md#言語enhanced-secureboot-派生層)
  を参照する。新カタログは 4 項目の簡略版で、旧版に記された公式カタログの
  言語・variation 設定をそのまま提供するものではない。

## 根拠と検証の道具

- 層の割り当てとドット規則: [R1 報告](../RELAYER-R1-REPORT.md)、
  [R1b 報告](../RELAYER-R1B-REPORT.md)、`plan_stages.py`・`verify_stages.py`。
  最終の割り当ては R1b と現行コードを使う。
- 完成した層の同一性: [R2a 報告](../RELAYER-R2A-REPORT.md)、
  `build/work/logs/r2a-verification.json`、`repack_stages.py`・`verify_built_stages.py`。
- ISO の構成: [R2b 報告](../RELAYER-R2B-REPORT.md)、
  `build/work/logs/r2b-*`。最終の ISO ハッシュは実物と R4b 報告を優先する。
- 起動: [R4a 事前確認報告](../RELAYER-R4A-REPORT.md)と、後続の
  `build/evidence/relayer-r4a/`。判定には transcript の完了行だけでなく serial の
  終了値と保存画像を使う。
- 設置: [R4b 報告](../RELAYER-R4B-REPORT.md)、`build/evidence/relayer-r4b/`。
  `tools/offline-install/` の `server-autoinstall.py`・`verify-installed-r4b.py`・
  `lubuntu-calamares-install.py`・`lubuntu-calamares-drive.py`・`lubuntu-guest-probe.py`
  が検証用の操作と採取を支援する。
- 回帰: `tests/test-ubuntu-merge.sh`、`test_repack_stages.py`・`test_stages_layout.py`。
  `ventoy/ramsel/verify-qemu.py` の期待層名とサイズも再層化版へ更新されている。
  期待表の更新自体は QEMU や Ventoy での実行結果ではない。

`build/` の記録と `.agent-handoff/` の補助はローカルの作業成果物であり、
ソースだけのチェックアウトでは別途用意する必要がある。
