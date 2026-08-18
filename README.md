# Go-Tech 1-3 SSL Anomaly Detection

工程横断ゼロショット欠陥検出「Promptable Patch Retrieval」の開発リポジトリです。
重み固定の SSL 事前学習済み ViT（DINOv3 主軸）でパッチ特徴を抽出し、特徴量ストア（kNN/FAISS）・
一次異常検出・HITL・LLM 構造化・補正レイヤを組み合わせて、工程・材料・撮像条件をまたぐ
欠陥検出を実現することを目指します。詳細は [`docs/researches.md`](docs/researches.md) を参照してください。

## 現状の実装

動いているのは **補正レイヤ本体（開発計画 Phase 0–3）**・**パッチ特徴抽出**・**パッチ特徴ストア**・
**一次異常検出**・**VisA 検証ゲート** の 5 パッケージです。HITL／LLM 構造化・評価基盤・
バージョン管理・オントロジー統合は未着手です。抽出→ストア→一次検出を通す合成ルートは
`visa_gate` にあり、CLI から起動できます。ただし image-level AUROC／AUPRO の計算は
評価基盤（`evaluation-framework`）の担当で未実装のため、ゲートの通し実行はまだ完走しません。

### `src/correction_layer/` — 補正レイヤ

合成 fixture（ランダム埋め込みの FAISS Flat＋手書きドメイン JSON）だけで、一次判定→適用選別→
競合解決→二次判定→最終判定の一連を完結します。

- 層: `model`／`boundary`／`decision`／`engine`
- 公開 API: `CorrectionEngine`・`PrototypeStore`・`load_domain_set`・`ExactAnyAxisMatcher` 等
- 仕様: `.kiro/specs/promptable-correction-layer/`（Phase 0–3 タスク完了）

### `src/feature_extraction/` — パッチ特徴抽出

重み固定の ViT（DINOv3）／CNN で、画像のタイル化からパッチ特徴・パッチ座標・抽出器同一性までを出します。
実重みは timm／anomalib の `TimmFeatureExtractor` 経由で取得します。

- 層: `model`／`boundary`／`geometry`／`engine`
- 公開 API: `FeatureExtractionEngine`・`timm_patch_extractor`・`visa_image_source`・
  `folder_image_source`・設定型（`BackboneConfig`／`TilingConfig`／`PreprocessingConfig`／
  `ExtractionRuntimeConfig`）
- 重みは更新しない（`requires_grad=False`＋`eval`）。ViT は token 出力、CNN は feature map を token 化
- 抽出器同一性（モデル名・重みリビジョン・前処理条件・埋め込み次元・パッチストライド）を特徴に添付
- torch／timm／anomalib の import は `boundary` に閉じ、`import-linter` で強制
- 仕様: `.kiro/specs/ssl-vit-feature-extraction/`（全タスク完了）

### `src/patch_feature_store/` — パッチ特徴ストア

抽出したパッチ特徴を FAISS Flat で保持し、正常近傍探索・プロトタイプの増分登録と集約・coreset 再選抜・
期限切れ剪定・バンク構成・スナップショットの保存／復元までを完結します。

- 層: `model`／`boundary`／`catalog`／`engine`（スナップショット組み立ては `engine_snapshot.py`）
- 公開 API: `PatchFeatureStore` と port 実装（`faiss_flat_index`・`anomalib_coreset_selector`・
  `directory_snapshot_repository`・`utc_clock`）、要求・結果型（`RegistrationRequest`／
  `NormalSearchQuery`／`SimilarityQuery`／`BankSpec`／`DomainCriteria` 等）
- 距離はコサイン固定（保持ベクトルは L2 正規化済み）。近傍探索は距離、識別子指定の問い合わせは
  類似度を返す
- プロトタイプ識別子は単調増加・非再利用。集約時は新しい id を発番して旧→新の対応表を残すので、
  下流は古い id からでも現在の実体をたどれる
- 状態変更は準備→コミットの 2 段。保存は `.staging`／`.previous` を使ったディレクトリ差し替えで、
  部分適用を残さない
- coreset 選択は anomalib `KCenterGreedy`。`faiss`／`torch`／`anomalib` の import は `boundary` に閉じ、
  `import-linter` で強制
- 仕様: `.kiro/specs/patch-feature-store/`（全タスク完了。設計要約は
  [`docs/patch-feature-store-design-overview.html`](docs/patch-feature-store-design-overview.html)）

### `src/primary_anomaly_detection/` — 一次異常検出

正常メモリバンクとの突き合わせでパッチ単位の異常スコアを出し、ヒートマップと ROI 候補まで作ります。
スコア方式は k 近傍距離と Mahalanobis 距離で、重み付き融合できます。

