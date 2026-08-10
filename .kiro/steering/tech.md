# Technology Stack

## Architecture

クリーンアーキテクチャ風の依存方向。内側は補正レイヤの判定スキーマと判定ロジック、
外側はバージョン管理・オントロジー・アプリ合成（`docs/package-dependency-direction.md`）。
依存は常に内側へ。差し替え点は Protocol（例: `SimilaritySource`・`AxisMatcher`）で逆転する。

実装済みの最初のパッケージ `correction_layer` は次の層に分かれる。

- `model` — 型・port・レコード・DomainSet（最内側）
- `boundary` / `decision` — 互いに独立。model のみに依存
- `engine` — composition root。具体ストアではなく port を注入される

層間・モジュール間の import は `import-linter` で CI 検査する。

## Core Technologies

- **Language**: Python 3.12 固定（`<3.13`）
- **Runtime target**: NVIDIA DGX Spark（aarch64 / Grace Blackwell / CUDA 13）
- **Tooling**: mise（Python / uv / Node）＋ uv（`.venv`・lock）
- **ML stack**: PyTorch cu130、anomalib（>=2.6、<3）、timm、faiss-cpu、numpy／scipy／sklearn
- **Schema / validation**: pydantic v2、jsonschema
- **LLM clients**（optional extra）: openai（vLLM 互換）、ollama

## Key Libraries（パターンに効くものだけ）

| 領域                       | 採用の型                                                          |
| -------------------------- | ----------------------------------------------------------------- |
| 特徴抽出                   | anomalib `TimmFeatureExtractor` + timm（DINOv3）                  |
| データ読み込み             | anomalib `anomalib.data`（VisA／Folder／Tabular）をアダプタで包む |
| 評価メトリクス             | anomalib／torchmetrics／scikit-learn を呼ぶ。自作しない           |
| 近傍探索                   | FAISS Flat（CPU）。版管理着手前に Lance／LanceDB スパイク予定     |
| ドメイン定義・補正レコード | pydantic モデルが権威。JSON Schema は派生                         |
| 性質テスト・依存検査       | hypothesis、import-linter                                         |
| ライブラリ選定の詳細       | `docs/library-adoption-proposal.md` に従う                        |

## Development Standards

### Type Safety

- 共有契約は pydantic／`StrEnum`／`Protocol`／frozen dataclass
- 「定義では `any` 可・入力では不可」のような二重契約は型を分ける（例: `DomainAxes` vs `ConcreteDomainAxes`）
- 公開面で具体実装に固定せず、差し替え seam は Protocol にする

### Code Quality

- ruff（`line-length = 100`、`target-version = py312`）
- Markdown は markdownlint-cli2（`mise run lint-md`）
- コードファイルがおおよそ 300 行を超えたら関心事単位の分割を検討する
- フィールドは 1 意味・必要最小限・具体名（曖昧な `data`／`status` 等を避ける）
- 自明なコメントは書かない

### Testing

- pytest（`pythonpath = ["src"]`、`testpaths = ["tests"]`）
- 合成 fixture で骨格を検証。決定性・集合等価は hypothesis を使う
- フェーズ完了条件は「動く状態＋pytest」

## Development Environment

### Required Tools

- mise、uv、Python 3.12、Node（markdownlint 用）
- GPU 確認: `mise run gpu-check`

### Common Commands

```bash
mise trust && mise install
mise run sync        # uv sync --extra llm
mise run sync-dev    # + pytest / ruff / hypothesis 等
mise run gpu-check
mise run lint-md
```

## Key Technical Decisions

- **重み固定・推論時適応** — ViT を更新せず、メモリバンク／プロトタイプ／適用条件で適応する
- **特徴抽出器は Protocol で切替** — 実装は DINOv3（anomalib `TimmFeatureExtractor`）。
  比較用 DINOv2／DINO／ImageNet CNN はバックボーン名の設定切替。MAE は将来検討
- **anomalib は特徴抽出・データ読み込み・指標** — ストア・スコア化は自前。依存は PyPI `>=2.6,<3`。
  anomalib の型はアダプタで受けて下流に漏らさない
- **公開データセットは VisA** — CC BY 4.0（商用可）。CC BY-NC-SA 4.0 の MVTec AD は使わない。
  spec 4 の完了条件は VisA 検証ゲート（`docs/visa-validation-gate.md`）
- **正常のみの実機データでは AUROC 系を使わない** — 過検出率・安定性・ドメインシフト影響量で
  評価する。分割は複数バンク＋共通評価集合、グループキーはウェハ／ロット／撮像日
  （`docs/normal-only-validation-plan.md`）
- **FAISS は CPU** — aarch64 で公式 GPU wheel が無い。必要なら後でソースビルド／cuVS を検討
- **LLM ランタイムはコンテナ側** — アプリ依存は OpenAI 互換／Ollama クライアントに閉じる
- **仕様駆動** — 機能は `.kiro/specs/{feature}/` で requirements→design→tasks→impl。
  応答言語は日本語、プロジェクト Markdown も仕様の `spec.json.language` に合わせる
