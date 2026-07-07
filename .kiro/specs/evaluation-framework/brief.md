# Brief: evaluation-framework

## Problem

半導体製造は正常が圧倒的多数で欠陥が極めて稀かつ微小なため、image-level AUROC のみでは
見逃し（False Negative）と過検出（False Positive）の非対称コストを反映できない
（researches.md §7）。学術指標と製造現場の運用指標を併用する多指標評価と、工程横断汎化・
HITL 回復量を定量化する評価基盤が必要（researches.md §5、§7）。

## Current State

- ソースコードは未実装。評価対象のパイプライン（一次検出・補正レイヤ）は先行 spec が構築予定。
- MIIC データセットは異常 116 枚にマスク付与済みで画素単位評価が可能。実機データには
  画素マスクがない（researches.md §7）。
- anomalib に合成異常機能（`PerlinAnomalyGenerator`、`SyntheticAnomalyDataset` /
  `make_synthetic_dataset`、`Folder` datamodule の `test_split_mode=SYNTHETIC`）が内蔵
  されている（researches.md §12）。

## Desired Outcome

- **画像単位指標**: image-level AUROC を基準に、PG2（Pre-sorted Good at 2%）・F1-Max・
  AUPRC を併用して算出できる（researches.md §7）。
- **領域単位指標**: AUPRO を主指標、pixel AUROC を参考併記とし、マスクを持つ MIIC でのみ
  算出する（researches.md §7）。
- **合成異常による局在化評価**: anomalib の合成異常機能で欠陥サイズ別・位置別の
  AUPRO／pixel AUROC を補強できる。用途は評価のみ（researches.md §12）。
- **運用 KPI**: 流出率（escape rate）・過検出率（overkill rate）を運用点で報告し、必要に応じ
  ppm／DPPM で示せる（researches.md §7）。
- **閾値・モデル選定**: FN／FP のコスト非対称性に基づくコスト感度分析で運用点とモデルを
  確定できる（researches.md §7）。
- **比較実験**: 特徴抽出器比較（DINOv3 主軸 vs ImageNet 教師あり CNN・DINOv2・DINO＋MAE・
  C-RADIOv2）、段階的ドメインシフト（同一工程→類似→異材料→異装置→異撮像）の劣化曲線、
  HITL プロトタイプ N 件追加による回復量を測定できる（researches.md §5、§7）。

## Approach

- データ別の二段構成を採る：(1) MIIC（画素マスクあり）は image-level 指標＋ AUPRO／pixel
  指標で局在化まで評価し、必要に応じ MVTec-AD／VisA でも妥当性確認。(2) 実機データ
  （マスクなし）は image-level 指標＋運用 KPI で評価する（researches.md §7）。
- 合成異常は評価専用とし、特徴抽出器の学習や閾値・スコアの較正には用いない
  （researches.md §12）。半導体の欠陥形態に寄せるため外部異常ソース画像・ブレンド率を
  調整し、ドメイン単位で妥当性を確認する（researches.md §12）。
- DGX Spark 実測（パッチ数×スケール×ストア規模のスイープ）と PC GPU 比較による計算資源
  要件の定量化もこの spec が所有する（researches.md §4、`docs/plan.md` 計算資源検証）。

## Scope

- **In**: 指標算出（image-level／領域単位／運用 KPI）、合成異常データ生成（評価専用）、
  コスト感度分析、特徴抽出器比較・劣化曲線・HITL 回復量の評価プロトコル、
  計算資源スイープ計測。
- **Out**: 検出・補正ロジックそのもの、合成異常を用いた学習・閾値較正
  （researches.md §12 で明示的に禁止）。

## Boundary Candidates

- 指標計算（メトリクス実装）と実験プロトコル（データ分割・比較条件の管理）の分離
- 合成異常生成（anomalib ラッパー）の独立モジュール化

## Out of Boundary

- 一次検出・補正レイヤの実装（primary-anomaly-detection、promptable-correction-layer が所有）
- 特徴量ストアの実装（patch-feature-store が所有）
- accuracy（正解率）の主指標採用（極端な不均衡下で無意味のため不採用、researches.md §7）

## Upstream / Downstream

- **Upstream**: primary-anomaly-detection（評価対象のスコア・ヒートマップ）、
  ssl-vit-feature-extraction（特徴抽出器比較の対象となるバックボーン切り替え・前処理条件）、
  patch-feature-store（ストア規模スイープの計測対象）。
  HITL 回復量・補正方式比較の実験実行は promptable-correction-layer の完成後になるが、
  指標・プロトコル定義は本 spec が所有するため、promptable-correction-layer は依存に
  含めない。
- **Downstream**: なし（年度評価レポートの根拠データを生成する終端）。

## Existing Spec Touchpoints

- **Extends**: なし（新規）
- **Adjacent**: primary-anomaly-detection、promptable-correction-layer、patch-feature-store

## Constraints

- AUPRO・pixel 指標はマスクを持つ MIIC（または小規模アノテ済みサブセット）に限定し、
  マスクのない実機データには適用しない（researches.md §7）。
- 合成異常は評価のみに使用（researches.md §12）。
- MIIC 異常 116 枚の統計不安定への対策として、正常分割の k-fold＋bootstrap 信頼区間を
  考慮する（`docs/plan.md` リスクと対策）。
