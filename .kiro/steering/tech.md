# Technology Stack

## Architecture

クリーンアーキテクチャ風の依存方向。内側は補正レイヤの判定スキーマと判定ロジック、
外側はバージョン管理・オントロジー・アプリ合成（`docs/package-dependency-direction.md`）。
依存は常に内側へ。差し替え点は Protocol（例: `SimilaritySource`・`AxisMatcher`）で逆転する。

実装済みパッケージは `correction_layer`・`feature_extraction`・`patch_feature_store`・
`primary_anomaly_detection`・`visa_gate`。前 4 つは同じ層パターンで、中間層の名前だけが
関心事に応じて変わる。`visa_gate` は合成ルート専用で、検出ロジックを持たない。

- `model` — 型・設定・port（最内側）
- 中間層 — 互いに独立し model のみに依存（判定は `decision`、幾何計算は `geometry`、
  台帳と純粋ロジックは `catalog`、スコア化は `scoring`、ヒートマップ／ROI は
  `localization`、外部 I/O・外部ライブラリは `boundary`）
- composition root — 具体実装ではなく port を注入される。ドメインパッケージは `engine`、
  合成ルートパッケージは `gate`（＋ `cli`）。関心事が増えたら `engine_snapshot` のように
  第 2 段を切り出し、layers 契約にも段を足す

外部 ML ライブラリ（torch／timm／anomalib／faiss）は `boundary` の内側だけで import する。
`primary_anomaly_detection` はこれらを直接 import せず、ストアへの到達も
`boundary/store_neighbors` に閉じる。パッケージ間の依存も一方向。
`patch_feature_store` → `feature_extraction`、`visa_gate` → 抽出／ストア／一次検出、
を許し、逆流と相互依存は forbidden 契約で止める。
`primary_anomaly_detection → evaluation_framework` は作らない（指標は port 越し。
実装は評価基盤が所有し、呼び出しは合成ルートに限る）。
層間・モジュール間の依存方向とこの禁止規則は `pyproject.toml` の contracts に書き、
`import-linter` で CI 検査する。

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
| coreset 選択               | anomalib `KCenterGreedy`。自作しない                              |
| ストア永続化               | `numpy.save`＋JSON／JSON Lines。スキーマは pydantic で検証        |
| ドメイン定義・補正レコード | pydantic モデルが権威。JSON Schema は派生                         |
| 性質テスト・依存検査       | hypothesis、import-linter                                         |
| ライブラリ選定の詳細       | `docs/library-adoption-proposal.md` に従う                        |

## Development Standards

### Type Safety

- 共有契約は pydantic／`StrEnum`／`Protocol`／frozen dataclass
- 「定義では `any` 可・入力では不可」のような二重契約は型を分ける（例: `DomainAxes` vs `ConcreteDomainAxes`）
- 公開面で具体実装に固定せず、差し替え seam は Protocol にする
- 設定モデルは pydantic `extra="forbid"`＋validator で不正値を構築時に拒否する
- パッケージ間を渡る数値は `np.float32` の C 連続配列。形状は型側に明記する（例: 特徴は `(N, D)`）

### Code Quality

- ruff（`line-length = 100`、`target-version = py312`）
- Markdown は markdownlint-cli2（`mise run lint-md`）
- コードファイルがおおよそ 300 行を超えたら関心事単位の分割を検討する
- フィールドは 1 意味・必要最小限・具体名（曖昧な `data`／`status` 等を避ける）
- 自明なコメントは書かない

### Testing

- pytest（`pythonpath = ["src"]`、`testpaths = ["tests"]`）
- テスト関数名は `test_should_...` で期待する振る舞いを述べる
- 合成 fixture で骨格を検証。決定性・集合等価は hypothesis を使う
- 実重みが必要な E2E は取得できなければ `pytest.skip`（例: `BackboneUnavailableError`）。
  数値の再現性は別プロセスで再計算したハッシュ一致で確認する
- フェーズ完了条件は「動く状態＋pytest」

### CI

`.github/workflows/python-ci.yml` が main への push と PR で ruff → lint-imports → pytest を通す。
ローカルでも同じ 3 つを揃えてから完了扱いにする。

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

uv run ruff check .
PYTHONPATH=src uv run lint-imports
uv run pytest
mise run visa-gate -- --data-root <VisA> --output-dir <out>
```

## Key Technical Decisions

- **重み固定・推論時適応** — ViT を更新せず、メモリバンク／プロトタイプ／適用条件で適応する
- **特徴抽出器は Protocol で切替** — 実装は DINOv3（anomalib `TimmFeatureExtractor`）。
  比較用 DINOv2／DINO／ImageNet CNN はバックボーン名の設定切替。MAE は将来検討
- **anomalib は特徴抽出・データ読み込み・指標** — ストア・スコア化は自前。依存は PyPI `>=2.6,<3`。
  anomalib の型はアダプタで受けて下流に漏らさない
- **バックボーン同一性は特徴と一緒に運ぶ** — モデル名・重みリビジョン・前処理条件・埋め込み次元・
  パッチストライドを解決して出力に添付する。ストアや補正レイヤはこれで互換性を判定する
- **プロトタイプ識別子は単調増加・非再利用** — 集約時は新しい id を発番し、旧→新の対応表を残す。
  同じ id が別のベクトルを指す状態を作らないため。下流の参照追従はこの対応表を使う
- **距離尺度はコサインに固定** — 保持するベクトルは L2 正規化済み。近傍検索は距離
  （1 − 類似度）、識別子指定の問い合わせは類似度で返す（補正レコードのしきい値が類似度）
- **状態変更は準備 → コミットの 2 段** — 索引と台帳のように二重に持つ状態は、計画を確定してから
  順に反映する。複数ファイルの更新はディレクトリ差し替えで行い、部分適用を残さない
- **未実装パッケージへの依存は合成ルートに閉じる** — 指標計算は `evaluation_framework` が所有する。
  検出パッケージから評価基盤を import せず、合成ルート（`visa_gate`）が `GateMetrics` port で呼ぶ。
  実装前はアダプタが失敗し、E2E は skip する
- **ストアは正常ベクトルの読み出しを公開しない** — Mahalanobis 較正の入力は呼び出し側が渡す。
  較正型は検出器の引数型なので公開面に出す。内部のスコア関数は公開しない
- **公開データセットは VisA** — CC BY 4.0（商用可）。CC BY-NC-SA 4.0 の MVTec AD は使わない。
  spec 4 の完了条件は VisA 検証ゲート（`docs/visa-validation-gate.md`）。配線は `visa_gate`。
  オリジナルデータ用の合成ルートは `visa_gate` に足さない
  （`docs/original-data-primary-detection.md`）
- **正常のみの実機データでは AUROC 系を使わない** — 過検出率・安定性・ドメインシフト影響量で
  評価する。分割は複数バンク＋共通評価集合、グループキーはウェハ／ロット／撮像日
  （`docs/normal-only-validation-plan.md`）
- **FAISS は CPU** — aarch64 で公式 GPU wheel が無い。必要なら後でソースビルド／cuVS を検討
- **LLM ランタイムはコンテナ側** — アプリ依存は OpenAI 互換／Ollama クライアントに閉じる
- **仕様駆動** — 機能は `.kiro/specs/{feature}/` で requirements→design→tasks→impl。
  応答言語は日本語、プロジェクト Markdown も仕様の `spec.json.language` に合わせる