- 層: `model`／`boundary`／`scoring`／`localization`／`engine`
- 公開 API: `PrimaryAnomalyDetector`・`DetectionConfig`・`ScoreMethod`・結果型
  （`PrimaryDetection`／`RoiCandidate`／`ScoringProvenance`）・較正型
  （`MahalanobisCalibration`／`MahalanobisCalibrationSet`）・`NormalNeighborSearch` port と
  実装入口 `store_normal_neighbor_search`
- 距離空間を揃えるため、スコア化の直前に必ず L2 正規化する。ストアの保持ベクトルも正規化済み
- Mahalanobis の較正入力は呼び出し側が渡す。ストアは正常ベクトルの読み出しを公開しない
- ドメイン別の突き合わせに対応。対応する分布が無ければプールへフォールバックし、
  要求した範囲と実際に落ちたかを結果に別々に記録する
- スコア化の前に抽出器同一性を照合し、不一致ならスコアを出さずにエラーにする
- 仕様: `.kiro/specs/primary-anomaly-detection/`（全タスク完了。設計要約は
  [`docs/primary-anomaly-detection-design-overview.html`](docs/primary-anomaly-detection-design-overview.html)）

### `src/visa_gate/` — VisA 検証ゲート

抽出・ストア・一次検出を実データで通す合成ルートです。公開データセット VisA の `train/good` を
既知正常として登録し、`test` 分割をスコア化して成果物と指標を残します。

- 層: `model`／`boundary`／`gate.py`（composition root）／`cli.py`
- 公開 API: `run_visa_gate`・`VisaGateConfig`・`VISA_CATEGORIES`・`GATE_BACKBONE_PRESETS`・
  結果型（`GateRunSummary`／`GateRunConditions`／`GateMetricValues`）・`GateMetrics` port・
  エラー（`VisaGateError` と派生）
- バックボーンはプリセットキーで選ぶ（`dinov3`／`dinov2`／`dino`／`wide_resnet50_2`）。
  タイルサイズはパッチストライドと整合させるためプリセットが持つ
- データセットに触れる前に検証する。ルート不在・未取得かつダウンロード未許可・書き込み不可は
  それぞれ別のエラーで即座に止める（約 16GB の暴発ダウンロードを防ぐ）
- 指標計算は持たない。`GateMetrics` port 越しに評価基盤へ委譲する（現状は未実装のため
  アダプタがエラーを返し、E2E テストは skip される）
- 起動: `mise run visa-gate -- --data-root <VisA のルート> --output-dir <出力先>`

### 検証状態

- `uv run pytest` — 751 passed, 1 skipped（`tests/`。合成 fixture 中心。skip は評価基盤未実装の
  VisA ゲート E2E）
- `PYTHONPATH=src uv run lint-imports` — 依存方向 26 契約が KEPT
- CI: `.github/workflows/python-ci.yml`（ruff・`lint-imports`・pytest）
- 次: [`docs/spec-execution-order.md`](docs/spec-execution-order.md) の順で `evaluation-framework` へ。
  これが入ると VisA 検証ゲートが通しで完走できる

```bash
mise run sync-dev   # 未同期の場合
uv run pytest
uv run ruff check .
PYTHONPATH=src uv run lint-imports
```

## 動作環境

