# Project Structure

## Organization Philosophy

Clean-lite設計（ドメイン/ポート/アダプタ）を採用し、ドメインロジックを外部実装（DB、キュー、MLflow）から分離します。将来の差し替えコスト最小化を重視し、ポート（抽象）とアダプタ（実装）を明確に分離します。

## Directory Patterns

### ドメイン層（ユースケース）

**Location**: `/src/domain/`  
**Purpose**: ビジネスロジック・ユースケース（外部実装に非依存）  
**Example**: `CreateSubmission`, `EnqueueJob`, `GetJobStatus`, `GetResults`, `GetVisualizationArtifacts`

### ポート層（抽象インタフェース）

**Location**: `/src/ports/`  
**Purpose**: ドメインが依存する抽象インタフェース  
**Example**:

- `StoragePort`: 提出ファイル保存/参照、アーティファクト一覧/取得（`list_artifacts`, `load_artifact_file`）
- `JobQueuePort`: ジョブ投入/取り出し
- `JobStatusPort`: 状態の保存/参照
- `TrackingPort`: メトリクス記録・`run_id` 生成（Workerのみ使用）

### レート制限層

**Location**: `/src/ports/rate_limit_port.py` + `/src/adapters/redis_rate_limit_adapter.py`  
**Purpose**: ユーザーごとの提出頻度を制御する。  
API 側で Redis カウンター（`leaderboard:rate:{user_id}`）を参照し、3600 秒の時間ウィンドウ内で 10 回を超える提出を拒否する。
**Pattern**:

- `RateLimitPort.increment_submission` は `RedisRateLimitAdapter` を使って `INCR` + `EXPIRE` で値を更新する。  
  TTL 3600 秒でリセットされ、`get_submission_count` は現在値を API の再投入やワーカーの判断に返す。
- `EnqueueJob` では `RateLimitPort` を先行して呼び出し、制限違反を検知する。  
  合格すれば `JobQueuePort` と `JobStatusPort` に渡してキュー投入し、公平性を維持する。

### アダプタ層（実装）

**Location**: `/src/adapters/`  
**Purpose**: ポートの具体実装（ファイルシステム、Redis、MLflow等）  
**Example**:

- `FileSystemStorageAdapter`: `/shared/submissions` へのファイル保存、`artifacts_root` でアーティファクト一覧/取得
- `RedisJobQueueAdapter`: Redis List/Streams によるキュー操作
- `RedisJobStatusAdapter`: Redis Hash による状態管理
- `MLflowTrackingAdapter`: MLflow Tracking Server（HTTP/REST）へのメトリクス記録

### API層（FastAPI）

**Location**: `/src/api/`  
**Purpose**: REST API エンドポイント、認証、バリデーション、レート制限  
**Example**:

- `POST /submissions`: 提出受付
- `POST /jobs`: ジョブ投入
- `GET /jobs/{id}/status|logs|results`: 状態・ログ・結果取得
- `GET /jobs/{id}/visualizations`: 可視化アーティファクト一覧（JSON）
- `GET /jobs/{id}/visualizations/{filename}`: 可視化ファイル取得
- `Authorization: Bearer <token>` ヘッダーを必須とし、`API_TOKENS` 環境変数のカンマ区切りリストと照合してトークンを検証。
- リストが空でもヘッダー自体は required なので、環境変数を変えるだけで公開/非公開を切り替えられる。
- `/submissions` は `metadata` フィールドを JSON としてパースし、`entrypoint`/`config_file` などを含んだ辞書とマージして保存。
- アップロードされたファイルは `NamedBinaryIO` でラップし、ファイル名を保持しつつ `StoragePort` を介して保存される。
- `GET /jobs/{job_id}/logs` は `StoragePort.load_logs(job_id)` を呼び出し、  
  ワーカーが `<LOG_ROOT>/<job_id>.log` として書き出したログを返すことでデバッグ可能にしている。

### Worker層

**Location**: `/src/worker/`  
**Purpose**: Redisキュー消費、anomalib学習・評価、MLflow記録、可視化アーティファクト収集  
**Example**: `JobWorker` クラス（`BRPOP` でキュー待機、ジョブ実行、TrackingPort経由で記録）

