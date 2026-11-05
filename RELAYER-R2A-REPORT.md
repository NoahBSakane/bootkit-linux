# R2a 報告: 設置用9層の生成と実物の検証

確認日: 2026-11-05。CCから委譲されたCodexが、この作業ツリー内で実行した。

## 変更点

設置用9層を生成した。圧縮後の実測合計は **5,269,733,376 バイト** (5.269733 GB、4.907822 GiB)。
実物の棚卸しと割り当ての層別比較、および公式との6ビュー比較は、いずれも差0。
R1b見積もり 5,113,448,344 バイトとの差は **+156,285,032 バイト** (+3.056%)。

### 生成した層

実測はファイルのバイト数。圧縮は公式と同じxz、ブロック131,072バイト。
所要秒は部分展開・疑似定義・圧縮・staging削除を含む。棚卸しと回帰試験を並行した経過時間。

| 層 | パス数 | 実測バイト | R1b見積もりとの差 | 生成秒 |
| --- | ---: | ---: | ---: | ---: |
| common | 77,973 | 1,138,008,064 | +436,494,784 | 52.316 |
| common.dl | 37,170 | 393,572,352 | -7,027,951 | 91.734 |
| common.dl.snap | 22 | 1,303,564,288 | -271,314,944 | 48.305 |
| common.dl.snap.ubuntu | 60,965 | 597,102,592 | +25,602,678 | 111.062 |
| common.dl.snap.lubuntu | 157,555 | 506,413,056 | +15,867,048 | 84.211 |
| common.server | 2,153 | 197,103,616 | +63,344,572 | 15.376 |
| common.dl.snap.ubuntu.std | 52,438 | 590,053,376 | -24,306,031 | 75.565 |
| common.dl.snap.lubuntu.std | 22,185 | 387,616,768 | -39,332,472 | 108.254 |
| common.server.std | 27,912 | 156,299,264 | -43,042,652 | 31.245 |
| 合計 | 438,373 | 5,269,733,376 | +156,285,032 | 618.068 |

成果物は `build/layers-stages/` の9本の `.squashfs`・9本の `.pseudo` と `build-stats.json`。
各実物の棚卸しは `build/work/inv-built/`。出力層のSHA-256は `build/work/logs/r2a-SHA256SUMS.layers`。

### 設置用の連鎖ごとの大きさ

ドット段数が少ない層から重ねる。Lubuntu Minimalは、受理済みR1bのとおりsnap共有層を含めない。

| OS | 選択 | 連鎖の合計バイト |
| --- | --- | ---: |
| ubuntu | minimal | 3,432,247,296 |
| ubuntu | normal | 4,022,300,672 |
| lubuntu | minimal | 2,037,993,472 |
| lubuntu | normal | 3,729,174,528 |
| server | minimal | 1,335,111,680 |
| server | normal | 1,491,410,944 |

### 新ISOの大きさの見積もり

**8,852,209,664 バイト** (8.852210 GB、8.244263 GiB) の見積もり。

| 項目 | バイト |
| --- | ---: |
| 設置用9層の実測合計 | 5,269,733,376 |
| 公式live・installer層の合計 (依頼元の値) | 848,723,968 |
| 現行ISOの層以外 (9,654,042,624 − 6,920,290,304) | 2,733,752,320 |
| 新ISOの見積もり | 8,852,209,664 |

層以外の部分を現行と同じと仮定した加算。R2bで作る設定層・メニュー等の変更量とISOの配置による差は未測定。ISOは作成していない。

### 実物の層と公式との照合

`inventory.py` のpfメタデータとcase-sensitive領域への展開後SHA-256を使った。
比較項目はパス集合・種別・モード・uid/gid・xattrの値全体・symlink先・通常ファイルSHA-256・デバイス番号。
時刻はR1と同じく同一性の判定に含めない。ルートエントリは既存の棚卸し方式と同様に対象外。

| ビュー | 公式パス数 | 実物の再構成パス数 | 差 |
| --- | ---: | ---: | ---: |
| ubuntu/minimal | 174,600 | 174,600 | 0 |
| ubuntu/normal | 226,649 | 226,649 | 0 |
| lubuntu/minimal | 271,261 | 271,261 | 0 |
| lubuntu/normal | 292,847 | 292,847 | 0 |
| server/minimal | 79,984 | 79,984 | 0 |
| server/normal | 106,719 | 106,719 | 0 |

