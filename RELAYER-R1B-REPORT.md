# R1b 報告: ul 分類の修正とドット規則の順での検証

日付: 2026-11-04。作業場所: この作業ツリー(`build/work/`)。層・ISO は作っていない。

R1 受理後の追加修正(R1b)。直したのは 2 点。`build/work/inv`(棚卸し 6 本)と
`build/work/plan` は R1 のものをそのまま使い、`plan` を取り直した。
`build/work/orig`(抽出物)は CC が削除済み(R1b では不要)。

## 結論

- 分類修正: Ubuntu・Lubuntu が同一なら Server に同名パスが在っても
  `common.dl` に入れる。対象は 17 道・653,416 バイト。
  残りの dl 重複 134 道はハードリンク同居規則のため OS 別の層に残る(原因を確かめた)。
- ドット規則の順(casper の導き方)で鎖を出し直し、
  自己検証が 6 ビューすべて差 0。旧順と新順の再構成ビューは完全一致(差 0)。
- 圧縮後の見積もりを直した(ハードリンクは 1 部・snap 層は比 1.0)。
  新見積もり合計は約 5,113,448,344 バイト(約 5.11GB)。

## 1. 直した内容

### 1.1 ul 分類(`tools/ubuntu-merge/plan_stages.py`)

段1の `ul` 条件から `not pres["server"]` を外した。
Ubuntu・Lubuntu の鍵(種別・内容・モード・所有者・xattr・symlink 先・
デバイス番号)が一致すれば、Server に同名パスが在っても
Ubuntu・Lubuntu 側は `common.dl` に入れる。
3 OS 同一(鍵が 1 種類)のものは従来どおり `common` に入る(除外を維持)。
Server 側の別内容は `common.server` に置く(新しい分岐。
Server 側は従来から `common.server` に在ったので層の種類は変わらない)。
ハードリンク・デバイス peer の同居規則(`not nlink_any` と組ごとの強制移動)は
変えていない。組が割れる配置は従来どおり OS 別の層へ戻す。

### 1.2 ドット規則の鎖順(`plan_stages.py`・`verify_stages.py`)

`CHAINS` を手書きの列挙から、層名から導く `dot_chain(leaf)` に変えた。
leaf の名前をドットで削って `NEW_LAYERS` に在る接頭辞だけを残し、
短い順(下から上へ)に並べる。casper が leaf から親をたどる順と同じ。
`verify_stages.py` の重ねも `dot_order()` で層名から導いた順にし、
`chains.json` の記載順に依存しない(ハードリンク同居検査の上端判定も同順)。
Lubuntu の Minimal だけは `common.dl.snap` を除く順を別に持つ(従来どおり。
段1に snap が無いため)。

新しい鎖(下から上へ):

- ubuntu minimal: common、common.dl、common.dl.snap、common.dl.snap.ubuntu
- ubuntu normal: 上に common.dl.snap.ubuntu.std を足す
- lubuntu minimal: common、common.dl、common.dl.snap.lubuntu(変更なし)
- lubuntu normal: common、common.dl、common.dl.snap、
  common.dl.snap.lubuntu、common.dl.snap.lubuntu.std
- server minimal / normal: 変更なし

旧順(例: ubuntu minimal = common.dl.snap、common、common.dl、…)との
違いは snap 層の位置だけだった(下から 2 段目へ移動)。

## 2. 151 道の原因の確認

R1 の `stage1_pair_bytes.dl` 151 道 1,315,208,542 バイトの内訳を、
棚卸しから数え直した(下は Ubuntu 側の大きさ。ハードリンクは名寄せで数える。
合計 1,315,208,542 バイトで R1 の値と一致):

- Server に同名パスが在って内容(鍵)が違う・ハードリンク絡みなし: 17 道・
  653,416 バイト。今回 `common.dl` に移したのはここだけ。
- 3 OS 同一の鍵だがハードリンク絡みで共有層に入れない: 119 道・
  1,313,740,562 バイト(例: `usr/bin/perl`・`usr/bin/coreutils`・
  `usr/lib/cargo/bin/coreutils/*` の組。組の顔ぶれが OS で違うため
  OS 別の層に組ごと置く)。
- Server に無く Ubuntu・Lubuntu 同一だがハードリンク絡み: 15 道・
  814,564 バイト(組全体が Ubuntu・Lubuntu 同一の 7 組)。

