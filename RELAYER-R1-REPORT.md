# R1 報告: 棚卸しと段別割り当ての計算

日付: 2026-11-04。作業場所: この作業ツリー(`build/work/`)。層・ISO は作っていない(`build/layers` なし)。

## 結論

- 設置元の 6 層の棚卸しが完了し、段別割り当て(`tools/ubuntu-merge/plan_stages.py`、新規)の自己検証(`tools/ubuntu-merge/verify_stages.py`、新規)が 6 ビューすべて差 0。
- 新層は 9 層。非圧縮の内容合計は約 17.08GB。圧縮後の見積もり(見積もり)は合計約 6.28GB。
- `common.dl.snap` は 8 組 16 道(非圧縮 3,149,758,464 バイト)。指示書の「8 個・1,574,879,232 バイト」は片側 1 部の合計と一致する。
- 段をまたぐ同一内容は snap 以外は 0 件。standard の段の OS 間重複は 8,795 組・17,660 件・539,291,099 バイト(段をまたぐ共有をやめることで戻る量)。

## 1. 棚卸し(入力と完全性)

入力 ISO(`~/Downloads/ubuntu-merge-research-20261029`、読み取りのみ)から設置元の 6 層だけを `build/work/orig/` に取り出し、`build/work/inv/` に棚卸しした(live・installer の 4 層は対象外)。

| 層 | 圧縮後(バイト) | 道数 | 通常ファイルの合計(バイト) |
| --- | --- | --- | --- |
| d-minimal | 3,432,136,704 | 174,600 | 9,055,157,103 |
| d-standard | 590,053,376 | 52,438 | 1,902,526,094 |
| l-minimal | 2,037,972,992 | 271,261 | 5,629,669,774 |
| l-standard | 1,691,181,056 | 22,201 | 4,310,775,364 |
| s-minimal | 1,335,115,776 | 79,984 | 3,693,927,179 |
| s-server | 156,299,264 | 27,912 | 542,078,888 |

完全性: 6 本とも `missing_meta` は空。`pf_entries` と道数が一致する。

注意(macOS 固有の補正): この Mac の作業場は大文字小文字を区別しないため、そのまま展開すると大文字小文字違いの別道(例: `usr/lib/.../perl/5.40.1/Sys/` と `sys/`)が衝突し、棚卸しが欠ける(d-minimal で 225 組 450 道)。大文字小文字を区別する像の作成はこの環境では許されなかった(`newfs` が拒否される)ため、新規の `tools/ubuntu-merge/fixup_casefold.py` で補正した。方針は pf(正・区別あり)を権威とし、衝突組の通常ファイルだけ `unsquashfs -cat` で実バイトを取り直す。衝突とハードリンクの絡みは無いことを層ごとに確かめている(絡めば打ち切り)。既存の `inventory.py`・`run-inventory.sh` は変更していない。R1 手順は `build/work/run-inventory-r1.sh` にある。

## 2. 新層の割り当て(件数と非圧縮の大きさ)

`python3 -I tools/ubuntu-merge/plan_stages.py build/work/inv build/work/plan` の `report.txt` と `layers.json` による。バイトは通常ファイルの内容合計(道・symlink・xattr の収まりは含まない)。

| 層 | 道数 | ファイル数 | 非圧縮(バイト) | 圧縮後の見積もり(バイト) |
| --- | --- | --- | --- | --- |
| common | 77,973 | 63,796 | 1,907,647,788 | 701,513,281 |
| common.dl | 37,149 | 27,024 | 1,088,711,967 | 400,360,019 |
| common.dl.snap | 22 | 16 | 3,149,758,464 | 1,158,283,729 |
| common.dl.snap.ubuntu | 60,989 | 38,573 | 2,909,038,884 | 1,069,762,156 |
| common.dl.snap.lubuntu | 157,579 | 89,012 | 2,633,310,019 | 968,366,363 |
| common.server | 2,153 | 1,576 | 1,786,279,391 | 656,881,592 |
| common.dl.snap.ubuntu.std | 52,438 | 47,093 | 1,902,526,094 | 699,629,843 |
| common.dl.snap.lubuntu.std | 22,185 | 18,775 | 1,161,016,900 | 426,949,241 |
| common.server.std | 27,912 | 21,165 | 542,078,888 | 199,342,636 |
| 合計 | 437,400 | 306,030 | 17,080,368,395 | 6,281,088,860 |

鎖(下から上へ):

