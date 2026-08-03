# Brief: primary-anomaly-detection

## Problem

欠陥が極めて稀でラベル付けコストが高いため、教師あり分類による欠陥判定は成立しない
（researches.md §1）。正常パッチ分布からの逸脱（anomaly score）に基づき、欠陥候補の
ヒートマップと ROI 候補を教師なしで得る一次検出が必要（researches.md §3.1、§3.2-2）。

## Current State

- ソースコードは未実装。`scipy>=1.13`（Mahalanobis 距離用）、`scikit-learn>=1.4` が依存に
  定義済み（`pyproject.toml`）。
- anomalib PatchCore を丸ごと使わず、近傍検索は patch-feature-store、スコア化は本 spec が所有
  する方針（researches.md §10、§11 の増分運用を守るため）。

## Desired Outcome

- パッチ特徴から正常分布との逸脱を算出し、欠陥候補ヒートマップと ROI 候補を出力する
  （researches.md §3.2-2）。
- 複数のスコア方式（Mahalanobis 距離、コアセットによる PatchCore 系 k 近傍距離）を
  組み合わせられる（researches.md §3.3）。MAE ピクセル再構成誤差は将来検討。
- 装置別・チャネル別に正常分布が乖離する場合、ドメイン（工程・材料・装置タグ）で分割された
  特徴量メモリと突き合わせてスコア化できる（researches.md §3.3）。

## Approach

- PatchCore 系 kNN 距離は patch-feature-store の正常メモリバンクに対する近傍検索で算出する。
- Mahalanobis 距離は scipy を用い、ドメイン単位の正常分布推定と組み合わせる
  （researches.md §3.3、§8 の再較正方針）。
- 複数スコアの融合とヒートマップ化、ROI 候補の切り出しまでを所有する。

## Scope

- **In**: 異常スコア算出（Mahalanobis／kNN）、スコア融合、ヒートマップ生成、
  ROI 候補の切り出し、ドメイン別正常分布との突き合わせ（既定はメモリバンク全体をプールした
  ドメイン非依存スコア化。ドメイン別正常分布との突き合わせは分布が乖離する場合のみの任意経路。
  ドメインタグを一次判定のハードフィルタには用いない。researches.md §3.3、§8）。
- **Out**: HITL フィードバックによるスコア補正・最終判定、閾値の運用点確定
  （コスト感度分析は evaluation-framework が所有）、MAE 再構成誤差（将来検討）。

## Boundary Candidates

- スコアラー（方式ごとの距離計算）とアグリゲータ（融合・ヒートマップ・ROI 切り出し）の分離

## Out of Boundary

- 補正レイヤによるスコア再構成・最終判定（promptable-correction-layer が所有）
- 評価指標の算出・閾値のコスト感度分析（evaluation-framework が所有）
- 正常メモリバンクの構築・管理（patch-feature-store が所有）
- MAE 再構成経路（将来検討。ssl-vit-feature-extraction も提供しない）

## Upstream / Downstream

- **Upstream**: ssl-vit-feature-extraction（パッチ特徴）、
  patch-feature-store（正常メモリバンクへの近傍検索）。
- **Downstream**: llm-feedback-structuring（ROI 候補がオペレータレビューの入力になる）、
  promptable-correction-layer（一次スコアの再構成対象）、evaluation-framework
  （検出性能の評価対象）。

## Existing Spec Touchpoints

- **Extends**: なし（新規）
- **Adjacent**: ssl-vit-feature-extraction、patch-feature-store、promptable-correction-layer

## Constraints

- バックボーンを CNN と比較する実験では、layer norm の有無など前処理条件を揃える
  （researches.md §10）。
- 撮像条件の変動が欠陥より支配的な場合に備え、ドメイン単位での分布推定・再較正を考慮する
  （researches.md §8）。
