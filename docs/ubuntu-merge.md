# Ubuntu Merge (案 B2):共通の層を共有する統合 ISO

公式の Ubuntu desktop・Lubuntu・Ubuntu Server(いずれも 26.04.1 amd64)を、
共通の層を共有する 1 つの ISO に統合する。3 つの OS を別々に持つ案
(B1)は採らない。各 OS の起動では、その OS の層の列だけが RAM に載り、
載る量は本物の ISO の層の合計と同じ程度に収める。

## 層の割り当て

各 OS の層(起動に使う squashfs の列)は次のとおり。同一ディレクトリ
(`/casper`)に置き、leaf の名前をドットで短くしていって親を探す
casper の `layerfs-path` の規則に従う。

| 層ファイル | 内容 | 使う OS | 層のサイズ |
| --- | --- | --- | --- |
| `common.squashfs` | 3 OS で同一のファイル(パス・種別・内容・モード・所有者・xattr・リンク先が一致) | 全部 | 1,297,666,048 |
| `common.dl.squashfs` | desktop と Lubuntu だけに同一であるファイル | Ubuntu・Lubuntu | 472,125,440 |
| `common.dl.ubuntu.squashfs` | Ubuntu の残り(固有 + desktop-Server 共通の複製) | Ubuntu | 2,952,462,336 |
| `common.dl.lubuntu.squashfs` | Lubuntu の残り(固有 + Lubuntu-Server 共通の複製) | Lubuntu | 1,980,141,568 |
| `common.server.squashfs` | Server の残り(固有 + 両共通の複製) | Server | 217,894,912 |
| `common.dl.lubuntu.install.squashfs` | Lubuntu の設置用上書き層。`unpackfs.conf`・白抜きの蘇生・xattr 補正・bootloader 用の小さな署名なし repo・context 修正を 1 層に統合した物。ISO の追記で足すもので、層の再生成の対象外 | Lubuntu | 7,507,968 |

土台 5 層の合計は 6,920,290,304 バイト(6.45GiB)。本物の主要 10 層の
合計 10,088,198,336 バイト(9.40GiB)に対して 3.17GB の削減である。
Lubuntu の追記 1 層は 7,507,968 バイトである。

起動の連鎖(`casper/bootkit-chains/<os>.list`。親から子の順。T2 との
インターフェースで変えない):

- Ubuntu (`bootkit.os=ubuntu`): `common.squashfs`、`common.dl.squashfs`、
  `common.dl.ubuntu.squashfs`。`layerfs-path=common.dl.ubuntu.squashfs`
- Lubuntu (`bootkit.os=lubuntu`): `common.squashfs`、
  `common.dl.squashfs`、`common.dl.lubuntu.squashfs`。
  設置用の追記をした ISO では末尾に `common.dl.lubuntu.install.squashfs`
  が付いた 4 層になり、`layerfs-path` はその leaf を指す。
  追記前の ISO の起動項目は土台の leaf のままで起動できる
  (`tools/ubuntu-merge/grub.py` の既定。追記スクリプトだけが
  `BOOTKIT_LUBUNTU_LEAF` で統合層の leaf を渡す)
- Server (`bootkit.os=server`): `common.squashfs`、`common.server.squashfs`

範囲の定義:各 OS の「全層」は次の主要層だけを指す。desktop の言語・
secureboot 派生層(`minimal.de` など 38 層)は対象外で、統合 ISO には
入れない。明示した `layerfs-path` の連鎖への影響と言語選択の制約は
「言語・enhanced-secureboot 派生層」で述べる。

- Ubuntu: `minimal` ← `minimal.standard` ← `minimal.standard.live`
- Lubuntu: 同名 3 層
- Server: `ubuntu-server-minimal` ← `.ubuntu-server` ← `.installer`
  ← `.installer.generic`

重ねの意味は overlayfs と同じで、上層の非ディレクトリは同パスと
下層サブツリーを隠す。土台 5 層の連鎖中では各 OS の各パスはちょうど
1 層に入り、whiteout は使わない。ただし公式の live 層由来の whiteout
(char/block 0,0)が leaf 層に残る (Lubuntu 86・Ubuntu 81。`unsquashfs -ll`
の種別数えで実測)。いずれも overlay の表示では消えた形になり、起動の
見た目には出ない。設置への影響は「OS インストールの検証」で述べる。

共有できない重複の扱い:desktop と Server だけに共通のファイル
(非圧縮 24MB、約 8MB 相当)と Lubuntu と Server だけに共通のファイル
(非圧縮 70MB、約 25MB 相当)は、層を増やす費用と比べて複製する。
層の木では両立しない集合(共通集合が包含関係にない)は共有できない。
重複の合計は圧縮後で約 33MB で、ISO 全体(約 10GB)の 0.4% 未満である。

ハードリンク(nlink>1)のパスとデバイスへのハードリンク先は、
inode の共有を保つため共有対象から外して各 OS の leaf に入れる。
デバイスとその peer は同じ層に同居させる。

## 層の作り方

層は本物と同じ圧縮・ブロックサイズ(xz、128KiB)で作る。
macOS では root なしで所有者・デバイスノード・xattr を展開できない
ため、展開物のメタデータは使わず、次で再現する:

- 実体(通常ファイル・symlink・fifo)は `unsquashfs` で取り出す。
  case-sensitive な作業場所が要る(terminfo など大文字小文字だけが
  違う同名がある)。デバイス・ソケットとデバイスへのハードリンクは
  展開せず疑似で作る。