実物のリンク辺 585 件、公式の通常ファイルの組 53 件を確認し、層またぎ・inode不一致は0。
層内の通常ファイルの組 45 組について、組の全メンバー集合も完全一致し、余分なinode結合は0。
通常ファイル390リンク辺は、展開後の `st_dev`・`st_ino` が一致することを直接確認した。
ホストに作れないデバイスとその別名195リンク辺は、実物squashfsからのpfのC/B・L行で確認した。
`security.capability` は公式 16 エントリ、実物 12 エントリで、すべて20バイト。値の比較も差0。
stdの各層のchar 0,0と、そのpfハードリンク別名を保持した。
全差分一覧は `build/work/logs/r2a-verification.json`、集約出力は `r2a-verify.log`。

### 実行コマンドと証拠

すべてプロジェクト直下から実行した。`TMPDIR` は `build/work/tmp` に設定した。
抽出・棚卸しスクリプトは実行時には `build/work/` に置き、実行後に同一内容を `.agent-handoff/` に保存した。

```sh
python3 -u .agent-handoff/extract-r2a.py
python3 -u -I tools/ubuntu-merge/repack_stages.py \
  build/work/plan/layers.json build/work/orig build/work/cs build/layers-stages
python3 -u .agent-handoff/inventory-r2a.py
python3 -u -I tools/ubuntu-merge/verify_built_stages.py \
  build/work/inv build/work/plan build/work/inv-built \
  build/work/logs/r2a-verification.json
BOOTKIT_CASE_STAGE="$PWD/build/work/cs" make test
```

抽出はISOごとに3並列、圧縮は最大8コア。容量を抑えるため生成stagingは1層ずつ作って削除し、完成層の棚卸しを並行した。
抽出スクリプトは公式3 ISO全体のSHA-256を、入力フォルダの公式
`SHA256SUMS.ubuntu` / `SHA256SUMS.lubuntu` と照合して一致を確認した。
設置元6層のハッシュは `build/work/logs/r2a-SHA256SUMS.orig` に保存した。内部層の由来は、抽出元ISO全体のSHA-256一致を根拠とする。

ログは `build/work/logs/` の `r2a-extract.log`・`extract-*.log`・`r2a-repack.log`・`r2a-inventory.log`・`r2a-verify.log`・`r2a-make-test.log`。
合成試験は内容の異なる `Sys/item`・`sys/item`、通常ファイルのリンク組、symlink、char 0,0とその別名、空白入りxattr、20バイトcapability、同一内容で独立した2ファイルを往復し、差0。
`make test` は通常パスと空白・ピリオドを含むパスの両方で合格した。

### 失敗と対処

- 合成試験の展開除外で `-e` を誤用した。`unsquashfs -help-option` で構文を確認し、`-exclude-file` へ変更して成功した。
- 合成試験を拡張した際、charの疑似定義に余分な引数を入れた。`mksquashfs` が示したC行の構文と照合して修正し、合成試験が成功した。
- 回帰試験にはR1bより前のUbuntu鎖順を期待する条件が残っていた。既存 `plan_stages.py` の受理済みドット順に試験を合わせた。全試験は修正後に再実行して合格した。

実物の生成・照合で生じた差分は0。
初回の試験ログは `r2a-synthetic-attempt*.log`・`r2a-make-test-attempt1.log` に残した。

### 容量管理と後始末

処理中の10秒間隔の空き容量記録は `r2a-space.jsonl`。観測最小は 22,200,320,000 バイト (20.676 GiB)、下限18GiBを上回った。
生成・展開の子プロセス実行中も1秒間隔で18GiBを検査し、下回る場合は停止する方式にした。
完成済みの層だけが参照する抽出元4本 (7,395,278,848バイト) を先に削除し、空き容量を確保した。対象と完成済み参照先は `r2a-cleanup-early.json`。
残りの `build/work/orig`、各生成・棚卸しstaging、合成試験の中間物も削除した。最終削除対象とサイズは `r2a-cleanup.json`。
公式ISO3本は読み取りのみ。case-sensitiveのマウント `build/work/cs` は残した。

## 残課題

R2b: 公式live・installer層の流用、設定層、install-sources.yaml、grub、ISO組み立てと、その後の起動・設置検証。
R2aではこれらの変更・実行を行っていない。

## 影響範囲

- 新規: `tools/ubuntu-merge/repack_stages.py`、`verify_built_stages.py`、`test_repack_stages.py`、この報告。
- 変更: `tests/test-ubuntu-merge.sh` (R2aの試験を追加、鎖順の期待値を現行R1bへ更新、既存の検証器試験を同一層の反復照合にそろえた)。
- 生成: `build/layers-stages/`、`build/work/inv-built/`、`build/work/logs/r2a-*`、
  `.agent-handoff/` の手順と記録。
- 既存の `repack.py`・`inventory.py`・`plan_stages.py`・`verify_stages.py` の動作は変更していない。R1/R1b由来の未コミット変更は保持した。
- 作業ツリー外への書き込み、ネットワーク通信、QEMU、git add、git commitは行っていない。
