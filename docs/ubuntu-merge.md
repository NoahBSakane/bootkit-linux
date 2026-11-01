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

5 層の合計は 6,920,290,304 バイト(6.45GiB)。本物の主要 10 層の合計
10,088,198,336 バイト(9.40GiB)に対して 3.17GB の削減である。

起動の連鎖(`casper/bootkit-chains/<os>.list`。親から子の順。T2 との
インターフェースで変えない):

- Ubuntu (`bootkit.os=ubuntu`): `common.squashfs`、`common.dl.squashfs`、
  `common.dl.ubuntu.squashfs`。`layerfs-path=common.dl.ubuntu.squashfs`
- Lubuntu (`bootkit.os=lubuntu`): `common.squashfs`、
  `common.dl.squashfs`、`common.dl.lubuntu.squashfs`
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
下層サブツリーを隠す。whiteout は使わない(各 OS の各パスは連鎖中の
ちょうど 1 層に入る)。

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
desktop・Lubuntu の設置は未検証である。

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
- Ubuntu desktop・Lubuntu の設置は未検証である。

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