- `unsquashfs -pf -` のメタデータ部を `tools/ubuntu-merge/pf2pseudo.py`
  で `mksquashfs -pf` 用に変換する(D/R/S→M、C/B 作成、L→M または
  疑似への L、x 維持。根 `/` は除き `-force-uid 0 -force-gid 0` で付ける)。
- M 行は raw パス順(親が子より先)に並べる。子より後だと mksquashfs
  が自動生成の親と「違う定義」とみなして無視する。
- `-pseudo-override` で所有者を上書きする。macOS 由来の
  `com.apple.*` xattr は `-xattrs-exclude` で除く。

各層の `.manifest`・`.size` などは `casper/bootkit-meta/<os>/` に
そのまま保存する(インストーラの検証用。起動には使わない)。

## 同一性の検証

`make verify-ubuntu-merge` が各 OS について、本物の全層を重ねた
ビューと新しい層の連鎖を重ねたビューを比べる。比較項目はパス集合・種別・モード・所有者・xattr・symlink 先・通常ファイルの
SHA-256・デバイス番号で、時刻は数えるだけで合否に使わない。検証は ISO の
中身から取り出した層について行い、`tests/test-ubuntu-merge.sh` に再構成の
合成試験がある。

検証の結果(制御条件。組み立てた `build/layers` でも ISO から
取り出した層でも同じ):

- Ubuntu: 228,781 パス一致、差 0(時刻の扱いを除く差 0)
- Lubuntu: 302,726 パス一致、差 0(時刻差 18,075)
- Server: 110,345 パス一致、差 0(時刻差 14,015)

時刻差は共有化の副作用で、下層に共通ファイルが降りた OS に出る
(Ubuntu は 0)。合否には使わない。

## ISO の組み立て

`tools/ubuntu-merge/assemble.sh` で作る。載せる物:

- `/casper`: 新層 5 個、3 つの initrd(`initrd.ubuntu`・`initrd.lubuntu`・
  `initrd.server`)、共通の `vmlinuz`(3 ISO で同一ハッシュ)、
  `bootkit-chains/`、`bootkit-meta/`、`bootkit-ramsel.cpio.gz`
- `/boot/grub`: desktop の物を土台に 9 項目(3 OS × 通常・toram・
  safe graphics)。各項目は `bootkit.os=<os>` と層の leaf を指す
  `layerfs-path=`、`initrd` を渡す。toram 項目だけ公式 initrd の後ろに小さな
  `bootkit-ramsel.cpio.gz` を連結し、選択複写を行う。`live-media-path` は
  既定(casper)。`bootkit_extra` は任意の診断引数用で、通常は空。
- `/EFI`、`.disk/`(info は統合の名前。casper-uuid は 3 OS の値を個別保存)、
  `pool/`(3 OS の和集合。同パスは同サイズを確認済みで競合なし)。
  `--no-pool` で pool なし版も作れる。
- BIOS(El Torito + MBR)・UEFI(El Torito Alt-Boot + GPT)の起動レコードを収録する。
  実 ISO は UEFI の 3 OS と、SeaBIOS / CD-ROM の Lubuntu・Ubuntu toram で起動確認済み。

素の casper の `toram` は ISO 全体を RAM に載せる。本 ISO の toram 項目は
`ventoy/ramsel/` の premount で選んだ連鎖だけを複写し、元媒体を外す。
通常と safe graphics の項目には追加 cpio を渡さない。

既存 ISO は `xorriso -dev ... -map ... -boot_image any replay` で差分だけを
追記する。層・pool のコピーや ISO 全体の作り直しは行わない。xorriso 1.5.8
の追記で確認した primary PVD の volume size の 2^22 sector 単位の巻戻りは、
`fix-pvd.py` が partition_offset=16 の secondary PVD と実ファイルサイズを
照合し、既知の差だけを 8 バイト補正する。不明な不整合は止める。
新規作成は層をハードリンクして段階物の容量を抑える。

統合 ISO (`build/ubuntu-merge-26.04.1-amd64.iso`) は 9,654,042,624 バイト。
公式 3 ISO の合計 13,337,823,232 バイトに対し 3,683,780,608 バイト
(27.62%)小さい。起動設定の追記を含む実ファイルの大きさである。
既存 ISO の更新は起動設定と cpio が対象で、層・pool の再生成は新規組立で行う。

現行の統合 ISO は、ramsel の画面メッセージを ASCII 英語にした追加 cpio
(`casper/bootkit-ramsel.cpio.gz`)へ差し替えたもので、9,655,549,952 バイト、
SHA-256 `48d88241cfab4a78f1d104319185a69c038fc988e2cfac5de9e708c81731ad51`。
差は cpio と ISO のボリューム情報だけで、層・pool・`grub.cfg` は不変
(casper 183 件・pool 589 件の名前と大きさを照合)。下記の起動・Ventoy・
オフラインインストールの検証は、差し替え前の ISO
(SHA-256 `761b156da9d45fd9b666d6a6cb42dd4fd1e961063c8a7bfeab6937ba560a7d04`)
で行った。差し替え後の ISO では、Lubuntu の RAM 不足の停止画面(VGA で英語の理由を表示)と、
Server の toram・取り外し後の全層読み出し・Python・APT を QEMU で確認した。

各 OS の連鎖の合計(起動でその OS の層の列として RAM に載る量。
選択複写の対象):

- Ubuntu: 4,722,253,824(本物の層合計 4,815,302,656 の 98.07%)
- Lubuntu: 3,749,933,056(本物の層合計 3,757,625,344 の 99.80%)
- Server: 1,515,560,960(本物の層合計 1,518,555,136 の 99.80%)

