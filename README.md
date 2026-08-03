# Go-Tech 1-3 SSL Anomaly Detection

工程横断ゼロショット欠陥検出「Promptable Patch Retrieval」の開発リポジトリです。
重み固定の SSL 事前学習済み ViT（DINOv3 主軸）でパッチ特徴を抽出し、特徴量ストア（kNN/FAISS）・
一次異常検出・HITL・LLM 構造化・補正レイヤを組み合わせて、工程・材料・撮像条件をまたぐ
欠陥検出を実現することを目指します。詳細は [`docs/researches.md`](docs/researches.md) を参照してください。

## 現状の実装

いま動いているのは **補正レイヤ本体（開発計画 Phase 0–3）** です。合成 fixture
（ランダム埋め込みの FAISS Flat＋手書きドメイン JSON）だけで、一次判定→適用選別→競合解決→
二次判定→最終判定の一連を完結します。実 ViT・実ストア・バージョン管理・オントロジー統合は未着手です。

| 項目 | 状態 |
| --- | --- |
| パッケージ | `src/correction_layer/`（model／boundary／decision／engine） |
| 公開 API | `CorrectionEngine`・`PrototypeStore`・`load_domain_set`・`ExactAnyAxisMatcher` 等 |
| テスト | `tests/`（合成 fixture 付き）。`uv run pytest` で 168 passed |
| CI | `.github/workflows/python-ci.yml`（ruff・`lint-imports`・pytest） |
| 仕様 | `.kiro/specs/promptable-correction-layer/`（Phase 0–3 タスク完了） |
| 次 | [`docs/spec-execution-order.md`](docs/spec-execution-order.md) の順で特徴抽出・ストア等へ |

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
  補正レイヤのテスト・lint を回すだけなら `sync-dev` を推奨します。

> 初回は `torch`（cu130）や `anomalib` の取得・ビルドで時間がかかります。ネットワーク接続が必要です。

### 4. GPU（CUDA / Blackwell）が見えるか確認

```bash
mise run gpu-check
```

`torch` のバージョンと、CUDA が利用可能か（`cuda True <GPU名>`）が表示されれば成功です。
補正レイヤ単体の pytest は GPU なしでも実行できます。

## 仮想環境有効化の確認

```bash
which python        # .../<repo>/.venv/bin/python を指していれば有効
echo $VIRTUAL_ENV   # .venv のパスが表示されれば有効
```

## よく使うコマンド

| コマンド               | 内容                                |
| ---------------------- | ----------------------------------- |
| `mise install`         | Python / uv / markdownlint 等を導入 |
| `mise run sync`        | 依存を同期（`uv sync --extra llm`） |
| `mise run sync-dev`    | 開発用依存も含めて同期              |
| `mise run gpu-check`   | PyTorch から CUDA が見えるか確認    |
| `mise run lint-md`     | Markdown を markdownlint で検査     |
| `mise run lint-md-fix` | Markdown の自動修正可能な指摘を修正 |
| `uv run pytest`        | 補正レイヤのテストを実行            |
| `uv run ruff check .`  | Python lint                         |

## 補足・注意

- **anomalib は PyPI の `>=2.6,<3`** を使用します（DINOv3 は `TimmFeatureExtractor` 経由。
  特徴抽出のみ利用し、ストア・スコア化は自前）。
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
│   └── correction_layer/     # 補正レイヤ（Phase 0–3 実装済み）
│       ├── model/            # 型・port・レコード・DomainSet
│       ├── boundary/         # スキーマ検証・PrototypeStore・ドメインロード
│       ├── decision/         # 一次判定・照合・解決・補正
│       └── engine.py         # composition root
├── tests/                    # pytest（合成 fixture 含む）
├── scripts/
│   └── prepare-python.sh     # takt worktree 用の環境準備スクリプト
├── docs/                     # 研究概要・手順・設計メモ
├── .github/workflows/        # python-ci / markdownlint
└── .kiro/                    # steering・specs（仕様駆動開発）
```
