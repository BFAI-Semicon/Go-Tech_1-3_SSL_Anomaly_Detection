# Project Structure

## Organization Philosophy

- **ドキュメントと仕様が先** — 研究・設計は `docs/`、機能仕様は `.kiro/specs/`、
  永続方針は `.kiro/steering/`
- **パッケージは責務単位** — `src/` に機能パッケージを並べ、依存は内側（判定スキーマ／
  判定ロジック）へ向ける。将来の `versioning`／`ontology`／`app` もこの向きを崩さない
- **実装は層＋合成** — 各パッケージ内は model（型・port）→ 中間層 → engine（または app）の
  一方向。中間層の名前は関心事で決める（判定なら `decision`、幾何計算なら `geometry`、
  台帳と純粋ロジックなら `catalog`、外部 I/O・外部ライブラリなら `boundary`）。
  同じ中間層のモジュール同士は互いに import しない

## Directory Patterns

### Application packages

**Location**: `src/{package}/`  
**Purpose**: 実行可能な機能単位。実装例は `correction_layer`・`feature_extraction`・
`patch_feature_store`  
**Example**: `model/`・`boundary/`・関心事別の中間層（`decision/`／`geometry/`／`catalog/`）・
`engine.py`（必要なら `engine_snapshot.py` のような第 2 段）・公開 `__init__.py`

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
- **port 実装の入口**: boundary は snake_case のファクトリ関数で公開し、返り値を Protocol 型で
  受ける（`timm_patch_extractor`、`visa_image_source`）。具象クラス名は公開面の契約にしない
- **テスト関数**: `test_should_...`（`test_should_reject_invalid_overlap`）
- **テストファイル**: `tests/` は平坦なので、パッケージを表す接頭辞で名前衝突を避ける
  （`test_store_registry.py`、`test_feature_config.py`）
- **ドメイン軸・スキーマフィールド**: 設計メモの語彙をそのまま（`element_id`、`prototype_ids`）
- **spec 名**: kebab-case（`promptable-correction-layer`）

## Import Organization

```python
from correction_layer.model.ports import AxisMatcher, SimilaritySource
from correction_layer.model.domain_set import DomainSet
from correction_layer.decision.primary import judge_primary
```

- パッケージルートからの絶対 import（`correction_layer...`）を使う
- 中間層同士（`boundary` ⇄ `decision`／`geometry`／`catalog`）の相互 import 禁止。
  配線は `engine`／テスト組み立て側
- 具象ストアや Loader を engine が直接型依存しない。port と注入で閉じる
- torch／timm／anomalib／faiss の import は `boundary` 限定。model・geometry・catalog・engine は
  numpy で書く
- パッケージ間 import も一方向。上流の型は自パッケージの model で受け直し、相互依存を作らない

## Code Organization Principles

1. **1 モジュール 1 関心事** — 一次判定・照合・解決・補正・軸マッチは decision 内で分離
2. **port で差し替え** — Phase 後半の ontology／実ストアは Protocol 実装の注入で足す
3. **公開 API は組み立てに必要な最小面** — Phase 0–3 の自己完結のため合成用シンボルは
   ルート公開してよいが、engine の型注釈は port 側に置く
4. **新規パッケージも同じ層パターン** — `src/` に増える単位は roadmap の spec／
   `docs/package-dependency-direction.md` の塊に対応させる
5. **engine が膨らんだら段を足す** — composition root が大きくなったら関心事を第 2 段の
   モジュールへ移し（例: スナップショット組み立て → `engine_snapshot.py`）、
   layers 契約にもその段を書いて上下関係を固定する