いずれも本物の合計の +5% 以内である。

## 起動の確認

2026-10-29、QEMU x86_64 / TCG / OVMF で統合 ISO を CD-ROM として接続し、
GRUB の通常・toram 項目を選択した。証拠は `build/evidence/B2/`。
serial 用の `console=` 等を `bootkit_extra` に追加し、画像も照合した。

| OS | 通常項目の画面 | toram 項目の画面 | toram の tmpfs 使用量 (バイト) | ISO 排出後 |
| --- | --- | --- | --- | --- |
| Server | subiquity / shell を確認 | subiquity / shell を確認 | 1,515,585,536 | toram は読出し・プログラム起動成功、通常は I/O エラー |
| Lubuntu | LXQt を確認 | LXQt を確認 | 3,749,957,632 | toram は読出し・プログラム起動成功、通常は I/O エラー |
| Ubuntu | GNOME ログイン画面を確認 | GNOME live セッションを確認 | 4,722,278,400 | toram は読出し・プログラム起動成功、通常は I/O エラー |

通常・toram のいずれも、その OS の連鎖だけが overlay の lowerdir と loop の
参照先になり、他 OS の層は重ならない。toram の `/cdrom` は tmpfs で、
層合計に対する余分は各 OS とも 24,576 バイト。`pool/`、他 OS の層、
initrd は複写されていない。`findmnt`・`/proc/mounts` に元の sr0 mount はなく、
`losetup -a` の層の参照先も tmpfs 内だけだった。

QEMU の `eject -f cd0` で ISO の裏付けファイルを外し、`info block` で空に
なったことを記録した。toram はキャッシュを落とした層の読出し、新規 Python、
`apt-get check` が成功。通常項目は同じ排出後、新規プログラムや層の読出しが
I/O エラーになる。3 OS とも選択した全 loop の全体を読んだ。

| 証拠の接頭辞・画像 | 内容 |
| --- | --- |
| `server-normal-v3` | 通常の subiquity / 2 層 / 排出対照 |
| `server-toram-delivery` | toram の subiquity / tmpfs / 排出後の操作 |
| `lubuntu-normal-lxqt.png` | 通常項目の LXQt。serial 診断 shell を追加した起動 |
| `lubuntu-normal-eject` | 通常項目の 3 層 / 排出対照 |
| `lubuntu-toram-gui-final` | 最終 ISO の toram / LXQt / tmpfs / 排出後の全 3 層読出し |
| `ubuntu-normal-gui` | 通常項目の GNOME ログイン画面 / 3 層 |
| `ubuntu-normal` | 通常項目の排出対照 |
| `ubuntu-toram-gui-final` | 最終 ISO の toram / 3 層 / 排出後の操作。画面は `-after-eject.png` |

通常項目の記録は追加 cpio の最終更新前のもので、通常項目はその cpio を
読まない。toram は最終 ISO でも 3 OS を再測定した。
Lubuntu の起動プロンプトでは Try Lubuntu を選択して LXQt へ進んだ。
通常項目のライブユーザー名は統合 `.disk/info` の先頭語により `ubuntu`。
Lubuntu 通常の画像取得時は `systemd.debug_shell=ttyS0` と serial-getty の
マスクを診断用に追加し、層と graphical.target は変えていない。

RAM 不足は Server toram / 1,280MiB の VM で、必要 1,582,669,824 バイトに
対し利用可能 1,028,845,568 バイトと理由を表示し、複写前に initramfs shell で
停止した (`server-short-1280`)。媒体参照での起動続行はしていない。
Ubuntu / 4,096 MiB と Lubuntu / 3,072 MiB も複写前の停止と serial の理由を
確認した。必要量・利用可の実測値は [RAM 選択複写](ubuntu-ramsel.md) に記載。
当時の停止画面は日本語で VGA では文字化けした。画面メッセージは ASCII
(英語) に変更した。VGA での表示は未確認。
1,024MiB の別実行は initrd の展開中に write error で止まり、本処理に
到達しなかった。この結果は選択複写の RAM 判定の証拠に含めていない。

媒体検出の修正: casper 26.04.2 の `is_casper_path` は casper 内の squashfs /
ext2 / dir を確認する。`.disk/info` と `bootkit-chains` はこの検査には使わない。
通常の探索では `matches_uuid` が initrd の `/conf/uuid.conf` と
`.disk/casper-uuid*` を照合する。元の統合 ISO には desktop の UUID しかなく、
Server / Lubuntu は一致しなかった。3 OS の値を個別保存後は実関数で全 OS が
一致し、Server の CD 接続で媒体検出と起動を確認した (`uuid-control.txt`)。
UUID 照合の無効化や casper 本体の置換はしていない。

