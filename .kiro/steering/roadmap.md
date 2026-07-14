# Roadmap

## Overview

工程横断ゼロショット欠陥検出「Promptable Patch Retrieval」（`docs/researches.md`）を実装する。
半導体製造では工程・材料・撮像条件の差により教師あり学習モデルの汎化が難しく、欠陥が稀で
ラベル付けコストが高い（researches.md §1）。そこで SSL 事前学習済み ViT（DINOv3 主軸）を
**重み固定**で特徴抽出器として用い、パッチ特徴の正常分布からの逸脱による一次検出、
FAISS ベースの特徴量ストア、HITL（ROI 注釈＋自然言語コメント）、LLM による構造化 JSON、
補正レイヤ（Promptable Patch Retrieval）を組み合わせた推論時適応パイプラインを構築する
（researches.md §3）。

## Approach Decision

- **Chosen**: 重み固定・推論時適応。SSL 事前学習済み ViT の重みは更新せず、正常パッチ特徴の
  メモリバンク追記・HITL プロトタイプ蓄積・構造化フィードバックの適用条件で運用側がドリフトへ
  適応する（researches.md §3.1、§11）。
- **Why**: 欠陥が稀でラベル付けコストが高く、案件ごとの再学習なしで工程・材料・撮像条件を
  またぐ汎化が必要（researches.md §1）。メモリバンク更新は特徴ベクトルの追記に帰着し
  勾配更新が不要（researches.md §11）。
- **Rejected alternatives**:
  - 案件ごとの教師あり再学習 — 工程・材料・撮像条件の差で汎化が難しく、ラベル付けコストが
    高い（researches.md §1）。
  - ローカルでの SSL 事前学習 — SSL 事前学習は配布元（Meta）が実施済みであり、ローカルでは
    学習工程を回さない方針（researches.md §10）。

## Scope

- **In**: researches.md の推論フロー6段（特徴抽出→一次検出→人間フィードバック→LLM 構造化→
  補正レイヤ→最終判定、§3.2）と特徴量ストア（§6、§11）、および評価計画（§7、§12）の実装。
- **Out**:
  - PatchCore 蒸留・既存手法ベース整備（`docs/plan.md` 前半の別テーマ。researches.md には
    含まれないため本 roadmap の対象外）
  - ViT の重み更新・SSL 事前学習の実施（researches.md §3.1 で禁止）
  - anomalib 本体の改修（DINOv3 対応は upstream の PR #3627 / `feature/dinov3` ブランチに依存）

## Constraints

- Python 3.12 固定。DGX Spark 向け torch cu130 aarch64 wheel が cp312 で提供されるため
  （`pyproject.toml` 6-8行目）。
- 実行環境は NVIDIA DGX Spark（aarch64 / GB10 Grace Blackwell / CUDA 13）。torch は
  cu130 index から取得（`pyproject.toml` 59-69行目）。
- anomalib は 2.6.0 の PyPI 公開まで `feature/dinov3` ブランチを暫定使用
  （`pyproject.toml` 70-73行目）。
- FAISS は aarch64 のため CPU 版（`faiss-cpu`）を使用（`pyproject.toml` 22-25行目）。
- DINOv2 等のモデルライセンスは早期に法務確認が必要（`docs/plan.md` リスクと対策）。

## Boundary Strategy

- **Why this split**: researches.md §3.2 の推論フロー6段と §6 の成果物4系統（固定モデル／
  推論パイプライン／UI・運用プロトコル／特徴量ストア）の責務単位に対応させた。各 spec が
  独立に requirements→design→tasks へ進められ、依存は特徴テンソル・ストアレコード・
  構造化 JSON という明示的なデータ契約のみになる。
- **Shared seams to watch**:
  - パッチ特徴のテンソル形状・位置/ドメインメタデータ
    （ssl-vit-feature-extraction ↔ patch-feature-store ↔ primary-anomaly-detection）
  - MAE 再構成経路の出力（再構成誤差の算出は primary-anomaly-detection が所有）
    （ssl-vit-feature-extraction ↔ primary-anomaly-detection）
  - ストアのレコードスキーマ（vit_embedding・annotation・構造化 JSON・適用メタ情報）
    （patch-feature-store ↔ promptable-correction-layer）
  - 検証済みプロトタイプ・正常特徴の登録トリガー（検証は llm-feedback-structuring、
    登録処理は patch-feature-store が所有。依存順序上は seam として扱い循環依存にしない）
    （llm-feedback-structuring ↔ patch-feature-store）
  - 構造化 JSON の運用スキーマ（判定・適用範囲・優先度）
    （llm-feedback-structuring ↔ promptable-correction-layer）
  - 異常スコアマップ・ROI 候補のインターフェース
    （primary-anomaly-detection ↔ promptable-correction-layer ↔ evaluation-framework）
  - 特徴抽出器比較の条件統一（比較用 ImageNet 教師あり CNN を含むバックボーン切り替えと
    前処理条件は ssl-vit-feature-extraction が所有、比較プロトコルは evaluation-framework
    が所有）（ssl-vit-feature-extraction ↔ evaluation-framework）

## Specs (dependency order)

- [ ] ssl-vit-feature-extraction -- タイル化・パッチ化と固定 SSL ViT（DINOv3 主軸）によるパッチ特徴抽出. Dependencies: none
- [ ] patch-feature-store -- FAISS kNN インデックス＋ドメイン分割・coreset・増分追加を備えた特徴量ストア. Dependencies: ssl-vit-feature-extraction
- [ ] primary-anomaly-detection -- Mahalanobis／kNN 距離／MAE 再構成誤差の融合による異常スコア化・ヒートマップ・ROI 候補抽出. Dependencies: ssl-vit-feature-extraction, patch-feature-store
- [ ] llm-feedback-structuring -- ROI 注釈＋自然言語コメントの受付と、LLM による運用スキーマ JSON 化・スキーマ検証・監査ログ. Dependencies: primary-anomaly-detection
- [ ] promptable-correction-layer -- roi_embedding とプロトタイプの近傍照合＋適用条件マッチによるスコア再構成と最終判定. Dependencies: ssl-vit-feature-extraction, patch-feature-store, primary-anomaly-detection, llm-feedback-structuring
- [ ] evaluation-framework -- 多指標評価（image-level／AUPRO／合成異常／運用 KPI）と特徴抽出器比較・劣化曲線の評価基盤. Dependencies: ssl-vit-feature-extraction, patch-feature-store, primary-anomaly-detection
  - promptable-correction-layer は依存に含めない。HITL 回復量・補正方式比較の実験実行は
    補正レイヤ完成後になるが、指標・プロトコル定義は独立に進められるため
    （`evaluation-framework/brief.md` Upstream / Downstream 参照）。