#### 可視化サブモジュール

- `visualization_types.py`: `VisualizationType` enum、`VisualizationArtifact`/`VisualizationManifest`、`VisualizationError` 例外
- `visualization_config.py`: `VisualizationConfig` データクラス。`config.yaml` の `visualization` セクションからパース
- `visualization_collector.py`: `VisualizationCollector` クラス。PNGスキャン → サフィックス分類 → 重複排除 → `visualizations/` へ整理、CSV検出

### Streamlit UI層

**Location**: `/src/streamlit/`  
**Purpose**: Web UI（提出フォーム、ジョブ監視、ログ表示）  
**Pattern**: Thin client - REST API呼び出しのみ、ドメインロジック非依存  
**Example**:

- `submit_submission()`: `POST /submissions` 経由でファイルアップロード
- `create_job()`: `POST /jobs` 経由でジョブ投入
- `fetch_job_status()`: `GET /jobs/{id}/status` 経由でステータス取得
- `fetch_job_logs()`: `GET /jobs/{id}/logs` 経由でログ取得
- `build_mlflow_run_link()`: `run_id` から MLflow UI リンク生成
- `has_running_jobs()`: 実行中ジョブ検出
- `get_status_color()`: ステータス色分け（✅❌⏳❓）

**Auto-refresh Pattern**:

- `@st.fragment(run_every="5s")` で `_render_jobs()` を装飾（main関数内で動的適用）
- 実行中（pending/running）ジョブがある場合のみAPIリクエストを実行（パフォーマンス最適化）
- 提出フォームの入力状態は保持される（Fragmentスコープ分離）

**Real-time Log Display Pattern**:

- `_render_job_logs()` でジョブのログを表示
- 実行中ジョブ: 展開状態（`expanded=True`）で最新100行を表示
- 完了/失敗ジョブ: 折りたたみ状態（`expanded=False`）で全ログを表示
- 手動更新ボタン（🔄）で任意タイミングのログ再取得

**Visualization Panel Pattern**:

- `_render_visualization_panel()` で完了ジョブの可視化結果を表示
- `fetch_visualizations()` で API から可視化一覧を取得
- 画像選択（`st.selectbox`）→ original / heatmap / mask / overlay の4列比較表示
- CSV予測ファイル一覧、MLflow Artifacts リンクを表示
- アーティファクトなし時は「可視化結果なし」を表示

#### エントリポイントのライフサイクル（パターン）

- 起動時にログ初期化 → 「待機開始」ログ出力
- `SIGTERM` / `SIGINT` を捕捉して安全に停止（グレースフルシャットダウン）
- 暫定実装では軽量な待機ループでプロセスを維持し、将来的に `JobWorker.run()`（ブロッキング待機 + 実行）へ置換

#### ワーカーの実行パターン

- `JobWorker` は `ARTIFACT_ROOT`（デフォルト `/shared/artifacts`）と `TrackingPort` を受け取る。
- ジョブごとに `<artifact_root>/<job_id>` へ成果物を出力する。
- `_build_command` は entrypoint と設定ファイルを `python` に渡し、`--output` で artifact_path を指定する。
- **投稿者のコードは `{output}/metrics.json` に結果を出力し、MLflowに依存しない**。
- `resource_class`（small=30分、medium=60分）に応じて `RESOURCE_TIMEOUTS` からタイムアウトを選ぶ。
- **リアルタイムログ出力**: `subprocess.Popen()` でサブプロセスを起動し、stdout/stderrをログファイルに直接ストリーミング。`PYTHONUNBUFFERED=1` でバッファリングを無効化。
- `_load_metrics()` で `metrics.json` を読み取り、パラメータとメトリクスを取得。
- `TrackingPort.start_run()` → `log_params()` → `log_metrics()` → `end_run()` で MLflow に記録。
- `run_id` を取得して `JobStatus.COMPLETED` を更新する。
- 例外・タイムアウト・OOM・metrics.json 不在/不正時は `FAILED` にしつつ `error` メッセージを Redis ハッシュへ書き込む。

### 共有ボリューム

**Location**: `/shared/`  
**Purpose**: 提出ファイル、アーティファクト、ログ、MLflow SQLiteバックエンド  
**Example**:

