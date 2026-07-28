# Requirements Document

## Project Description (Input)

一次検出の異常スコアだけでは、現場が許容する既知パターンの過検出（False Positive）を抑制できない。ROI 注釈に基づくプロトタイプ記憶と自然言語由来の適用条件を推論時に統合し、異常スコアを再構成する補正機構（Promptable Patch Retrieval の中核）を実装する（researches.md §3.1、§3.2-5、§5）。

- 欠陥候補 ROI の埋め込み（roi_embedding）とストア内プロトタイプ（vit_embedding）を近傍照合し、類似度閾値および構造化 JSON の適用条件（工程・材料・装置等）を満たすときに異常スコアを再構成する（researches.md §3.2-5）。
- 最終判定として NG、許容（False Positive の抑制）、要確認などを返す（researches.md §3.2-6）。
- 補正方式（スコア再重み付け／閾値適応／ラベル上書き）と条件ソース（ROI のみ／言語のみ／併用）を設定で切り替え可能にし、評価実験の比較軸に対応する（researches.md §5）。
- 近傍照合は patch-feature-store の kNN 検索を利用し、適用条件マッチは llm-feedback-structuring が生成した運用スキーマ JSON（判定・適用範囲・優先度）を評価する。
- 判定スキーマ・優先順位チェーン・バージョン管理の詳細設計は `docs/structured-json-versioning/README.md` に従い、実装は `docs/incremental-development-plan.md` の Phase 0–7 で段階化、採用ライブラリは `docs/library-adoption-proposal.md` の提案に従う。
- スコープ外: プロトタイプの登録・coreset 管理（patch-feature-store）、構造化 JSON の生成（llm-feedback-structuring）、補正効果の定量評価（evaluation-framework）。
- 制約: 補正は推論時の条件適用であり ViT の重み更新を伴わない（researches.md §3.1）。有効期限（expiry）切れのプロトタイプは補正に使用しない（researches.md §11）。

詳細は `.kiro/specs/promptable-correction-layer/brief.md` を参照。

## Requirements
<!-- Will be generated in /kiro-spec-requirements phase -->