- ubuntu minimal: common.dl.snap、common、common.dl、common.dl.snap.ubuntu
- ubuntu normal: 上に common.dl.snap.ubuntu.std を足す
- lubuntu minimal: common、common.dl、common.dl.snap.lubuntu(snap 層は含まない)
- lubuntu normal: common.dl.snap、common、common.dl、common.dl.snap.lubuntu、common.dl.snap.lubuntu.std
- server minimal: common、common.server
- server normal: 上に common.server.std を足す

段1の分け方(道数): 3 OS 同一 77,972、Ubuntu・Lubuntu 同一 36,245、Ubuntu 残り 60,367、Lubuntu 残り 157,044、Server 残り 2,006、Server の snap 6、snap 共有 16。ハードリンクの組の強制移動は 0 組(組は自然に 1 層に収まった)。ディレクトリの衝突の明示追加は 0 件。段1で 2 OS だけ同一の組(Ubuntu・Server 783 道 1,487,485,758 バイト、Lubuntu・Server 387 道 1,324,353,021 バイト、Ubuntu・Lubuntu 151 道 1,315,208,542 バイト)は新しい層の並びに 2 OS 共有が無いため OS 別に重ねて持つ。

## 3. 各段のビューの差(自己検証)

`python3 -I tools/ubuntu-merge/verify_stages.py build/work/inv build/work/plan` の結果。比較項目はパス集合・種別・モード・所有者・xattr・symlink 先・通常ファイルの SHA-256・デバイス番号。

- ubuntu minimal: 公式 174,600、新 174,600、差 0
- ubuntu normal: 公式 226,649、新 226,649、差 0
- lubuntu minimal: 公式 271,261、新 271,261、差 0
- lubuntu normal: 公式 292,847、新 292,847、差 0
- server minimal: 公式 79,984、新 79,984、差 0
- server normal: 公式 106,719、新 106,719、差 0
- ハードリンクの組の層またぎ: 0

Minimal(段1だけ)の再構成が公式の minimal 単体と差 0 であることから、段2の内容は段1の共有層に混ざっていない。ハードリンクの組はすべて 1 つの層内に全名前がそろっている。

## 4. `common.dl.snap` の内容

Ubuntu の段1と Lubuntu の段2に同一内容(パス・種別・内容・モード・所有者・xattr が一致)で在る snap 8 組。`var/lib/snapd/snaps/<名>.snap` と `var/lib/snapd/seed/snaps/<名>.snap` はハードリンクの組で、組の全名前を置く(16 道、両側の合計 3,149,758,464 バイト。片側 1 部は 1,574,879,232 バイト)。Lubuntu の段2の差分からは除いている(下の snap 層と重ねて同じになる)。

| 名前 | 1 部のバイト | SHA-256(両側共通) |
| --- | --- | --- |
| bare_5.snap | 4,096 | 03d0a2eb62e1b8861e557f7875f2d74f59f56c89ac0b4775fbe6d00c465fc84b |
| core24_1643.snap | 70,049,792 | 1c63b692a11edab44387e97911b9681d9010305cb9f9218c38bfbe2bedb50e45 |
| firefox_8763.snap | 272,957,440 | f29dcac9ba739c603454550b8ca6db2b0de6ce75a497148a4247824fe8254aeb |
| firmware-updater_226.snap | 17,301,504 | 2022fcb179cd02a8e8d26329f1e4e7bf8b3865467d5bbbefd0add8e497d6c6b9 |
| gnome-46-2404_164.snap | 644,382,720 | 42b7b1ef333784b7fb1c6188bd490b5f8e2fd52807a081e4591b8eb287b3f769 |
| gtk-common-themes_1535.snap | 96,141,312 | e64ec1ad03ac012ba3539a9e61cfe2007f102140dbb03a009e82a53fccf7f6a5 |
| mesa-2404_1839.snap | 421,507,072 | 8962b397993d74a452accdab3dc07696703d814ac480aa4fbeef5bde1a1dd236 |
| snapd_27710.snap | 52,535,296 | 62d5f40157079784d6aa78a1e41c894e078e71da6acb174005d5ce70bf15e630 |

core24 と snapd は Server の段1にも同一内容で在るため、Server 側の層(`common.server`)にも重ねて置いている(Server の段1の再構成に要るため。Server の鎖に snap 層は無い)。

## 5. 段をまたぐ同一内容(snap 以外)と standard の段の重複

