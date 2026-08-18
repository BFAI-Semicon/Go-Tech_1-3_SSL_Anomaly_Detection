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
  - MAE 再構成経路の実装（将来検討。researches.md §3.3）
  - anomalib 本体の改修（DINOv3 は anomalib>=2.5.1 の TimmFeatureExtractor で利用可能。
    依存は PyPI の `anomalib[cu130]>=2.6,<3`）

## Constraints

- Python 3.12 固定。DGX Spark 向け torch cu130 aarch64 wheel が cp312 で提供されるため
  （`pyproject.toml` 6-8行目）。
- 実行環境は NVIDIA DGX Spark（aarch64 / GB10 Grace Blackwell / CUDA 13）。torch は
  cu130 index から取得（`pyproject.toml`）。
- anomalib は PyPI の `anomalib[cu130]>=2.6,<3` を使用（DINOv3 は TimmFeatureExtractor 経由。
  利用範囲は特徴抽出・データ読み込み・評価メトリクスで、ストア・スコア化は自前）。
- 公開データセットは VisA（CC BY 4.0、商用可）を使う。MVTec AD は CC BY-NC-SA 4.0 で
  商用不可のため使わない（`docs/visa-validation-gate.md`）。
- FAISS は aarch64 のため CPU 版（`faiss-cpu`）を使用（`pyproject.toml`）。
- DINOv2 等のモデルライセンスは早期に法務確認が必要（`docs/plan.md` リスクと対策）。
- 各 spec で使うライブラリは `docs/library-adoption-proposal.md` の採用提案に従う。
- メモリバンクの版管理は、bank 版管理の着手前（`docs/incremental-development-plan.md`
  Phase 5）に Lance / LanceDB のスパイクを実施し、FAISS＋自作メタデータ層から
  置き換えるかを判断する（`docs/library-adoption-proposal.md` §3）。判断までは
  FAISS 前提の記述を維持する。

## Boundary Strategy

- **Why this split**: researches.md §3.2 の推論フロー6段と §6 の成果物4系統（固定モデル／
  推論パイプライン／UI・運用プロトコル／特徴量ストア）の責務単位に対応させた。各 spec が
  独立に requirements→design→tasks へ進められ、依存は特徴テンソル・ストアレコード・
  構造化 JSON という明示的なデータ契約のみになる。
- **Shared seams to watch**:
  - データセット入力（画像・split・GT マスク）。読み込みは ssl-vit-feature-extraction の
    入力アダプタが所有し、anomalib の型を下流に漏らさない
    （ssl-vit-feature-extraction ↔ primary-anomaly-detection ↔ evaluation-framework）
  - 検証ゲート用に前倒しする image-level AUROC・AUPRO。実装は evaluation-framework が所有し、
    呼び出しは合成ルート `visa_gate` に限る。`primary_anomaly_detection → evaluation_framework`
    は作らない（evaluation-framework ↔ visa_gate）
  - パッチ特徴のテンソル形状・位置/ドメインメタデータ
    （ssl-vit-feature-extraction ↔ patch-feature-store ↔ primary-anomaly-detection）
  - バックボーン同一性（モデル名・重みリビジョン・前処理条件・埋め込み次元）
    （ssl-vit-feature-extraction ↔ patch-feature-store ↔ promptable-correction-layer）
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

- [x] ssl-vit-feature-extraction -- データセット入力アダプタ、タイル化・パッチ化と固定 SSL ViT（DINOv3 主軸。anomalib TimmFeatureExtractor）によるパッチ特徴抽出. Dependencies: none
- [x] patch-feature-store -- FAISS kNN インデックス＋ドメイン分割・coreset・増分追加を備えた特徴量ストア. Dependencies: ssl-vit-feature-extraction
- [x] primary-anomaly-detection -- Mahalanobis／kNN 距離の融合による異常スコア化・ヒートマップ・ROI 候補抽出. Dependencies: ssl-vit-feature-extraction, patch-feature-store
  - 完了: 2026-08-18。合成ルートは `visa_gate`。image-level AUROC／AUPRO は
    `evaluation-framework` 未実装のためゲートの数値通過は未観測
    （`docs/visa-validation-gate.md`）。
- [ ] llm-feedback-structuring -- ROI 注釈＋自然言語コメントの受付と、LLM による運用スキーマ JSON 化・スキーマ検証・監査ログ. Dependencies: primary-anomaly-detection
- [ ] promptable-correction-layer -- roi_embedding とプロトタイプの近傍照合＋適用条件マッチによるスコア再構成と最終判定. Dependencies: ssl-vit-feature-extraction, patch-feature-store, primary-anomaly-detection, llm-feedback-structuring
- [ ] evaluation-framework -- 多指標評価（image-level／AUPRO／合成異常／運用 KPI）と特徴抽出器比較・劣化曲線の評価基盤. Dependencies: ssl-vit-feature-extraction, patch-feature-store, primary-anomaly-detection
  - promptable-correction-layer は依存に含めない。HITL 回復量・補正方式比較の実験実行は
    補正レイヤ完成後になるが、指標・プロトコル定義は独立に進められるため
    （`evaluation-framework/brief.md` Upstream / Downstream 参照）。
  - VisA 検証ゲートが使う image-level AUROC・AUPRO のみ primary-anomaly-detection と
    並行して前倒し実装する。
  - 独自の実機画像は正常のみでラベル・画素マスクが無いため、AUROC 系ではなく過検出率・
    スコア安定性・ドメインシフト影響量を測る専用プロトコルを持つ
    （`docs/normal-only-validation-plan.md`）。