公式 ISO の素の toram との量の比較は [RAM 選択複写](ubuntu-ramsel.md) を参照。
この量の比較は、公式 ISO が元の kernel / initrd と BIOS direct、統合 ISO が UEFI / GRUB である。
Ventoy 1.1.18 経由の検証は [Ventoy QEMU 検証](ventoy-qemu.md)を参照。
GRUB2 モードで ISO 内の GRUB と追加 cpio を使い、3 OS の選択複写・
USB 取り外し後の全層読出し・Python・APT が成功した。Server の残留 mapper
のログ上のエラーと、通常起動モードの制約は同記録に明記している。
Ventoy / BIOS は Server の toram と取り外しも確認した。
UEFI safe graphics の Server は 4,096 MiB で subiquity の言語選択画面まで到達し、
`/proc/cmdline` の `nomodeset` を確認した (`build/evidence/e-quick/server-safe*`)。
Lubuntu も 6,144 MiB で Try 選択後の LXQt と `nomodeset` を確認した。
Ubuntu も 8,192 MiB で GNOME Live デスクトップと `nomodeset` を確認した。
SeaBIOS / CD-ROM の Lubuntu・Ubuntu toram は各対象 3 層だけを複写し、tmpfs 使用量は
各 3,749,957,632 / 4,722,278,400 バイト。全層読出し・Python・APT が成功した。
詳細と証拠は [RAM 選択複写](ubuntu-ramsel.md) を参照。
実機・Secure Boot は未検証。
新規 ISO 組立経路の全体は今回再実行せず、既存 ISO の
差分更新を実施した。最終 ISO の SHA-256 は
`761b156da9d45fd9b666d6a6cb42dd4fd1e961063c8a7bfeab6937ba560a7d04`
(`build/evidence/B2/iso.sha256`)。`make test` 全件合格、
`verify-merge-delivery.log` はこの最終 ISO からの 3 OS 比較も差 0。

## 言語・enhanced-secureboot 派生層

公式 desktop の派生 squashfs は 38 個、合計 243,068,928 バイト。
`minimal.de` などと `minimal.standard.de` など、および enhanced-secureboot
の各派生である。casper 26.04.2 の `setup_overlay` は `layerfs-path` があれば
leaf の名前からドットを削って親を列挙する。指定 leaf が
`minimal.standard.live` なら使うのは主要 3 層だけで、言語による追加選択や
兄弟の言語層の追加はしない。公式 desktop initrd の
`conf/conf.d/default-layer.conf` 自体もこの live leaf を既定にしている。
従って公式 desktop の既定起動も主要 3 層だけである。
`LAYERFS_PATH` が無い分岐は全 squashfs を
列挙するため、この結論は明示した leaf の起動に限る。

派生層は翻訳の追加だけではない。実物の `minimal.en`・`minimal.no-languages`
の一覧には 0:0 character device (overlay の whiteout) があり、他言語用の
フォントや apt 関連ファイルなどを削る。単純に 1 層を追加して本物の主要
3 層と同一のビューを保つ方式ではないため、今回は追加しない。

`install-sources.yaml` は `locale_support: langpack`、`preinstalled_langs`
(de/en/es/fr/it/pt/ru/zh と空値)、通常・enhanced-secureboot の variation を
持つ (実物は `casper/bootkit-meta/<os>/casper-meta/` に保存)。
日本語の派生層と ja の事前インストール指定は公式 ISO にも無い。
主要層には `usr/share/locale/ja/` の 27 レコードと Noto CJK のフォント 4 個が
あり、これらは統合層の同一性検証の対象で保持する。casper が既定起動で載せる
日本語関連ファイルは、派生層の省略によって減らない (層ビュー比較済み)。
日本語 GUI 表示・入力・インストーラの言語選択は未実測である。

統合 ISO の `bootkit-meta` に元のカタログを保存しても、元の
`minimal.*` は再層化した名前と一致しない。元のカタログをそのまま使った
OS インストールや enhanced-secureboot の選択は検証対象外である。
派生を全部保存するだけなら 243,068,928 バイトの追加だが、再層化に合わせた
各カタログ・派生パスの変換と別の同一性検証が必要で、小さな 1 層追加の
範囲を超える。根拠は保存済み casper 26.04.2 ソース、公式カタログ、
`build/evidence/B2/language-{layers,en-tree,none-tree}.txt`。

## OS インストールの検証 (オフライン)

### 目的と結果の要約

Server は、統合 ISO からネットワークなしで設置し、素の単独起動で serial と
VGA (tty1) の両方に `login:` が出て `ubuntu` で入れる。`dpkg --audit` は sudo
あり・なしとも無出力・終了 0、`apt-get check` は終了 0、GUI
(`ubuntu-desktop`・`gdm3`・`gnome-shell`) は不在、`getcap /usr/bin/ping` と
`/usr/bin/mtr-packet` はともに `cap_net_raw=ep` である。確認日は 2026-11-02、
QEMU x86_64 / TCG / OVMF、RAM 2,048MiB、複製 ISO の SHA-256 は
`cdad754da04ea793b1330de4ca22ef7520acb3d03ccf2fd679050a0917b56293`、
seed (`seed11.iso`) の SHA-256 は
`7017278b681cc6ca319dcfa85b7634fb722cc3ac6fd5fcbcc665a8fc16491221` である。
証拠は `build/evidence/install-sources/xfix/server-xfix11*` である。Ubuntu
desktop の設置は未検証である。Lubuntu の設置は次節で述べる。

### 設置の仕組み

ISO への追記は次の 3 点である。いずれも既存 ISO の複製への差分追記だけで、
層・pool の再生成や ISO 全体の作り直しはしない。入力 ISO 自体には書かない。

- `/casper/install-sources.yaml` (方式 (a): 1 つのカタログに複数 OS の項目を
  ID つきで入れる。Server は `source: {id: ubuntu-server}` で選ぶ)。
  原文は `tools/offline-install/install-sources.yaml` である。subiquity は
  起動時に同パスを探し、無ければ組込みの legacy 項目
  (`path=/media/filesystem`、`type=cp`) へ落ちて設置が失敗するため、
  再層化に合わせたカタログを置く。
- 公式 Server ISO の `/dists` (署名つき原本)。live の cdrom.sources が
  `file:///cdrom` の pool を指すため、これが無いと標的内の `apt-get update`
  が終了 100 で失敗する。