- 段をまたいだ同一内容(snap 共有を除く): 3 OS とも 0 件 0 バイト。minimal と standard の両方に在る同名の道は Ubuntu 125 件・Lubuntu 96 件・Server 40 件あるが、内容(SHA-256)が一致する物は 1 件も無い。
- standard の段での OS 間の同一内容: 8,795 組・17,660 件・片側換算の重なり 539,291,099 バイト。この重なりが、段をまたぐ共有をやめることで戻る量である。

## 6. 現行の割り当て(`plan.py`)との比較

live・installer の 4 層を空にして `plan.py` を実行した結果(段をまたぐ共有を含む場合の参考値)。非圧縮は同じ定義(通常ファイルの内容合計)。

| 層 | 道数 | ファイル数 | 非圧縮(バイト) |
| --- | --- | --- | --- |
| common | 92,472 | 74,352 | 2,347,270,634 |
| common.dl | 32,489 | 25,735 | 1,349,809,832 |
| common.dl.ubuntu | 103,438 | 76,290 | 7,236,528,430 |
| common.dl.lubuntu | 169,591 | 98,440 | 6,222,901,257 |
| common.server | 15,297 | 11,949 | 1,882,836,443 |
| 合計 | 413,287 | 286,766 | 17,039,346,596 |

新しい割り当ての内容合計 17,080,368,395 バイトは現行とほぼ同じ(約 41MB 増)。増分は段1と段2の両方に置く同名の道(261 件、中身は異なる)と snap の Server 側の重ね置きによる。段をまたぐ共有をやめた分の戻りは上の 539,291,099 バイトである。

## 7. 圧縮後の見積もり(見積もり)

層ごとの非圧縮の合計に現行の圧縮率(設置元 6 層の圧縮後の合計 9,242,759,168 ÷ 非圧縮の合計 25,134,134,402 = 0.36774)を掛けた見積もり。層ごとの中身の縮み方は均一ではないため、あくまで見積もりである。層ごとの現行の圧縮率は d-minimal 0.37903、d-standard 0.31014、l-minimal 0.36201、l-standard 0.39231、s-minimal 0.36144、s-server 0.28833。

第 2 章の表の右列のとおり、合計の見積もりは約 6,281,088,860 バイト(約 6.28GB)である。

## 8. 指示書との差異

- Server の snap は指示書の想定(standard の層)と異なり、すべて s-minimal に在った(core24_1643・snapd_27710・hwctl_123 の 3 組 6 道)。subiquity の snap は設置元の 6 層のどこにも無い(`subiquity` の名があるのは apport のかけらのみ)。そのため Server の snap は `common.server.std` ではなく `common.server`(段1の Server 側)に置いている。Server の段1に snap が在る以上、共有層に置くと Server の段1の再構成が壊れるため、共有層は使っていない(指示書の「共有層を使わず」と一致)。
- `common.dl.snap` の 8 組のうち core24・snapd は上記の理由で Server 側にも重ね置きしている。snap 層の 8 組・1,574,879,232 バイト(片側)の数値は指示書の実測値と一致する。
- thunderbird_1228.snap の組(d-standard のみ、231,878,656 バイト × 2 道)は Ubuntu の段1に無いため snap 共有の対象外で、`common.dl.snap.ubuntu.std` に入る。

## 残課題

- R2(層の作成)では `layers.json` の `os`・`src` をもとに層を作る。ハードリンクの組は `linkto` と同じ層に固めること。whiteout(char 0,0。d-standard・l-standard・s-server に各 1 件)は段2の層に保持されている。
- `fixup_casefold.py` は macOS の作業場向けの補正である。Linux(大文字小文字を区別する場)では不要で、実行しても何も変えないことを次で確かめること(R1 の範囲外)。
- 回帰試験に新しい割り当ての自己検証を足した(`tests/test-ubuntu-merge.sh` 第 8 節)。合成データで通ることだけを実行して報告する。

## 影響範囲

- 新規: `tools/ubuntu-merge/plan_stages.py`、`tools/ubuntu-merge/verify_stages.py`、`tools/ubuntu-merge/fixup_casefold.py`、`build/work/run-inventory-r1.sh`、`RELAYER-R1-REPORT.md`。
- 変更: `tests/test-ubuntu-merge.sh`(第 8 節を追加。既存の節は無変更)。
- 既存の道具(`plan.py`・`verify.py`・`inventory.py`・`run-inventory.sh` など)は変更していない。
- 書き込みは作業ツリーの中だけ。入力 ISO・他の場所には書いていない。`build/` は git の対象外。
