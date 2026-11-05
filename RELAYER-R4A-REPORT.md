# R4a 報告: QEMU事前確認で停止

確認日: 2026-11-05。CCから委譲されたCodexが作業ツリー内で実施。

## 変更点

**プロセス監視が拒否されたため、依頼の停止条件に従い6項目の起動検証を開始せず停止した。**
QEMU自体の短い起動・停止は成立した。既存のISO・実装・他の変更ファイルには変更していない。

### 事前確認

- ISO: `build/ubuntu-merge-26.04.1-amd64-relayer.iso`。ファイルサイズは8,847,738,880バイトと確認した。SHA-256は今回は再計算していない。
- QEMU: `/opt/homebrew/bin/qemu-system-x86_64`。
- 条件: TCG、128MiB、`-S` でCPU停止、`-display none`、`-nic none`、ISOを読み取り専用CDとして接続。
- QEMUのstderrにSIGTERMによる停止が記録された。子プロセスの `wait()` が戻った後に監視確認へ進んだ。確認コマンド全体はツール計測で約1.3秒だった。
- `ps` の起動例外で最初の記録処理が中断したため、poll値・終了コードの数値は保存できなかった。stderrと実行順に基づく終了確認を証拠へ記録した。
- 自分が起動したQEMUは終了待ちまで完了した。ホスト全体のQEMU残存は**確認不能**。

`pgrep` は終了コード3で次を出力した。

```text
sysmon request failed with error: sysmond service not found
pgrep: Cannot get process list
```

`ps` はシェルからの実行でも、Pythonからの起動でも拒否された。

```text
zsh:5: operation not permitted: ps
PermissionError: [Errno 1] Operation not permitted: '/bin/ps'
```

QEMUのstderr原文:

```text
qemu-system-x86_64: terminating on signal 15 from pid 98048 (<unknown process>)
```

原因の仮説は、このセッションのサンドボックスがプロセス情報の取得を制限していること。
裏取りとして、`pgrep` と `ps` の両経路で拒否を確認した。
`sysmond` がホスト自体で欠落しているかは未確認であり、上のエラーだけから断定しない。
保護の変更・権限昇格・別の監視手段への切り替えは行わず、依頼どおり停止した。

### 項目とOSの結果

すべて「未確認」は、ゲストを起動して検証していないことを表す。
通常項目の排出対照も依頼された後続作業のため実行していない。

| 項目 | Ubuntu通常 | Ubuntu toram | Lubuntu通常 | Lubuntu toram | Server通常 | Server toram |
| --- | --- | --- | --- | --- | --- | --- |
| 1 画面への到達 | 未確認 | 未確認 | 未確認 | 未確認 | 未確認 | 未確認 |
| 2 cmdline・層の鎖 | 未確認 | 未確認 | 未確認 | 未確認 | 未確認 | 未確認 |
| 3 toram複写量 | 対象外 | 未確認 | 対象外 | 未確認 | 対象外 | 未確認 |
| 4 排出後の読み出し・対照 | 未確認 | 未確認 | 未確認 | 未確認 | 未確認 | 未確認 |
| 5 live・snap・unpackfs | 未確認 | 対象外 | 未確認 | 対象外 | 未確認 | 対象外 |
| 6 排出前のdmesg回帰 | 未確認 | 対象外 | 未確認 | 対象外 | 未確認 | 対象外 |

### tmpfs使用量と鎖の合計

鎖の合計は依頼文の値。今回はゲスト内の使用量を測っていない。

| OS | 期待される層数 | 鎖の合計バイト | tmpfs使用量 | 差 |
| --- | ---: | ---: | --- | --- |
| Ubuntu | 6 | 4,815,413,248 | 未確認 | 算出不能 |
| Lubuntu | 7 | 3,762,163,712 | 未確認 | 算出不能 |
| Server | 5 | 1,518,551,040 | 未確認 | 算出不能 |

### 保存した証拠

- `build/evidence/relayer-r4a/preflight-result.json`: 実行条件、確認できた結果、停止判定。
- `build/evidence/relayer-r4a/preflight-qemu.log`: QEMUのstderr原本。
- `build/evidence/relayer-r4a/preflight-process.log`: プロセス監視のエラー記録。
- `build/work/logs/r4a-preflight-qemu.log` と `r4a-preflight-process.log`: 実行時のログ。
- `.agent-handoff/experiments/relayer-r4a-preflight.md`: 事前確認の計画と結果。

## 残課題

Markdownの自動検査は未完了。導入済みmarkdownlintのローカルキャッシュからの起動は、依存 `globby` の解決で停止した。
ログは `build/work/logs/r4a-markdownlint.log`。追加取得は行っていない。

6項目の起動・層・排出・回帰検証がすべて残る。CCがQEMUの起動とプロセス監視のできる環境で引き継ぐ。
UEFI/GRUB起動、serial原本・整形ログ・到達画面、ゲストのメモリ使用量は未確認。
設置の検証R4bには着手していない。

## 影響範囲

追加したものは、この報告・事前確認の計画・ログ・証拠だけ。
ネットワーク・USBは使用していない。ISOの内容、起動ランナー、既存コードは変更していない。
`git add`・`git commit` は行っていない。