- `/shared/submissions`: 投稿コード・データ
- `/shared/artifacts`: MLflow artifact_root
- `/shared/logs`: 学習・評価ログ（任意）
- `/shared/jobs`: ジョブメタJSON（任意）
- `/shared/mlflow.db`: SQLiteバックエンドストア

### Storage Metadata & Logs

- `FileSystemStorageAdapter` は `UPLOAD_ROOT/<submission_id>` に `metadata.json` を書き込む。
- そのファイルは `files` リストと `user_id`/`entrypoint`/`config_file` などのメタ情報を保持する。
- `UPLOAD_ROOT`/`LOG_ROOT` は起動時に自動作成される。
- `validate_entrypoint` は `/` や `..` を含むパスを拒否し、`.py` で終わるファイルだけを許可してパスの安全性を確保する。
- `load_logs(job_id, tail_lines=N)` は `<LOG_ROOT>/<job_id>.log` を返す。`tail_lines` パラメータで最終N行のみを取得可能（大規模ログのメモリ効率化）。`deque` を使用した効率的なtail処理。

### ドキュメント構成

**Location**: `LeadersBoard/` + `LeadersBoard/docs/`  
**Purpose**: プロジェクトドキュメント（セットアップ、API仕様、デプロイ手順）  
**Pattern**:

- `README.md`: プロジェクト概要、クイックスタート、使用方法、API概要（開発者・運用者向け）
- `README_user.md`: 投稿者向けガイド（API Token、投稿方法、結果確認、サンプルコード、FAQ）
- `docs/api.md`: 詳細API仕様（エンドポイント、認証、レート制限、投稿者コード規約）
- `docs/deployment.md`: デプロイ手順（ローカル/本番、シングル/マルチノード、バックアップ、モニタリング）

**Documentation Principle**:

- README.md: 5分で理解できる概要とクイックスタート（技術者向け）
- README_user.md: プラットフォーム利用者向けの完全ガイド（非技術者でも理解できる）
- docs/api.md: API利用者向けの完全なリファレンス
- docs/deployment.md: 運用者向けの実践的な手順書

### Demo構成

**Location**: `LeadersBoard/demo*/`  
**Purpose**: anomalibモデルの学習・検証デモエントリポイント  
**Example**:

- `demo/`: 基本的な anomalib デモ構成
- `demo_anomalib/`: Anomalib Padim モデルのデモ（config.yaml + main.py）
- `demo_anomalib2/`: パフォーマンスメトリクス対応の Anomalib Padim デモ。`visualize.py` ヘルパーで可視化アーティファクト生成（`main.py` と共に投稿）

### CI/CD構成

**Location**: `.github/workflows/`  
**Purpose**: GitHub Actionsによる継続的インテグレーション・デプロイメント  
**Pattern**:

- `ci.yml`: CIパイプライン（ruff + ユニットテスト、ubuntu-22.04）
- `deploy.yml`: CDパイプライン（self-hosted runner、プリビルドイメージ使用）

### Docker構成

**Location**: `LeadersBoard/` + `.devcontainer/`  
**Purpose**: docker-compose構成（ベース + 環境別オーバーレイ）  
**Example**:

- `LeadersBoard/docker-compose.yml`: ベース構成（nginx, api, worker, redis, mlflow, streamlit）
- `LeadersBoard/docker-compose.prod.yml`: 本番オーバーレイ（ghcr.ioからのプリビルドイメージ参照）
- `.devcontainer/docker-compose.override.yml`: 開発用オーバーレイ（apiのtargetをdevに変更、ソースマウント）
- `docker/api.Dockerfile`: API用Dockerfile（マルチステージ: dev/prod）
- `docker/worker.Dockerfile`: Worker用Dockerfile（GPU対応）
- `docker/streamlit.Dockerfile`: Streamlit UI用Dockerfile（Python 3.13-slim、baseUrlPath=/streamlit/）
- `.env.example`: 環境変数テンプレート
- `.vscode/launch.json`: デバッグ構成（API、Worker、Streamlit、ユニット/統合テスト）

### Nginx 構成

**Location**: `LeadersBoard/nginx/`  
**Purpose**: Basic 認証付きリバースプロキシ設定  
**Pattern**:

- `nginx/conf.d/default.conf`: パスルーティング、Basic 認証、WebSocket 転送
- `nginx/entrypoint.sh`: htpasswd 存在チェック付き起動スクリプト
- `nginx/auth/htpasswd`: 認証情報（Git 管理外、`.gitignore` で除外）

**マルチステージビルド**:

- `api.Dockerfile`は`dev`と`prod`の2ステージを持つ
- 開発時: `.devcontainer/docker-compose.override.yml`で`target: dev`を指定、`sleep infinity`で手動起動
- 本番時: `docker-compose.yml` + `docker-compose.prod.yml` でプリビルドイメージを使用

**本番デプロイパターン**:

```bash
# 本番環境（プリビルドイメージ使用）
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-build
```

**devcontainer.json設定**:

```json
{
  "dockerComposeFile": [
    "../LeadersBoard/docker-compose.yml",
    "./docker-compose.override.yml"
  ],
  "service": "api",
  "workspaceFolder": "/app"
}
```

## Naming Conventions

- **Files**: `snake_case.py`（Pythonモジュール）
- **Classes**: `PascalCase`（例: `CreateSubmission`, `RedisJobQueueAdapter`）
- **Functions**: `snake_case`（例: `enqueue_job`, `get_job_status`）
- **Constants**: `UPPER_SNAKE_CASE`（例: `MLFLOW_TRACKING_URI`, `UPLOAD_ROOT`）

## Import Organization

```python
# 標準ライブラリ
import os
from typing import Optional

# サードパーティ
import mlflow
from fastapi import FastAPI
from redis import Redis

# プロジェクト内（絶対インポート推奨）
from src.domain.create_submission import CreateSubmission
from src.ports.storage_port import StoragePort
from src.adapters.filesystem_storage_adapter import FileSystemStorageAdapter
```

**Path Aliases**: なし（絶対インポート `src.` を使用）

## Code Organization Principles

### 依存方向

- ドメイン → ポート（抽象）のみ依存
- アダプタ → ポート実装（ドメインには非依存）
- API/Worker → ドメイン + アダプタ（DIで注入）

### 境界の責務

- **API**: 認証、入力正規化・バリデーション、冪等化、レート制限、ジョブ投入、ステータス集約、`run_id` とMLflow UIリンク返却（MLflow DB直読なし）
- **Worker**: 学習/評価実行、TrackingPort経由で記録、JobStatusPort経由で進捗更新
- **Streamlit UI**: 提出フォーム、ジョブ監視、ログ表示（REST API経由、ドメイン非依存）
- **ドメイン**: ビジネスロジック（外部実装に非依存）
- **ポート**: 抽象インタフェース（実装詳細を隠蔽）
- **アダプタ**: 具体実装（差し替え可能）
- **EnqueueJob**: `RateLimitPort` で `MAX_SUBMISSIONS_PER_HOUR = 10` と  
  `MAX_CONCURRENT_RUNNING = 1` を順番に検証し、  
  Redis カウンターが示す提出数を超えないときだけ `JobQueuePort` と `JobStatusPort` に渡す。  
  ドメインでレート制限ロジックを分離することで API/Worker はリミッタの内部実装に依存しない。

### テスト戦略

- **ユニットテスト**: ドメイン・ポート実装（モックアダプタ使用）
  - **Location**: `/tests/unit/`
  - **Focus**: ドメインロジック・アダプタの単体テスト、可視化（types/config/collector/artifacts）
  - **Count**: 160件
- **統合テスト**: docker-compose環境でエンドツーエンド（実Redis・MLflow使用）
  - **Location**: `/tests/integration/`
  - **Coverage**: エンドツーエンドフロー、metrics.json読み取り、セキュリティ（パストラバーサル）、エラーハンドリング（OOM、タイムアウト、metrics.json不在/不正）、可視化E2E
  - **Count**: 18件
- **境界テスト**: ファイルサイズ上限、タイムアウト、重複投入、OOM等
- **Total Tests**: 178件

## Maintenance

- updated_at: 2026-02-26
- reason: defect-location-visualization - 可視化関連のファイル・パターン・テスト数更新