つまり「Server の段1にも同じパスが在るが内容が違う」は 17 道だけが該当し、
残り 134 道はハードリンクの組を 1 層に固める規則によるもので、
今回の条件修正の対象外である。`stage1_pairs.dl` は 151 → 134、
`stage1_pair_bytes.dl` は 1,315,208,542 → 1,314,555,126 バイトになった。

`common.dl` に移った 17 道:

```text
etc/alternatives/pager
etc/ca-certificates.conf
etc/chrony/chrony.keys
etc/ssl/certs/ca-certificates.crt
etc/systemd/system/timers.target.wants/apt-daily-upgrade.timer
etc/systemd/system/timers.target.wants/apt-daily.timer
run/systemd/resolve/stub-resolv.conf
usr/bin/man
usr/lib/dbus-1.0/dbus-daemon-launch-helper
usr/lib/python3.14/__pycache__/functools.cpython-314.pyc
usr/lib/python3.14/__pycache__/sitecustomize.cpython-314.pyc
usr/share/info/dir
var/crash
var/lib/chrony
var/lib/dpkg/alternatives/pager
var/lib/dpkg/available
var/log
```

同じ SHA-256 でも鍵が違うものを含む(例: `etc/chrony/chrony.keys` は
3 OS とも内容同一だがモードが違い、`usr/lib/dbus-1.0/dbus-daemon-launch-helper`
は内容同一だがモードが違う)。鍵の定義は変えていない。

## 3. 変更後の層ごとの道数・非圧縮の大きさ(R1 との差)

`report.txt` による。バイトは通常ファイルの内容合計(道・symlink・xattr の
収まりは含まない)。

| 層 | 道数 R1 → R1b | 非圧縮 R1 → R1b(バイト) |
| --- | --- | --- |
| common | 77,973 → 77,973(±0) | 1,907,647,788 → 1,907,647,788(±0) |
| common.dl | 37,149 → 37,170(+21) | 1,088,711,967 → 1,089,365,383(+653,416) |
| common.dl.snap | 22 → 22(±0) | 3,149,758,464 → 3,149,758,464(±0) |
| common.dl.snap.ubuntu | 60,989 → 60,965(-24) | 2,909,038,884 → 2,908,385,468(-653,416) |
| common.dl.snap.lubuntu | 157,579 → 157,555(-24) | 2,633,310,019 → 2,632,656,603(-653,416) |
| common.server | 2,153 → 2,153(±0) | 1,786,279,391 → 1,786,279,391(±0) |
| common.dl.snap.ubuntu.std | 52,438 → 52,438(±0) | 1,902,526,094 → 1,902,526,094(±0) |
| common.dl.snap.lubuntu.std | 22,185 → 22,185(±0) | 1,161,016,900 → 1,161,016,900(±0) |
| common.server.std | 27,912 → 27,912(±0) | 542,078,888 → 542,078,888(±0) |

`classes`: C3 77,972(±0)、Cdl 36,245 → 36,262(+17)、
leaf-ubuntu 60,367 → 60,350(-17)、leaf-lubuntu 157,044 → 157,027(-17)、
leaf-server 2,006 → 1,989(-17)。内容合計は 17,080,368,395 →
17,079,714,979 バイト(-653,416。`common.dl` への一本化分)。
道数の増減が 17 より大きい層があるのは、要る親ディレクトリの置き場が
動いたため(例: 葉から抜けた道の親のみだった dir が葉から消える)。
`cross_stage_dups` は 3 OS とも [0, 0] のまま。
`explicit_leaf` は 3 OS とも 0 のまま。ハードリンクの強制移動は 0 組。

## 4. 自己検証の結果(ドット規則の順)

`python3 -I tools/ubuntu-merge/verify_stages.py build/work/inv build/work/plan`
の結果。比較項目は R1 と同じ(パス集合・種別・モード・所有者・xattr・
symlink 先・通常ファイルの SHA-256・デバイス番号)。

- ubuntu minimal: 公式 174,600、新 174,600、差 0
- ubuntu normal: 公式 226,649、新 226,649、差 0
- lubuntu minimal: 公式 271,261、新 271,261、差 0
- lubuntu normal: 公式 292,847、新 292,847、差 0
- server minimal: 公式 79,984、新 79,984、差 0
- server normal: 公式 106,719、新 106,719、差 0
- ハードリンクの組の層またぎ: 0