- xattr 補正層 3 個 (次項)。

道具と再現の手順は次のとおり。各追記の直後に `fix-pvd.py` で PVD 補正し、
roundtrip を照合する。

- `sh tools/ubuntu-merge/add-xfix-layers.sh <複製ISO>`:
  補正層 3 個を 1 回の xorriso 起動でまとめて写す。追記と補正を分けると
  primary PVD の volume size の巻戻りで次の xorriso が像を読めなくなる。
- `sh tools/ubuntu-merge/add-install-sources.sh <複製ISO> [カタログ]`:
  カタログを `/casper/install-sources.yaml` へ写す。
- `sh tools/ubuntu-merge/add-server-dists.sh <複製ISO> <公式ServerISO>`:
  公式 Server ISO の `/dists` を抜粋して写す。
- `python3 -I tools/ubuntu-merge/xfix-build.py`・`xfix-verify.py`・
  `xfix-audit.py`: 補正層の構築・検証・不一致の全数調査。
- `sh tools/offline-install/make-xfix-seed.sh <user-data> <meta-data>
  <out-seed.iso> [extra-file]`: seed (CIDATA) の ISO 化。
  user-data の原文が正本で、この道具は ISO 化だけを行う。
- `python3 tools/offline-install/server-autoinstall.py --iso <複製ISO>
  --seed <seed.iso> --disk <空qcow2> --prefix <接頭辞>`:
  QEMU x86_64 / TCG / OVMF、`-net none`、RAM 2,048MiB (既定)、
  空 qcow2 20GB で自動設置する。

カタログの `size` は層の連鎖の合計である (Server は 1,297,666,048 +
217,894,912 + 49,152 = 1,515,610,112)。再現の記録は
`build/evidence/install-sources/xfix/rebuild11-*.log`、
最終 SHA-256 は同 `rebuild11-final.sha256` である。

### xattr 補正層

原因は `tools/ubuntu-merge/inventory.py` の xattr 値の空白割りで、
`security.capability` が 5 バイトに欠けたことである。設置の
`stage-extract` の `rsync -aXHAS` がこの読み取りで EINVAL となり失敗する。
欠けの修正と回帰試験は `tests/test-ubuntu-merge.sh` にある。

不一致の全数 (`tools/ubuntu-merge/xfix-audit.py` で公式 10 層と統合 5 層を
棚卸しし、OS ごとに可視ビューで突き合わせ。証拠は
`build/evidence/install-sources/xfix/mismatch.json`):

- `security.capability`: 2 パス (`usr/bin/ping`・`usr/bin/mtr-packet`。
  公式 20 バイトに対し統合 5 バイト)。3 OS の連鎖すべて
  `common.squashfs` にある。
- `trusted.overlay.origin`: 54 ディレクトリ
  (統合側の再構成時の付帯値)。
- `trusted.overlay.impure` と通常 xattr の不一致は無い。

設置を壊すのは能力値だけである。curtin は層を loop で載せて overlay で
重ね、`rsync -aXHAS` で標的へ写す。overlay 越しの読み取りでは
`trusted.overlay.*` は核が横取りして写らないため、通常 xattr の能力値だけが
通る。

補正層は OS ごとの leaf の子で、casper のドット規則で親の連鎖を導出する
(例: `common.server.xfix.squashfs` → `common.server` → `common`)。
中身・モード・所有者・時刻は統合層の版のまま、xattr だけ公式の可視値で
置く。共通層 (`common.squashfs`) にある不一致は各 OS の補正層に複製して
入れる。検証は `tools/ubuntu-merge/xfix-verify.py` で連鎖 + xfix の可視
xattr と公式の全件一致、中身は `cmp` で公式・統合と一致である。

| 補正層 | 直すパス数 | 大きさ (バイト) |
| --- | --- | --- |
| `common.server.xfix.squashfs` | 21 (通常ファイル 2 + dir 19) | 49,152 |
| `common.dl.ubuntu.xfix.squashfs` | 28 (通常ファイル 2 + dir 26) | 49,152 |
| `common.dl.lubuntu.xfix.squashfs` | 11 (通常ファイル 2 + dir 9) | 49,152 |

起動項目には反映しない。`layerfs-path` と `bootkit-chains` は変えず、
起動は従来のままにする。補正は設置の連鎖だけに効く。
カタログの Server 項目の `path` だけを `common.server.xfix.squashfs` にする。

### 設置先の後処理(暫定策)

OS ごとの leaf 層が installer・live 層の内容を含むため、設置先に混ざる。
casper が initrd に入ると live の媒体を探して止まり、subiquity の自動起動と
serial-getty の drop-in が `login:` を塞ぐ。根本の解決は、設置元の層から
installer・live 由来を分ける再層化である。seed の late-commands による
後処理は OS ごとの保守が要る暫定策である。

seed の late-commands (確定形。原文は
`tools/offline-install/server-xfix-user-data.yaml` と
`server-xfix-meta-data.yaml`。各々に `echo CMDn_RC=$R` の終了記録付き) は
次の 9 件である。

- CMD0: casper の purge (`/target` へ proc/sys/dev を載せて
  `chroot /target apt-get purge -y casper`)。
- CMD1: initramfs の casper conf 2 件の削除。
- CMD2: installer 層だけの一覧 (`installer-only-paths11.txt`。3,554 件。
  `/var/lib/dpkg/info/` は除外) の `/target` からの一括除去。seed ISO 内の
  別ファイルとして同梱し、CIDATA ラベルで mount して読む。
