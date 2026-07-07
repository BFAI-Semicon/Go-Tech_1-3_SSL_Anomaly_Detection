# Brief: promptable-correction-layer

## Problem

一次検出の異常スコアだけでは、現場が許容する既知パターンの過検出（False Positive）を
抑制できない。ROI 注釈に基づくプロトタイプ記憶と自然言語由来の適用条件を推論時に統合し、
異常スコアを再構成する補正機構（Promptable Patch Retrieval の中核）が必要
（researches.md §3.1、§3.2-5、§5）。

## Current State

- ソースコードは未実装。近傍照合に必要な FAISS・特徴抽出・構造化 JSON は先行 spec
  （patch-feature-store、ssl-vit-feature-extraction、llm-feedback-structuring）が提供予定。
- 補正の3方式（スコア再重み付け／閾値適応／ラベル上書き）の比較検証が研究の検証軸として
  定義されている（再重み付けとラベル上書きの差の検証は researches.md §5、閾値適応を含む
  3方式の列挙は `docs/plan.md` 構成要素・評価軸に由来）。

## Desired Outcome

- 欠陥候補 ROI の埋め込み（roi_embedding）とストア内プロトタイプ（vit_embedding）を
  近傍照合し、類似度閾値および構造化 JSON の適用条件（工程・材料・装置・期限等）を満たす
  ときに異常スコアを再構成する（researches.md §3.2-5）。
- 最終判定として NG、許容（False Positive の抑制）、要確認などを返す（researches.md §3.2-6）。
- スコア再重み付け／閾値適応／ラベル上書きの3方式を切り替えて比較検証できる
  （researches.md §5「スコアの再重み付けとラベル上書きの差を検証可能とする」）。
- ROI のみ／言語のみ／両方の条件を切り替えて比較できる（researches.md §5）。

## Approach

- 近傍照合は patch-feature-store の kNN 検索を利用し、ドメイン・適用メタ情報で絞り込む。
- 適用条件マッチは llm-feedback-structuring が生成した運用スキーマ JSON
  （判定・適用範囲・優先度・有効期限）を評価する。
- 補正方式（再重み付け／閾値適応／ラベル上書き）と条件ソース（ROI のみ／言語のみ／併用）を
  設定で切り替え可能にし、評価実験の比較軸に対応する（researches.md §5）。

## Scope

- **In**: roi_embedding とプロトタイプの近傍照合、類似度閾値判定、適用条件マッチ、
  異常スコア再構成（3方式）、最終判定（NG／許容／要確認）の出力。
- **Out**: プロトタイプの登録・coreset 管理（patch-feature-store が所有）、構造化 JSON の
  生成（llm-feedback-structuring が所有）、補正効果の定量評価（evaluation-framework が所有）。

## Boundary Candidates

- 照合（近傍検索＋適用条件フィルタ）と補正（スコア再構成の3方式）と判定（最終ラベル決定）の
  3段分離

## Out of Boundary

- 特徴量ストアの更新・純化（patch-feature-store が所有）
- HITL 入力の受付・構造化（llm-feedback-structuring が所有）
- フィードバック 1 件あたりの改善量などの評価（evaluation-framework が所有）

## Upstream / Downstream

- **Upstream**: primary-anomaly-detection（一次スコア・ROI 候補）、patch-feature-store
  （プロトタイプ近傍検索）、llm-feedback-structuring（適用条件の構造化 JSON）、
  ssl-vit-feature-extraction（roi_embedding の生成元となるパッチ特徴）。
- **Downstream**: evaluation-framework（ROI vs 言語 vs 併用、補正方式間の比較、
  HITL 回復量の評価対象）。

## Existing Spec Touchpoints

- **Extends**: なし（新規）
- **Adjacent**: patch-feature-store、primary-anomaly-detection、llm-feedback-structuring、
  evaluation-framework

## Constraints

- 補正は推論時の条件適用であり、ViT の重み更新を伴わない（researches.md §3.1）。
- 有効期限（expiry）切れの適用条件・プロトタイプは補正に使用しない（researches.md §3.2-4 の
  運用スキーマ、§11 の expiry 間引き）。
