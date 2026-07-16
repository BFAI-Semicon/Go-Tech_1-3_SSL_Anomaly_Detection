# Go-Tech 1-3 SSL Anomaly Detection

工程横断ゼロショット欠陥検出「Promptable Patch Retrieval」の開発リポジトリです。
重み固定の SSL 事前学習済み ViT（DINOv3 主軸）でパッチ特徴を抽出し、特徴量ストア（kNN/FAISS）・
一次異常検出・HITL・LLM 構造化・補正レイヤを組み合わせて、工程・材料・撮像条件をまたぐ
欠陥検出を実現することを目指します。詳細は [`docs/researches.md`](docs/researches.md) を参照してください。

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
- 開発用ツール（pytest, ruff, JupyterLab, onnx/openvino 等）も入れる場合は `mise run sync-dev`。

> 初回は `torch`（cu130）や `anomalib` の取得・ビルドで時間がかかります。ネットワーク接続が必要です。

### 4. GPU（CUDA / Blackwell）が見えるか確認

```bash
mise run gpu-check
```

`torch` のバージョンと、CUDA が利用可能か（`cuda True <GPU名>`）が表示されれば成功です。

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

## 補足・注意

- **anomalib は暫定で本家の GitHub main ブランチを使用**しています（DINOv3 対応は本家
  main に統合済みですが、対応するリリース版（2.6.0 想定）はまだ PyPI 未公開です。
  `pyproject.toml` の `[tool.uv.sources].anomalib` 参照）。
  リリース版が PyPI 公開されたら、`pyproject.toml` のコメントに従って PyPI 版へ切り替えてください。
- **FAISS は `faiss-cpu`** を使用します（aarch64 では GPU 版 wheel が未提供のため）。
- `.venv` はリポジトリに含めません。`mise run sync` でいつでも再構築できます。

## ディレクトリ構成（抜粋）

```text
.
├── README.md
├── mise.toml            # Python/uv・タスク定義
├── pyproject.toml       # 依存関係の定義
├── scripts/
│   └── prepare-python.sh  # takt worktree 用の環境準備スクリプト
├── docs/                # 研究概要・手順
└── .kiro/               # spec 駆動開発（roadmap / specs）
```
