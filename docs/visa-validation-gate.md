# VisA 検証ゲート（spec 4 完了時点）

[spec 実行順](./spec-execution-order.md) の 4（primary-anomaly-detection）を完了した時点で、
公開データセット VisA を使って **正常メモリバンク構築 → 一次検出 → 最小指標** を通しで
実行できる状態にする。実データ（MIIC・実機）を投入する前に、
特徴テンソル → ストアレコード → スコア／ROI というデータ契約が実際につながることを確認するゲート。

## なぜ計画に追加するか

roadmap の 6 spec の brief をそのまま実装すると、spec 4 完了時点でも次の 2 つが欠ける。

- **画像の読み込み・train/test 分割・GT マスク取得の所有者がいない**。
  ssl-vit-feature-extraction の Upstream は「なし（パイプラインの起点）」で、
  In スコープはタイル化・パッチ化から始まっている。
- **検出性能を数値化できない**。指標算出は evaluation-framework（順序 6）の所有で、
  primary-anomaly-detection は明示的に Out にしている。

この 2 つを、ゲートの成立に必要な最小範囲だけ前倒しする。全量を前倒しはしない。

## データセットの選定

**VisA**（Visual Anomaly、Amazon Science）を使う。12 カテゴリ・10,821 枚
（正常 9,621／異常 1,200）で画素マスクを持ち、`anomalib.data.Visa` から利用できる。

### ライセンス