- CMD3: `update-initramfs -u -k all` での initrd の再生成。
- CMD4: 再生成した initrd に casper が無いことの確認。
- CMD5: 一覧の残存数の報告 (報告のみ)。
- CMD6: subiquity 由来 3 単位の直接 mask (`/dev/null` への symlink)。
- CMD7: `multi-user.target.wants` 側の subiquity の symlink 除去。
- CMD8: mask と wants の検証。

一覧の作り方は `tools/ubuntu-merge/installer-only-paths.py` である。公式
Server ISO の installer 2 層にだけ在る全パスを列挙する (下 2 層に在るパスと
上書き分は除く)。原文は
`build/evidence/install-sources/xfix/installer-only-paths11.txt` である。
`/var/lib/dpkg/info/` 以下の 75 件は一覧から除く (除かないと標的の台帳が
消え、`dpkg --audit` が installer 由来 14 包の `.list`・`.md5sums` 欠落を
報告する)。除いた一覧は 3,554 件である。seed の late-commands の組み立ては
`tools/offline-install/make-bulk-user-data.py` である。

採らなかった方式: `systemctl mask` は設置環境の chroot では使えず
(終了 1 で無変更のため)、unit 本体を `/dev/null` への symlink で直接 mask
する。該当 14 包の purge は `initramfs-tools` (起動に要る) 等を削るため
採らない。

残る差: 公式の 2 設置層との manifest 突き合わせ
(`build/evidence/install-sources/xfix/target11-manifest-diff.txt`) では、
共通 708 包・版差 0・標的側のみ 20 件 (UEFI 向け 6 件 + installer 由来 14
件) である。ファイルでは `/etc/cloud` が残り (16,713 バイト・16 件。
設置器用設定なし)、`/etc/default/grub` の live 由来 cmdline が残る
(`autoinstall ds=nocloud` 付き。核は無視するため起動への害なし)。
subiquity の snap 本体は一括除去で消え、`/var/lib/snapd/snaps` には
core24・hwctl・snapd の 3 件のみ残る。標的の事後調査は
`tools/offline-install/target-ls.py` で qcow2→raw 化して読み取り専用で読む
(`target11-survey.txt`)。

### 既知の制約と未検証

- 対話インストールの選択画面に他 OS の項目が出る (未検証)。
- Ubuntu desktop 用の dists は Release が衝突するため未対応である。
- Minimal 構成 (`unpack_regular` 偽) は未検証である。
- sudo なしの `dpkg --audit` は、一覧に `/var/lib/dpkg/info/` を含めた構成で
  は終了 2、除いた構成では無出力・終了 0 だった。除いた構成の実測は 1 回
  だけで、sudo なしの終了 2 の原因(権限か台帳か)は未特定である。
- `verify-installed-extra.py` の `dpkg-l` (全文 `dpkg -l`) は巨大出力で
  完了行が取れず exit 1 になる (検査器側の欠陥。要約の `TOTAL=726` は
  取れた)。
- Ubuntu desktop の設置は未検証である。

### 検証の道具

`tools/offline-install/` の各道具の説明は次のとおり。証拠の置き場は
`build/evidence/install-sources/` である (seed 等の ISO は `*.iso` で git の
対象外。現行では `build/` 全体が未追跡)。

- `server-autoinstall.py`: 統合 ISO から Server を autoinstall で標的
  ディスクへ入れる (第 1 起動)。
- `server-inspect.py`: 統合 ISO の Server live を起動し、ファイル経由で
  操作・調査する。
- `server-shell.py`: 統合 ISO の Server live を debug shell で起動し、
  操作・調査する。
- `verify-installed.py`: 標的ディスク単独で起動し、設置結果を検証する
  (第 2 起動)。`--kernel`・`--initrd`・`--append` で直接核起動もできる。
- `verify-installed-extra.py`: 標的ディスク単独で起動し、xfix 由来の
  追加検査を行う (第 2 起動の続き)。
- `target-ls.py`: qcow2/raw 内の ext4 を読み取り専用で読む
  (sudo・macFUSE 不要)。
- `make-server-seed.sh`・`make-xfix-seed.sh`・`make-bulk-user-data.py`:
  seed と user-data の生成。

### Lubuntu の設置 (Calamares、オフライン)

#### 結果の要約

統合層での設置は 2026-11-02 に完走し、再起動後の検証まで通った。
入力 ISO (`ubuntu-merge-26.04.1-amd64.iso`) の SHA-256 照合後に APFS
クローンで複製し (`48d88241cfab4a78f1d104319185a69c038fc988e2cfac5de9e708c81731ad51`)、
追記スクリプトで統合層を足した ISO
(`b4ce3f06c6e29a1ea77a2fc44ea284dee816e49a34ea6661b4501574c6d93537`、
9,664,593,920 バイト) から、`-net none`・空 qcow2 20GB・RAM 4,096MiB・
GRUB の Lubuntu 通常項目で起動し、Calamares で Erase disk
(EFI 300MiB + `lubuntu_2604` 19.71GiB ext4)・利用者 test/testbox・
`test1234` の条件で設置した。設置は 04:12 開始 → unpackfs (4 展開元) →
dracut → `contextualprocess@before_bootloader` (自作 apt の 5 指名が通過) →
grubcfg・bootloader・packages と進み、`completion: succeeded` (43/43) で
終わった。標的ディスク単独の起動では GRUB → dracut → SDDM と上がり、
SDDM には UBUNTU (`installer` 利用者) と TEST の 2 欄が出る
(既定セッションは live のまま)。
TTY3 で test/`test1234` ログインし、`startx /usr/bin/startlxqt` で LXQt の
デスクトップ (壁紙・Computer/Network/test/Trash・下パネル・時計) を確認した。
`dpkg --audit` は無出力、`sudo apt-get check` は Done で E: 行なし
(終了 0 相当) である。`gnome-shell`・`ubuntu-server` は `un`、
`ubuntu-desktop`・`subiquity` は該当なしで、GNOME/Server の混入は無い。
`getcap /usr/bin/ping`・`/usr/bin/mtr-packet` は `cap_net_raw=ep` である。
live 由来の残りは `installer` 利用者 (uid 1001。dpkg の所有なし) と
`/home/installer`、live セッション定義
(`/usr/share/xsessions/lubuntu-live-environment.desktop`)、
`/pool` (`main`)・`/dists` (`resolute`。約 7MB。不活性)、
`calamares` (`ii` 3.3.14)・`casper` (`ii` 26.04.2) である。
`dracut` は dpkg 上 `un` だが実行体は統合層の蘇生分 (129,932 バイト) で
設置段は通った。`libboost-python1.90.0` は `ii` で入っており、
8 層時代の「不在」の記録は包名の差し (`1.90` と `1.90.0`) による。
証拠は `build/evidence/lubuntu-install/` の `install7-*` (画面指紋・設置ログ)
と `boot7-*` (標的起動の記録) である。