旧順とドット順の両方で重ねたビューを突き合わせた結果、
6 ビューともパス集合・内容とも完全一致(差 0)。
同一パスが複数の層に在る場合の上書きの向きは、
今回の実データでは結果を変えない。
理由: 各 OS の各道は段1ではちょうど 1 つの層に在り(組の強制移動と
葉への明示追加は上端の葉へ寄せる)、
OS をまたぐ同名の競合は葉への写しで上端が勝つため、
中間の順を入れ替えても勝者は変わらない。

## 5. 圧縮後の見積もりの直し

R1 の見積もりの問題: (a) ハードリンクの 2 名前を二重に数えている、
(b) snap(中身自体が圧縮済み)に一律の圧縮率を掛けている。
直した見積もり: ハードリンクの組は同一(src タグ, grp)を 1 部で数える
(組内の大きさ不一致は 0 件で確かめた)。
snap 層は二重計上を除いた片側 1 部 1,574,879,232 バイトをそのまま
圧縮後の目安にする(比 1.0)。それ以外の層は二重計上を除いた大きさに
現行の圧縮率(0.36774。設置元 6 層の圧縮後合計 ÷ 非圧縮合計)を掛ける。
層ごとの中身の縮み方は均一でないため、引き続き見積もりである。

| 層 | 二重計上除去後(バイト) | 見積もり(バイト) |
| --- | --- | --- |
| common | 1,907,647,788 | 701,513,280 |
| common.dl | 1,089,365,383 | 400,600,303 |
| common.dl.snap | 1,574,879,232 | 1,574,879,232(比 1.0) |
| common.dl.snap.ubuntu | 1,554,098,229 | 571,499,914 |
| common.dl.snap.lubuntu | 1,333,957,652 | 490,546,008 |
| common.server | 363,735,302 | 133,759,044 |
| common.dl.snap.ubuntu.std | 1,670,647,438 | 614,359,407 |
| common.dl.snap.lubuntu.std | 1,161,016,900 | 426,949,240 |
| common.server.std | 542,076,930 | 199,341,916 |
| 合計 | — | 5,113,448,344(約 5.11GB) |

旧方式(R1 と同じ一律掛け)で R1b の内容に掛けた参考値は
6,280,848,573 バイト。R1 の旧方式の値 6,281,088,860 バイトとの差
-240,287 バイトは、移動した 653,416 バイトに 0.36774 を掛けた分と一致する。
二重計上の除去で大きく下がるのは `common.server`(1,786,279,391 →
363,735,302)、`common.dl.snap.ubuntu`(2,908,385,468 → 1,554,098,229)、
`common.dl.snap.lubuntu`(2,632,656,603 → 1,333,957,652) である。

## 残課題

- R2(層の作成)では `layers.json` の `os`・`src` をもとに層を作る。
  ハードリンクの組は `linkto` と同じ層に固めること。
  134 道の残り重複(3 OS 同一の組・Server 欠きの 7 組)は、
  組単位の共有可否の判定が要るため R1b の対象外とした。
- `fixup_casefold.py` は macOS の作業場向けの補正である。
  Linux(大文字小文字を区別する場)では不要で、実行しても何も変えないことを
  次で確かめること(R1 の残課題のまま)。
- 回帰試験に ul 分類の合成ケースと鎖順の検査を足した
  (`tests/test-ubuntu-merge.sh` 第 8 節)。
  通ることだけを実行して報告する(`make test` の合格を作業ログで確かめた)。

## 影響範囲

- 変更: `tools/ubuntu-merge/plan_stages.py`(ul 条件・`dot_chain`・`CHAINS`)、
  `tools/ubuntu-merge/verify_stages.py`(`dot_order`)、
  `tests/test-ubuntu-merge.sh`(第 8 節を追加。既存の節は無変更)、
  `build/work/plan/`(取り直し。R1 の数値は `RELAYER-R1-REPORT.md` に残る)。
- 新規: `RELAYER-R1B-REPORT.md`(この文書)。
- 既存の道具(`plan.py`・`verify.py`・`inventory.py`・`run-inventory.sh` など)は
  変更していない。書き込みは作業ツリーの中だけ。
  入力 ISO・他の場所には書いていない。`build/` は git の対象外。
  コミットはしていない。
