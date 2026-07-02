# takt-sdd 開発手順

`docs/researches.md`（SSL異常検知パイプラインの研究概要書）をtakt-sddで開発する場合の流れを説明します。

## 前提：AIプロバイダの設定（未設定です）

takt-sddは内部のtaktエンジンがAIエージェント（Claude Code / Codex / Cursor Agentなど）を呼び出して動きます。この環境を確認したところ、**プロバイダCLIも設定ファイル（`~/.takt/config.yaml`）もまだ存在しない**ため、最初にこれを用意する必要があります。選択肢は2系統あります。

- **CLI型**: Claude Code（`claude`）や Cursor Agent（`cursor-agent`）のCLIをインストールして使う
- **SDK型**（CLI不要）: APIキーを環境変数で渡す（`TAKT_ANTHROPIC_API_KEY` で `claude-sdk`、`TAKT_OPENAI_API_KEY` で `codex` など）

設定は `~/.takt/config.yaml` に書きます。日本語で運用する場合は `language: ja` を指定します。

```yaml
provider: claude    # または claude-sdk, codex, cursor など
model: sonnet
language: ja
```

## 基本の開発フロー

takt-sddは「**仕様（spec）を先に固め、人間が各フェーズ間で承認しながら進む**」流れです。成果物はすべて `.kiro/specs/{feature}/` に出力されます。

### 手っ取り早く体験する場合（クイックパス）

```bash
cd ~/work/GoTech/Go-Tech_1-3_SSL_Anomaly_Detection
takt-sdd kiro-spec-quick "docs/researches.md に基づき、DINOv3を特徴抽出器とした欠陥検出の一次検出（パッチ特徴抽出と異常スコア化）を実装する..."
```

これ1コマンドで要件（requirements.md）→設計（design.md)→タスク（tasks.md）まで一括生成されます。

### フェーズごとに人間が確認しながら進める場合（推奨）

```bash
# 1. 要件定義（EARS形式のrequirements.mdが生成される）
takt-sdd kiro-spec-requirements -- "実装したい機能の説明..."
#    → .kiro/specs/{feature}/ が作られるのでfeature名を確認し、内容をレビュー

# 2. ギャップ分析（既存コードがある場合のみ。今回は新規なのでスキップ可）
takt-sdd kiro-validate-gap -- "feature={feature}"

# 3. 設計生成（design.md と research.md）
takt-sdd kiro-spec-design -- "feature={feature}"

# 4. 設計レビュー（GO/NO-GO判定が design-review.md に出る）
takt-sdd kiro-validate-design -- "feature={feature}"

# 5. タスク分解（tasks.md）
takt-sdd kiro-spec-tasks -- "feature={feature}"

# 6. 実装(レビュー・デバッグ・検証ゲート付きで自動実装)
takt-sdd kiro-impl -- "feature={feature}"

# 7. 実装検証
takt-sdd kiro-validate-impl -- "feature={feature}"

# 進捗確認はいつでも
takt-sdd kiro-spec-status -- "feature={feature}"
```

各フェーズの後に生成物（Markdown）を人間が読んで修正・承認してから次へ進むのが基本の使い方です。

## このプロジェクトでの進め方の提案

`researches.md` は研究計画全体（特徴抽出、一次検出、HITL、補正レイヤ、評価系など）を含む大きなドキュメントなので、**全体を一度に1つのspecにするのは不向き**です。次のいずれかをおすすめします。

- `takt-sdd kiro-discovery -- "docs/researches.md の内容..."` でアイデアをルーティングし、brief/roadmapに分割してから `kiro-spec-batch` で依存順にspecを複数生成する
- または、自分で機能を切り出して（例:「タイル化＋DINOv3特徴抽出パイプライン」→「PatchCore系異常スコア化」→「特徴量ストア」→…）、1機能ずつ上記のフェーズ実行を回す

## 補足

- 実行時のタイムアウト目安はフェーズあたり15分、実装は30分程度かかることがあります。
- ワークフロー定義をカスタマイズしたい場合のみ `takt-sdd eject --lang ja` でプロジェクトに展開します（通常は不要）。