#### 追記と設置の手順

ISO への追記は次の 3 点である。いずれも既存 ISO の複製への差分追記だけで、
層・pool の再生成や ISO 全体の作り直しはしない。入力 ISO 自体には書かない。

- `/casper/common.dl.lubuntu.install.squashfs` (設置用上書き層。次項)。
- `/casper/bootkit-chains/lubuntu.list` (親から子の 4 行。
  `common.squashfs`、`common.dl.squashfs`、
  `common.dl.lubuntu.squashfs`、`common.dl.lubuntu.install.squashfs`)。
- `/boot/grub/grub.cfg` (`tools/ubuntu-merge/grub.py` の再生成。
  追記スクリプトが `BOOTKIT_LUBUNTU_LEAF` で統合層の leaf を渡す。
  既定は土台の leaf のままで、追記前の ISO は従来どおり起動できる)。

toram の選択複写は連鎖の一覧 (`lubuntu.list`) を読むだけで、層の数に
依存しない。統合層の名前は `valid_layer_name` の規則
(`*.squashfs` で使える文字だけ) に収まり、4 層の連鎖を扱える。
toram 項目での設置自体は未検証である。

道具と再現の手順は次のとおり。追記の直後に `fix-pvd.py` で PVD 補正し、
roundtrip を照合する。

- 入力 ISO の SHA-256 照合後に APFS クローンで複製する
  (`cp -c`。複製前後で SHA-256 が一致することを記録する)。
- `sh tools/ubuntu-merge/add-lubuntu-install-layer.sh <入力ISO> <複製ISO>`:
  設置用上書き層の構築・検証・追記を 1 回の起動で行う。pool の deb は
  入力 ISO から読む。追記後の SHA-256 と大きさを記録する。
- `python3 -I tools/offline-install/lubuntu-calamares-install.py
  --iso <複製ISO> --disk <空qcow2> --prefix <接頭辞> --mem 4096`:
  QEMU x86_64 / TCG / OVMF、`-net none`、空 qcow2 20GB で GRUB の
  Lubuntu 通常項目から起動し、Try 選択後のデスクトップで Calamares を
  起動する。Welcome まで自動で進み、以降は画面ごとに手動で進める。
- 設置後は標的ディスク単独で起動し、LXQt のログイン・`dpkg --audit`・
  `apt-get check`・GNOME/Server の不在・`getcap` を見る。

再現の記録は `build/evidence/lubuntu-install/` に置く (追記層の構築記録
`install-build.log`、複製前後の SHA-256、設置の画面指紋、標的起動の記録)。

#### 層の構成

設置用上書き層は 7,507,968 バイト・661 パスである。中身と目的は次の
とおり。起動の overlay・toram 複写・unpackfs 展開の順はどれも親から子の
4 層で一致する。

- `etc/calamares/modules/unpackfs.conf`:起動の overlay と同じ順の 4 展開元
  (原文 `tools/offline-install/lubuntu-unpackfs-install.conf`)。
  先頭だけ無条件で、残りは通常の選択のときだけ展開する
  (`installation_data.unpack_regular` は pkgselect が立てる)。
- 白抜きの蘇生:live の leaf 層の whiteout (char/block 0,0) で Server 層に
  実体がある物 (dracut 一式など 67 パス) を Server 層から抜いて同梱し、
  leaf の whiteout を上書きして蘇らせる。写しだと標的で実行不能になる
  (dracut 段が終了 126 で失敗する)。実体がどの層にも無い物
  (dpkg の dracut 付属文書の一部など) は入れない。
- xattr 補正 11 パス:統合層の `security.capability` の値の切れ
  (`usr/bin/ping`・`usr/bin/mtr-packet` の公式 20 バイトに対し統合
  5 バイト) を公式値で上書きし、unpack の `rsync -X` で欠落した 2 ファイル
  の実体を補う。公式値の出所は
  `tools/ubuntu-merge/lubuntu-xfix-official.json` である。
  中身・モード・所有者・時刻は統合層の版のまま、正しい xattr だけ公式の
  可視値で置く。whiteout は使わない。
