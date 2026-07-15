# Brief: llm-feedback-structuring

## Problem

一次検出の誤判定（False Positive 等）を体系的に抑制するには、現場オペレータの知見
（ROI の許容／不許容判断と適用範囲・例外条件のコメント）を機械が扱える形に変換する必要が
ある（researches.md §3.2-3〜4、§5）。自然言語コメントのままでは補正レイヤの適用条件として
使えず、変換の失敗や誤適用を追跡する仕組みもない。

## Current State

- ソースコードは未実装。`pydantic>=2.7`（運用スキーマ定義・JSON Schema 生成）、
  `jsonschema>=4.21`（構造化 JSON のスキーマ検証）が依存に定義済み
  （`pyproject.toml` 30-32行目）。
- LLM クライアントは optional extra `llm` に定義済み：vLLM の OpenAI 互換エンドポイント
  ＋ guided_json 用の `openai>=1.40`、Ollama structured outputs 用の `ollama>=0.4`
  （`pyproject.toml` 36-43行目）。vLLM 本体は NVIDIA 提供コンテナで運用する
  （`pyproject.toml` 37行目コメント）。

## Desired Outcome

- オペレータが ROI（欠陥／非欠陥、許容／不許容）と自然言語コメント（適用範囲・例外条件）を
  入力できる（researches.md §3.2-3）。
- LLM がコメントを運用スキーマ（判定、適用範囲、優先度など）の JSON へ変換する
  （researches.md §3.2-4）。
- 変換スキーマと監査ログが成果物として提供される（researches.md §6 の UI／運用プロトコル）。
- スキーマ検証に失敗した変換は監査ログに記録される（`docs/plan.md` リスク対策
  「LLM JSON 化の逸脱：構造化出力＋スキーマ検証、失敗時の監査ログ」）。

## Approach

- 運用スキーマは pydantic で定義し、JSON Schema を生成して jsonschema で検証する
  （`pyproject.toml` 31-32行目）。
- LLM 呼び出しは vLLM の OpenAI 互換 API（guided_json）または Ollama structured outputs で
  構造化出力を強制する（`pyproject.toml` 39-42行目）。
- 入口はオペレータによる ROI 候補レビュー：primary-anomaly-detection が出力した ROI 候補を
  レビューし、注釈＋コメントを付ける運用フローとする（researches.md §3.2-2〜3 の順序）。

## Scope

- **In**: ROI 注釈＋コメントの受付インターフェース（UI／運用プロトコル）、LLM 呼び出し、
  運用スキーマ定義、スキーマ検証、監査ログ。
- **Out**: 構造化 JSON を使った異常スコアの再構成（promptable-correction-layer が所有）、
  プロトタイプ特徴のストア登録処理の実体（patch-feature-store が所有。本 spec は検証済み
  注釈を渡す側）。

## Boundary Candidates

- 受付（ROI＋コメントの入力・保存）と変換（LLM 呼び出し・スキーマ検証）の分離
- 監査ログ（変換成否・適用履歴の記録）の独立モジュール化

## Out of Boundary

- 補正レイヤの適用条件マッチング・スコア再構成（promptable-correction-layer が所有）
- 特徴量ストアのインデックス管理（patch-feature-store が所有）

## Upstream / Downstream

- **Upstream**: primary-anomaly-detection（レビュー対象の ROI 候補・ヒートマップ）。
- **Downstream**: promptable-correction-layer（構造化 JSON を適用条件として消費）、
  patch-feature-store（検証済みプロトタイプ・正常特徴の登録トリガー）。

## Existing Spec Touchpoints

- **Extends**: なし（新規）
- **Adjacent**: primary-anomaly-detection、promptable-correction-layer、patch-feature-store

## Constraints

- vLLM 本体は aarch64／Blackwell では NVIDIA 提供コンテナ（`vllm/vllm-openai:cu130-*`）で
  運用し、本リポジトリにはクライアント側のみを持つ（`pyproject.toml` 36-38行目）。
- 構造化 JSON はスキーマ検証を必須とし、逸脱時は監査ログへ記録する（`docs/plan.md`
  リスクと対策）。