- ターゲット: **NVIDIA DGX Spark**（aarch64 / GB10 Grace Blackwell, CUDA 13）
- Python 3.12（`torch` は CUDA 13 = `cu130` ビルドを使用）
- ツール管理: [`mise`](https://mise.jdx.dev/) + [`uv`](https://docs.astral.sh/uv/)

Python・uv・仮想環境（`.venv`）はすべて `mise` が管理します。手動で Python や venv を用意する必要はありません。

## セットアップ

### 1. mise をインストール（未インストールの場合のみ）

`mise --version` で確認し、未インストールなら [mise 公式ドキュメント](https://mise.jdx.dev/getting-started.html) に従って導入してください。

### 2. ツールを信頼してインストール

リポジトリのルートで実行します。`mise.toml` を信頼（trust）し、Python 3.12 と uv を導入します。

```bash
mise trust && mise install
```

- `mise trust`: この `mise.toml` を信頼済みにする（初回のみ必要）。
- `mise install`: `mise.toml` に定義された Python 3.12 / uv を導入し、`.venv` を作成する。

### 3. 依存関係を同期

`pyproject.toml`（＋ `uv.lock`）に従って、`.venv` にライブラリを一括インストールします。

```bash
mise run sync
```

- 実体は `uv sync --extra llm`（anomalib[cu130] / timm / faiss-cpu / LLM クライアント等）。
- 開発用ツール（pytest, ruff, hypothesis, import-linter 等）も入れる場合は `mise run sync-dev`。
  テスト・lint を回すなら `sync-dev` を推奨します。

> 初回は `torch`（cu130）や `anomalib` の取得・ビルドで時間がかかります。ネットワーク接続が必要です。

### 4. GPU（CUDA / Blackwell）が見えるか確認

```bash
mise run gpu-check
```

`torch` のバージョンと、CUDA が利用可能か（`cuda True <GPU名>`）が表示されれば成功です。
pytest は GPU なしでも実行できます（特徴抽出の E2E は CPU で動き、重みを取得できない環境では skip されます）。

## 仮想環境有効化の確認

```bash
which python        # .../<repo>/.venv/bin/python を指していれば有効
echo $VIRTUAL_ENV   # .venv のパスが表示されれば有効
```

## よく使うコマンド

| コマンド               | 内容                                     |
| ---------------------- | ---------------------------------------- |
| `mise install`         | Python / uv / markdownlint 等を導入      |
| `mise run sync`        | 依存を同期（`uv sync --extra llm`）      |
| `mise run sync-dev`    | 開発用依存も含めて同期                   |
| `mise run gpu-check`   | PyTorch から CUDA が見えるか確認         |
| `mise run visa-gate`   | VisA 検証ゲートを起動（引数は `--` の後）|
| `mise run lint-md`     | Markdown を markdownlint で検査          |
| `mise run lint-md-fix` | Markdown の自動修正可能な指摘を修正      |
| `uv run pytest`        | テストを実行                             |
| `uv run ruff check .`  | Python lint                              |
| `uv run lint-imports`  | 依存方向の契約を検査（`PYTHONPATH=src`） |

## 補足・注意

- **anomalib は PyPI の `>=2.6,<3`** を使用します（DINOv3 は `TimmFeatureExtractor` 経由。
  特徴抽出・データ読み込み・評価指標・coreset 選択に利用し、ストア本体・スコア化は自前）。
- **FAISS は `faiss-cpu`** を使用します（aarch64 では GPU 版 wheel が未提供のため）。
- `.venv` はリポジトリに含めません。`mise run sync` でいつでも再構築できます。
- 方針・依存方向・段階計画は [`.kiro/steering/`](.kiro/steering/) と [`docs/index.md`](docs/index.md) を参照してください。

## ディレクトリ構成（抜粋）

```text
.
├── README.md
├── mise.toml                 # Python/uv・タスク定義
├── pyproject.toml            # 依存・pytest・import-linter 契約
├── src/
│   ├── correction_layer/     # 補正レイヤ（Phase 0–3 実装済み）
│   │   ├── model/            # 型・port・レコード・DomainSet
│   │   ├── boundary/         # スキーマ検証・PrototypeStore・ドメインロード
│   │   ├── decision/         # 一次判定・照合・解決・補正
│   │   └── engine.py         # composition root
│   ├── feature_extraction/   # パッチ特徴抽出（実装済み）
│   │   ├── model/            # 入力型・設定・port
│   │   ├── boundary/         # timm/anomalib アダプタ・抽出器同一性
│   │   ├── geometry/         # タイル配置・パッチ座標
│   │   └── engine.py         # composition root
│   ├── patch_feature_store/  # パッチ特徴ストア（実装済み）
│   │   ├── model/            # プロトタイプ・問い合わせ・設定・port
│   │   ├── boundary/         # FAISS・coreset・スナップショット入出力・時刻
│   │   ├── catalog/          # 台帳・受理・集約・剪定・バンク・操作履歴
│   │   ├── engine.py         # composition root
│   │   └── engine_snapshot.py # スナップショットの組み立てと適用
│   ├── primary_anomaly_detection/ # 一次異常検出（実装済み）
│   │   ├── model/            # 設定・結果・エラー・port
│   │   ├── boundary/         # ストアの近傍探索アダプタ
│   │   ├── scoring/          # k 近傍・Mahalanobis・融合
│   │   ├── localization/     # ヒートマップ合成・ROI 抽出
│   │   └── engine.py         # composition root
│   └── visa_gate/            # VisA 検証ゲート（実装済み）
│       ├── model/            # ゲート設定・プリセット・結果・port
│       ├── boundary/         # データセット検証・抽出/ストア組み立て・成果物・指標
│       ├── gate.py           # composition root
│       └── cli.py            # CLI 引数解釈
├── tests/                    # pytest（合成 fixture 含む）
├── scripts/
│   ├── prepare-python.sh     # takt worktree 用の環境準備スクリプト
│   ├── visa_gate.py          # VisA 検証ゲートの起動スクリプト
│   └── http_server.sh        # docs/ を配信するローカル HTTP サーバ
├── docs/                     # 研究概要・手順・設計メモ
├── .github/workflows/        # python-ci / markdownlint
└── .kiro/                    # steering・specs（仕様駆動開発）
```
