# Project Structure

## Organization Philosophy

- **ドキュメントと仕様が先** — 研究・設計は `docs/`、機能仕様は `.kiro/specs/`、
  永続方針は `.kiro/steering/`
- **パッケージは責務単位** — `src/` に機能パッケージを並べ、依存は内側（判定スキーマ／
  判定ロジック）へ向ける。将来の `versioning`／`ontology`／`app` もこの向きを崩さない
- **実装は層＋合成** — 各パッケージ内は model（型・port）→ boundary／decision →
  engine（または app）の一方向。decision モジュール同士は互いに import しない

## Directory Patterns

### Application packages

**Location**: `src/{package}/`  
**Purpose**: 実行可能な機能単位。現時点の実装例は `correction_layer`  
**Example**: `model/`・`boundary/`・`decision/`・`engine.py`・公開 `__init__.py`

### Tests next to contract

**Location**: `tests/`  
**Purpose**: パッケージ横断の pytest。fixture は合成データ（例: `tests/fixtures/domains/`）  
**Example**: モジュール単位の `test_*.py` と E2E（`test_engine_e2e.py`）

### Design authority in docs

**Location**: `docs/`  
**Purpose**: 研究概要・段階計画・ライブラリ選定・依存方向など人間が読む権威メモ  
**Example**: 分割セットはサブフォルダ（`structured-json-versioning/`）に置き、
親に案内ファイルを残す。索引 `docs/index.md` はトップレベル Markdown を日付降順で列挙

### Spec-driven delivery

**Location**: `.kiro/specs/{feature}/`  
**Purpose**: 機能ごとの requirements／design／tasks／research  
**Example**: roadmap の 6 spec（特徴抽出→ストア→一次検出→LLM 構造化→補正→評価）

## Naming Conventions

- **パッケージ／モジュール**: snake_case（`correction_layer`、`domain_loader.py`）
- **型・クラス**: PascalCase（`CorrectionEngine`、`ExactAnyAxisMatcher`）
- **関数**: snake_case（`load_domain_set`、`judge_primary`）
- **ドメイン軸・スキーマフィールド**: 設計メモの語彙をそのまま（`element_id`、`prototype_ids`）
- **spec 名**: kebab-case（`promptable-correction-layer`）

## Import Organization

```python
from correction_layer.model.ports import AxisMatcher, SimilaritySource
from correction_layer.model.domain_set import DomainSet
from correction_layer.decision.primary import judge_primary
```

- パッケージルートからの絶対 import（`correction_layer...`）を使う
- `boundary` ⇄ `decision` の相互 import 禁止。配線は `engine`／テスト組み立て側
- 具象ストアや Loader を engine が直接型依存しない。port と注入で閉じる

## Code Organization Principles

1. **1 モジュール 1 関心事** — 一次判定・照合・解決・補正・軸マッチは decision 内で分離
2. **port で差し替え** — Phase 後半の ontology／実ストアは Protocol 実装の注入で足す
3. **公開 API は組み立てに必要な最小面** — Phase 0–3 の自己完結のため合成用シンボルは
   ルート公開してよいが、engine の型注釈は port 側に置く
4. **新規パッケージも同じ層パターン** — `src/` に増える単位は roadmap の spec／
   `docs/package-dependency-direction.md` の塊に対応させる