- VisA のデータは **CC BY 4.0**（表示のみ。商用利用可）。根拠は配布元
  [amazon-science/spot-diff](https://github.com/amazon-science/spot-diff) README の License 節と、
  AWS Open Data Registry の
  [visa.yaml](https://github.com/awslabs/open-data-registry/blob/main/datasets/visa.yaml)
  （`License: https://creativecommons.org/licenses/by/4.0/`）。
- MVTec AD は CC BY-NC-SA 4.0（商用不可）のため使用しない。
- **anomalib 2.6.0 の docstring は VisA を CC BY-NC-SA 4.0 と誤記している**
  （`anomalib/data/datamodules/image/visa.py` と `anomalib/data/datasets/image/visa.py`）。
  法務確認では anomalib の記述ではなく上記の配布元を根拠にする。

### カテゴリ

既定は PCB 系（`pcb1`〜`pcb4`）。12 カテゴリのうち構造が最も複雑で、半導体検査画像に一番近いため。
カテゴリを装置タグの代理として扱えば、ドメイン分割とカテゴリ横断の劣化曲線の動作確認にも使える。

## 合格条件

1. VisA の `train/good` から正常パッチ特徴を抽出し、メモリバンクを構築・永続化できる。
2. 構築済みメモリバンクに対して `test` 画像をスコア化し、ヒートマップと ROI 候補が出力される。
3. image-level AUROC と AUPRO を算出できる。image-level AUROC 0.9 を暫定の下限とし、
   下回る場合は配線ミスを疑う（**この数値は動作確認の目安であり、チューニングの目標値ではない**）。
4. 同一 CLI でカテゴリとバックボーンを差し替えて再実行でき、結果が出力ディレクトリに残る。
5. 上記が pytest から起動できる（データ未取得の環境では skip する）。

## バックボーン比較（ゲート通過直後に実施）

VisA はラベルと画素マスクを持つため、**検出力そのものを比較できる最初の機会**になる。
正常のみの実機データでは検出力の比較が原理的にできないので、抽出器比較の主戦場は
ここと MIIC になる（`docs/normal-only-validation-plan.md`）。

同一 CLI で `--backbone` を振り、カテゴリごとに image-level AUROC と AUPRO を並べる。
比較対象は DINOv3（主軸）に対して DINOv2・DINO・ImageNet 教師あり CNN（`wide_resnet50_2`）。

条件統一が結果を左右するため、次を揃えて記録する。

- **前処理条件**（layer norm の有無など）。DINOv2 は適用可否で精度が変わる（researches.md §10）。
- **タイル化・パッチ化のサイズと重なり**、kNN の k、coreset 率、スコア融合の重み。
- **バンクサイズはパッチ数でも揃える**。バックボーンによってパッチグリッドが異なり、
  同じ画像枚数でも登録パッチ数が変わる。画像枚数を揃えたうえでパッチ数を併記し、
  差が大きい場合は部分サンプリングでパッチ数も揃える。
- **距離尺度のスケール**。埋め込み次元が異なると L2 距離の絶対値を横並びにできない。
  正規化方法（コサイン／L2 正規化後の距離）を統一し、運用点は分位点で与える。
- **抽出器同一性メタ**（モデル名・重みリビジョン・前処理条件・埋め込み次元）を結果に添付する。
  ssl-vit-feature-extraction がこのメタを出力する。

VisA は代理データなので、この比較だけで抽出器を確定しない。MIIC の AUROC／AUPRO と、
正常のみ実機データで測るドメイン不変性・安定性・データ効率を合わせて選定する。

## 各 spec への追加範囲

- **ssl-vit-feature-extraction**: データセット入力アダプタ。anomalib の `ImageItem` を
  自前のタイル入力型へ変換し、anomalib の型を下流に漏らさない。
- **patch-feature-store**: データセット由来の既知正常（`train/good`）を HITL 検証を介さずに
  一括登録する初期構築経路。
- **primary-anomaly-detection**: ゲートを実行する CLI エントリポイント。
- **evaluation-framework**: image-level AUROC と AUPRO のみ前倒しで実装。
  PG2・F1-Max・AUPRC・運用 KPI・コスト感度分析は spec 6 本体に残す。

## 実行インターフェース

`pyproject.toml` は `package = false` のため `[project.scripts]` は使えない。
`scripts/` に置き、`mise.toml` の task から呼ぶ既存の慣習に合わせる。

```bash
mise run visa-gate -- --data-root /path/to/VisA --category pcb1
```

引数は最小限に絞る。

- `--data-root`（必須）: VisA のルート。既定値は持たせない（後述の暴発防止とリポジトリ汚染防止）。
- `--category`: 既定 `pcb1`。`anomalib.data.datasets.image.visa.CATEGORIES` を `choices` にする。
- `--backbone`: 既定は DINOv3。timm のバックボーン名で比較用モデルに差し替える。
- `--download`: 既定 off。明示したときだけダウンロードを許可する。
- `--output-dir`: スコアマップ・ROI・指標・抽出器同一性メタの出力先。

## 実装前に踏まないための既知の罠

anomalib 2.6.0 の実装を読んで確認した挙動。設計時に織り込む。

1. **ダウンロードの暴発**。`Visa.prepare_data()` は `root/visa_pytorch/{category}` も
   `root/{category}` も無ければ確認なしでダウンロードする（約 16GB）。
   `--data-root` の存在を CLI 側で検証し、`--download` 未指定なら即エラーにする。
2. **書き込み権限と容量**。`apply_cls1_split()` は `root/split_csv/1cls.csv` を読んで
   `root/visa_pytorch/` へ画像を複製する。12 カテゴリ全部を処理するので、
   `--category` を絞っても初回は全カテゴリ分がコピーされる。読み取り専用ストレージでは失敗する。
3. **1cls レイアウトの不一致**。配布元の `prepare_data.py` は `VisA_pytorch/1cls/{category}` を作るが、
   anomalib は `{root}/visa_pytorch/{category}` を見る。前処理済みデータを流用する場合は
   datamodule ではなく `VisaDataset(root="<...>/VisA_pytorch/1cls", category=..., split=...)` を直接使う。
4. **collate の暗黙リサイズ**。`ImageBatch.collate` はバッチ内で画像形状が混在すると、
   最大の H/W へ全件リサイズする。タイル化前の生画像を流すなら `batch_size=1` にするか、
   タイル化を Dataset 側に入れて形状を揃えてから collate させる。
5. **リポジトリ汚染**。このリポジトリにはリポジトリレベルの `.gitignore` が無い。
   データセットはリポジトリ外に置く（`--data-root` に既定値を持たせない理由でもある）。

なお anomalib のデータセットはリサイズを強制しない。前処理はモデル側の `PreProcessor` が持つため、
anomalib のモデルを使わず datamodule だけ借りれば、画像はネイティブ解像度で得られる。
超高解像度画像のタイル化を ssl-vit-feature-extraction が所有する方針とぶつからない。

## このゲートの限界

VisA は半導体検査画像ではない代理データであり、通過しても検出性能の妥当性は主張できない。
確認できるのは配線とデータ契約が成立することまで。工程・材料・装置タグは VisA に存在せず、
カテゴリを代理に使うだけなので、ドメイン分割の実運用妥当性も別途 MIIC・実機データで検証する。
本番の評価プロトコル（PG2・運用 KPI・コスト感度分析・劣化曲線）は evaluation-framework が所有する。

## 次の段階

ゲート通過後は、独自の半導体検査画像（正常のみ）で
[正常データのみの実機画像検証](./normal-only-validation-plan.md) に進む。
実データはラベルも画素マスクも持たないため、検出性能ではなく過検出率・スコアの安定性・
ドメインシフトの影響量・汚染候補を測る検証になる。