- `/pool`・`/dists`:bootloader の deb だけの最小 repo
  (`grub-efi-amd64-signed`・`grub-efi-amd64-bin`・`grub-efi-amd64-unsigned`・
  `grub2-common`・`shim-signed`・`efibootmgr` の 6 deb +
  `dists/resolute` の索引) を層に同梱し、live の overlay 上の
  `/pool`・`/dists` を `file:///` の素性 (`Trusted: yes`) で読む。
  `contextualprocess@before_bootloader` が `grub-efi-amd64-signed` 等を
  標的へ入れるのに要る。統合 ISO に pool が無いと `apt-get update` が
  終了 100 になり、後の段が全部飛ぶ。deb の出所は入力 ISO の `/pool`
  (読むだけ) で、依存の閉包は repo 内と統合層の既設で閉じること
  (不足があれば中断する)。`Release` の `Date` は C ロケールで書く
  (ja ロケールの `%a %b` は apt が `Invalid 'Date'` と警告する)。
- `etc/calamares/modules/before_bootloader_context.conf`:手順本体を層内の
  `bootrepo-apt.sh` に置き、conf 側は短い `sh ...` 呼び出し 1 行だけに
  する。YAML の素朴な値に `:`+空白を含めると yaml-cpp が
  `illegal map value` で読めず、Calamares が起動時に初期化失敗するため。
- `etc/calamares/bootrepo-apt.sh`:`file:///` 素性の更新と bootloader 用
  5 指名 (`grub-efi-amd64-signed`・`grub-efi-amd64-bin`・
  `grub-efi-amd64-unsigned`・`shim-signed`・`efibootmgr`) の導入。
  `--no-upgrade` は残して live の既設を変えない。指名漏れの新規依存は
  入らないため、既設に無い物は指名に含める
  (層の道具が指名集合の推移閉包を検査する)。

層の道具 (`add-lubuntu-install-layer.sh`) の検査は次のとおり。
stage と層に whiteout (char/block 0,0) が無いこと、補正 11 パスの xattr が
公式値と一致すること、中身が統合層と一致すること (ping・mtr-packet を
`cmp`)、指名集合の推移閉包が live 既設・repo 内・指名自体で閉じること、
`Release` の `Date` の形式、conf の 4 展開元、`bootrepo-apt.sh` の 5 指名と
`--no-upgrade` の保持である。追記後は ISO から取り出した層・list・grub.cfg
と追記前の物を `cmp` で照合する。

#### 白抜きの実測

公式の live 層由来の whiteout (char/block 0,0) が leaf 層に残る。
入力 ISO から `unsquashfs -ll` の種別数えで実測した値は Lubuntu 86・
Ubuntu 81 である。いずれも overlay の表示では消えた形になり、起動の
見た目には出ない。Lubuntu の 86 のうち Server 層に実体がある 67 を
設置用上書き層で蘇らせ、上書きの順が overlay と同じため設置先は
通常ファイルになる。残りはどの層にも実体が無い物で、標的に残っても
設置の成否基準には触れない。

#### live・installer 由来の混入の一覧と量

公式 Lubuntu の設置元は live 層そのものを含むため、Calamares に live 由来物
を消す後処理 (`try_remove`) は無く、unpack した連鎖分の live 由来が標的に
入る。公式 manifest の差分では live だけの 44 包がある
(`build/evidence/lubuntu-install/live-only-packages.txt`。
`busybox-initramfs`・calamares 一式・casper・`lubuntu-installer-prompt`・
initramfs 一式・`user-setup` など)。Server の公式 installer 層のような
分離は Lubuntu の公式層に無く、この manifest 差分が除去一覧の代替になる。
設置先ディスクの実測では、`installer` 利用者 (GECOS `Ubuntu`、shell
`/usr/bin/subiquity-shell`。dpkg の所有なし) と `/home/installer`、
live セッション定義
(`/usr/share/xsessions/lubuntu-live-environment.desktop`)、
`/pool`・`/dists` (約 7MB。不活性) が残る。`/casper` は標的に無い。

#### 既知の制約

- SDDM の既定セッションが live 環境のままである。LXQt には手動で
  `Lubuntu.desktop` を選ぶ必要がある。live 定義の除去・既定の固定は
  未実施である。
- toram 項目での設置は未検証である (設計上は連鎖の一覧を読むだけで
  通る見込み)。
- Minimal 構成 (`unpack_regular` 偽) は未検証である。
  (`unpack_regular` が偽のとき ping の capability 欠けが残る見込み。)
- `libboost-python1.90.0` は設置先に `ii` で入っている。8 層時代の
  「不在」の記録は包名の差し (`1.90` と `1.90.0`) による見落としで、
  統合層での再確認で解消した。

#### 設置の検証の道具

`tools/offline-install/` の各道具の説明は次のとおり。証拠の置き場は
`build/evidence/lubuntu-install/` である (現行では `build/` 全体が
未追跡)。

- `lubuntu-calamares-install.py`:統合 ISO から Lubuntu を Calamares で
  標的ディスクへ入れる (第 1 起動)。GRUB の Lubuntu 通常項目を選び、
  Calamares の Welcome まで自動で進める。
- `lubuntu-guest-probe.py`:稼働中の QEMU に monitor+serial で接続し、
  ゲストの現状を読む。画面も撮る。QEMU は残して終了する。
- `uinput-click.py`:ゲスト内で uinput ポインタを作り、真座標に 1:1 で
  動かして押す。ウィザードの選択・入力に使う。
- `lubuntu-whiteout-rescue.py`:Lubuntu の leaf 層の whiteout のうち
  Server 層に実体がある物を列挙する。
- `lubuntu-xfix-official.json`:補正 11 パスの公式値
  (中身の出所の層と xattr)。
