# Research & Design Decisions — promptable-correction-layer

## Summary

- **Feature**: `promptable-correction-layer`
- **Discovery Scope**: New Feature（リポジトリ内は greenfield。ただし設計メモ `docs/structured-json-versioning/` が判定スキーマ・競合解決の権威として存在するため、外部調査ではなくリポジトリ内資料の突合を主体とした discovery を実施）
- **Key Findings**:
  - スコープは `docs/incremental-development-plan.md` の Phase 0–3 に限定される。永続化・バージョン管理（Phase 4–6）、オントロジー（Phase 7）、実パイプライン統合（Phase 8）は含まない。Phase 0–3 は合成データのみで判定ロジックを固める段階であり、ファイル形式のマイグレーションが発生しない。
  - 設計メモ §13 の未決事項のうち、Phase 2 の実装をブロックする「`params` の持ち方」「`match.similarity_threshold` の距離尺度」の 2 点は本設計で確定する必要がある（計画自身が「ここで確定する」と明記）。
  - 優先順位チェーン（§9.1）は「総順序である」という数学的性質が要件（7.7 の決定性）であり、`hypothesis` による property-based testing の採用が `docs/library-adoption-proposal.md` §2 で指定済み。ルールエンジンの採用は同 §7 で明示的に見送り（決定性・監査可能性のため自作＋hypothesis が正解）。
  - `src/` 配下にソースコードは存在しない（`pyproject.toml`・`docs/`・`.kiro/` のみ）。既存パターンの踏襲対象はなく、パッケージ構成は本設計で新規決定する。
  - 設計レビュー（2026-07-29）で `match.scope` を廃止した。推論時に値が確定しないキー（`defect_class` 等）は照合不能であり、適用条件はドメイン軸＋プロトタイプ類似度の 2 系統に限定する（下記 Design Decisions）。
  - 設計レビュー（2026-07-30）で `match` の類似度条件（`prototype_ids`／`similarity_threshold`）を対で任意化した。類似度条件を持たないレコードはドメイン軸のみで適用される広域補正（ドメイン単位の閾値調整等）を表す（下記 Design Decisions）。

## Research Log

### スコープと段階計画の確定

- **Context**: requirements の Boundary Context が Phase 0–3 限定を宣言しており、設計の境界を段階計画と突合する必要があった。
- **Sources Consulted**: `docs/incremental-development-plan.md`（Phase 0–3 の定義）、`.kiro/specs/promptable-correction-layer/requirements.md`（Boundary Context）、`.kiro/specs/promptable-correction-layer/brief.md`、`.kiro/steering/roadmap.md`
- **Findings**:
  - Phase 0: `src/` パッケージ構成・pytest・ruff の整備、合成 fixture（ランダム埋め込みの FAISS Flat インデックス＋手書きドメイン JSON 1 個）、fixture ロードと kNN 検索の確認。
  - Phase 1: 最小 E2E（固定パス 1 ファイルのドメイン JSON → 一次判定 → `OverrideNegative` × `LabelOverride` 1 レコード適用 → NG／許容）。`match` は `prototype_ids`＋`similarity_threshold` のみ。
  - Phase 2: pydantic による全フィールドモデル化（4 action × 3 method＋null）、jsonschema 構造検証。
  - Phase 3: 複数ドメイン合成（`any` ワイルドカードのみ）と優先順位チェーン、テーブル駆動テスト＋hypothesis。
- **Implications**: トップレベルのバージョン管理メタ（`domain_id`／`domain_version`／`domain_source_ontology_version`／`target_ontology_version`／`built_against_bank_snapshot_id`／`domain_representations_by_ontology_version`。§8.1）は Phase 0–3 のドメイン定義 JSON に**含めない**（`domain_id`／`domain_version` は Phase 4、`built_against_bank_snapshot_id` は Phase 5、オントロジー系 3 フィールドは Phase 7 の責務）。要素単位の `ontology_version`（§6.3。トップレベルメタとは別のフィールド）も含めない（Phase 7 のオントロジー統合責務）。含めると Phase 4 以降で正式なアーティファクトスキーマと二重定義になる。合成フィクスチャ用の簡易スキーマ（ドメイン軸 4 つ＋`elements[]`）を本 spec が所有する。

### 判定スキーマと優先順位チェーンの権威確認

- **Context**: 補正レコードの解釈（action／method／match）と競合解決の仕様の裏取り。
- **Sources Consulted**: `docs/structured-json-versioning/correction-layer.md`（§6・§9）、`docs/structured-json-versioning/versioning-model.md`（§3.1 削除・§4.2 ドメイン合成）、`docs/structured-json-versioning/file-layout-and-samples.md`（§8.1 レコードサンプル）
- **Findings**:
  - action は 4 値（`OverrideNegative`／`OverridePositive`／`KeepPrimary`／`ReviewRequired`）、method は 3 値＋null。`KeepPrimary`／`ReviewRequired` は method null（§6.2）。
  - 優先順位チェーンは specificity → `ReviewRequired` 短絡 → safety（`OverridePositive` > `KeepPrimary` > `OverrideNegative`）→ recency（`recorded_at`）→ `element_id` 大の総順序（§9.1）。
  - `ReviewRequired` 短絡は「同 specificity の勝ち集合内」でのみ効く（specificity に従属。§9.1 rule2）。
  - 削除は要素の実削除で表現し（tombstone なし）、`KeepPrimary` は有効集合に残って specificity で広域を遮蔽する能動マスク（§3.1・§6.1）。この挙動差が要件 6.4／7.6 に対応する。
  - `element_id` は全ドメインで一意の整数、`prototype_ids` は JSON 整数（int64）、`recorded_at` は UTC。
- **Implications**: チェーンは既存フィールドのみから導出され per-record priority を持たない。`priority.json` 上書きは Phase 6 なので本設計に含めない。

### 類似度尺度の確定（§13 未決 → 本設計で確定）

- **Context**: `match.similarity_threshold` の距離尺度（cosine か L2 か、大小方向、FAISS メトリック対応）は設計メモ §13 で未決。Phase 2 の実装がブロックされるため確定が必要。要件 2.5 は「近傍検索と同一の類似度尺度で解釈する」ことを要求。
- **Sources Consulted**: `docs/2025-2026_survey.md`（研究動向）、各手法の原典・公式実装（PatchCore CVPR 2022 / faiss `IndexFlatL2`、MuSc ICLR 2024、AnomalyDINO WACV 2025、Dinomaly CVPR 2025、HiMatch-AD 2026、AnomalyVFM CVPR 2026）、`docs/structured-json-versioning/operations.md` §13、`pyproject.toml`（faiss-cpu）
- **Findings**（2026-07-29 に距離尺度の文献調査を実施）:
  - CNN 特徴の世代（PatchCore 原典＝WideResNet50）は**非正規化 L2**（公式実装が faiss `IndexFlatL2`、anomalib 実装も Euclidean）。
  - ViT／foundation model 特徴の世代は **cosine が支配的**。DINOv2 パッチ特徴の deep nearest neighbor という本プロジェクトの一次検出と同型の先行研究 AnomalyDINO は cosine 距離 \( d(x,y)=1-\langle x,y\rangle/(\|x\|\|y\|) \) を明示採用。DINOv3 系の後続（HiMatch-AD）も検索・異常応答とも cosine。再構成型の Dinomaly（DINOv2）も異常マップは cosine。CLIP 系 zero-shot（WinCLIP 等）は埋め込み空間の構造上 cosine。
  - 例外は MuSc（ViT パッチトークンに L2）で、「ViT なら必ず cosine」とまでは言えないが、DINO 系の後続には踏襲されていない。
  - L2 正規化済みベクトルでは \( \|x-y\|^2 = 2-2\cos(x,y) \) の単調関係により最近傍の順位は cosine と同一。差が出るのは正規化の有無（ノルム情報を捨てるか）と閾値の意味論のみ。
  - FAISS では L2 正規化済みベクトルに対する `METRIC_INNER_PRODUCT`（`IndexFlatIP`）が cosine 類似度の厳密計算になる。Flat インデックスなので近似誤差はない。
- **Implications**: 決定は下記 Design Decisions を参照。一次判定の異常スコアと `similarity_threshold` の充足判定を同一の cosine 類似度関数（`prototype_store` に一元化）から導出することで要件 2.5 を構造的に保証する。

### `params` の持ち方の確定（§13 未決 → 本設計で確定）

- **Context**: method 別パラメータの形が未決（§6.2 は `params.weight`／`params.threshold_delta` を例示）。
- **Sources Consulted**: `docs/structured-json-versioning/correction-layer.md` §6.2、`docs/structured-json-versioning/file-layout-and-samples.md` §8.1（`"params": {}` の例）
- **Findings**: §8.1 のサンプルは `LabelOverride` で `params: {}`。§6.2 は `ScoreReweight` に `weight`、`ThresholdAdapt` に `threshold_delta` を対応させている。
- **Implications**: `params` は常に JSON オブジェクトとし、内容を method で決める（下記 Design Decisions）。

### `prototype_ids` の充足意味論（ANY）

- **Context**: 要件 2.2 の「prototype_ids に含まれるプロトタイプとの類似度が条件を満たした」は、リスト内の全プロトタイプか任意の 1 つかが明示されていない。
- **Sources Consulted**: `docs/structured-json-versioning/correction-layer.md` §9 規則 2（「`match.prototype_ids` はリストのため、一部が残れば残存分で適用する」）
- **Findings**: 「一部が残れば残存分で適用」は、リストが連言（AND）ではなく選言的なアンカー集合であることを含意する。全要素充足が必要なら一部欠落で適用不能になるはずである。
- **Implications**: 「`prototype_ids` のいずれか 1 つとの類似度が閾値以上なら充足（ANY・max 類似度で判定）」を採用（下記 Design Decisions）。

### specificity の暫定定義（§13 未決の部分確定）

- **Context**: §9.1 は「`domain` タプルがより具体的な方を優先（完全指定 > `any`）」とするが、多軸指定時の具体度スコアの厳密定義は §13 で未決。Phase 3 の決定的な競合解決（要件 6.3・7.1）には定義の確定が必要。ただし上位クラス階層（Phase 7）を含む完全な厳密化は本スコープ外。
- **Sources Consulted**: `docs/structured-json-versioning/correction-layer.md` §9.1、`docs/structured-json-versioning/versioning-model.md` §4.2（合成順: 装置指定 → 材料指定 → 工程全体 `any`）、`docs/structured-json-versioning/operations.md` §13
- **Findings**: §4.2 の合成順はドメイン軸の具体指定数に基づく順序である。当初案は第 2 キーに `match.scope` の条件キー数を置く辞書式比較だったが、`match.scope` 自体の廃止（下記 Design Decisions）により第 2 キーはいったん消滅した。その後、類似度条件の任意化（下記 Design Decisions）により「同一ドメイン軸数でも適用範囲の粒度が異なる」ケースが生じ、第 2 キーとして類似度条件の有無を再導入した。
- **Implications**: Phase 3 では「辞書式比較（第 1 キー: 非 `any` ドメイン軸数 0–4、第 2 キー: 類似度条件の有無）」を暫定定義として採用（下記 Design Decisions）。Phase 7 の上位クラス階層導入時に再検証が必要（Revalidation Trigger として design.md に記録）。

### `match.scope` の要否（設計レビューによる廃止）

- **Context**: 設計メモ §6.3 は `match` に `scope`（ドメイン軸以外の付帯条件。例 `defect_class`／`measurement`）を持たせていた。設計レビュー（2026-07-29）で「推論時に入力パッチは `defect_class` を持たない（一次判定は正常分布からの逸脱のみで欠陥種別を出さない）ため照合できない」という指摘を受け、ドメイン以外の scope 照合の要否を再検討した。
- **Sources Consulted**: `docs/structured-json-versioning/correction-layer.md` §6.3、`docs/structured-json-versioning/ontology.md` §5（scope キーの想定値）、`docs/researches.md` §3.2（プロトタイプ記憶は ROI 注釈に基づく許容／不許容）、`.kiro/steering/roadmap.md`（欠陥分類を担う spec は存在しない）
- **Findings**:
  - `defect_class` は推論時に未知（欠陥分類器は計画に存在しない）。キー欠落＝不一致の意味論では、当該キーを条件に持つレコードは永続的に不一致となり、エラーにならずに静かに死ぬ。
  - `defect_class` の実態は「その HITL 判定がなぜ下されたか」という来歴であり、来歴は既存の `source_ref` → 独立監査ログ（llm-feedback-structuring 所有）が受け持つ。`match`（適用条件）に来歴を混ぜるのはフィールド設計原則（1 フィールド 1 意味）に反する。
  - `measurement` 等の推論時に既知の値はカテゴリ文脈であり、必要になればドメイン軸の追加として扱える（別の照合機構を二重に持つ理由がない）。
  - 外観による判別は `prototype_ids`＋`similarity_threshold` が受け持つ。FN 救済（OverridePositive）でも判別力は不許容プロトタイプ（注釈された欠陥 ROI の登録）への類似で表現され、scope の出番はない。
- **Implications**: `match.scope` を廃止し、適用条件をドメイン軸＋プロトタイプ類似度の 2 系統に限定する（下記 Design Decisions）。設計メモ §6.3・§9.1 も同時に更新した。

### 構造検証の実装方式（pydantic と jsonschema の役割分担）

- **Context**: 段階計画 Phase 2 は「pydantic でモデル化」と「jsonschema による構造検証」の両方を挙げており、二重実装を避ける役割分担が必要。
- **Sources Consulted**: `docs/incremental-development-plan.md` Phase 2、`docs/structured-json-versioning/operations.md` §11（構造検証の 1 段目）、`pyproject.toml`（「pydantic — 運用スキーマ定義 & JSON Schema 生成」「jsonschema — 構造化 JSON のスキーマ検証」のコメント）
- **Findings**: pyproject の依存コメントが役割を既に規定している。pydantic がスキーマ定義の権威で、JSON Schema はそこから生成する。
- **Implications**: pydantic モデルを単一の権威とし、`model_json_schema()` で生成した JSON Schema を jsonschema で raw ドキュメントに適用（違反レポート収集）→ 合格後に pydantic でパース、の 2 段にする。生成された JSON Schema は llm-feedback-structuring と共有するデータ契約の成果物を兼ねる（requirements の Adjacent expectations「フィールド名・意味を共有語彙として共有」に対応）。

### ライブラリ採用の確認

- **Context**: 採用ライブラリは `docs/library-adoption-proposal.md` に従う制約（brief・roadmap）。
- **Sources Consulted**: `docs/library-adoption-proposal.md`、`pyproject.toml`
- **Findings**:
  - 即採用: `hypothesis`（優先順位チェーンの総順序性質検証。Phase 3 の品質を底上げする費用対効果が最も高い一手と明記）。現状 `pyproject.toml` の dev 依存に未追加。
  - 見送り: ルールエンジン（決定性・監査可能性のため自作＋hypothesis）。
  - `curies`／`rdflib`（Phase 7）、`filelock`／`sqlite3`／`deepdiff`（Phase 4）、`instructor`（Phase 8）、Lance スパイク（Phase 5）はいずれも本スコープ外のフェーズに紐づくため導入しない。
  - 既存依存で本スコープに使うもの: `faiss-cpu`（Flat インデックス）、`numpy`、`pydantic>=2.7`、`jsonschema>=4.21`、`pytest`、`ruff`。
- **Implications**: 依存追加は `hypothesis` と `import-linter`（ともに dev。import-linter は提案書外だが、層依存規約の機械検査というインフラ用途であり判定ロジックには関与しない）。torch／anomalib は本スコープでは使わない（合成埋め込みは numpy で生成）。

### 既存コードベースの調査

- **Context**: 統合先・踏襲パターンの有無の確認。
- **Sources Consulted**: リポジトリ全体の Python ファイル検索（`src/**/*.py` は 0 件）、`pyproject.toml`
- **Findings**: ソースコード・テストとも未実装。`[tool.uv] package = false`（アプリケーション用途）、`[tool.ruff] line-length = 100, target-version = py312`。pytest 設定は未定義。
- **Implications**: `src/` レイアウトの import を通すため `[tool.pytest.ini_options] pythonpath = ["src"]` の追加が必要（Phase 0「pytest の整備」の範囲内）。

## Architecture Pattern Evaluation

| Option                                                      | Description                                                                                                                              | Strengths                                                                                                                               | Risks / Limitations                                                                             | Notes                                            |
| ----------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | ------------------------------------------------ |
| 単一パッケージ内の段階分離（採用）                          | `src/correction_layer/` 1 パッケージ内で「入力境界（検証・ロード）→ 判定ロジック（照合・競合解決・補正）→ オーケストレーション」を層分離 | brief の境界候補（照合／補正／判定の 3 段分離）に一致。各段が独立にテスト可能。Phase 8 で一次判定・ストアを実物に差し替える seam が明確 | パッケージ内規律は import 方向の規約で担保する必要がある                                        | roadmap の他 spec が兄弟パッケージとして並ぶ前提 |
| レイヤードディレクトリ（controllers/services/repositories） | 技術レイヤでディレクトリ分割                                                                                                             | 小規模 CRUD には単純                                                                                                                    | 本機能は CRUD ではなく判定パイプライン。技術レイヤ名がドメインを語らない                        | 不採用                                           |
| ルールエンジン採用                                          | durable-rules 等に競合解決を委譲                                                                                                         | 宣言的記述                                                                                                                              | 決定性・監査可能性がブラックボックス化。`docs/library-adoption-proposal.md` §7 が明示的に見送り | 不採用                                           |

## Design Decisions

### Decision: 類似度尺度は cosine 類似度（FAISS IndexFlatIP＋L2 正規化）

- **Context**: §13 未決。Phase 2 実装のブロッカー。要件 2.5（近傍検索と `similarity_threshold` の同一尺度）。
- **Alternatives Considered**:
  1. 非正規化 L2 距離（`METRIC_L2`）— PatchCore 原典（CNN 特徴）の選択。ノルム情報を保持できるが、本プロジェクトの一次検出が使う DINOv2/v3 パッチ特徴の系譜（上記 Research Log の文献調査）では採用例が少ない。「低いほど近い」のため `similarity_threshold` という名称と大小方向が逆転する。
  2. cosine 類似度（L2 正規化＋`METRIC_INNER_PRODUCT`）— DINOv2 パッチ特徴の deep nearest neighbor の直接の先行研究（AnomalyDINO）および DINOv3 系後続（HiMatch-AD）の選択。「高いほど近い」でフィールド名と整合。
- **Selected Approach**: 全埋め込みを登録時・照会時に L2 正規化し、`faiss.IndexFlatIP` の内積＝cosine 類似度とする。値域 [-1, 1]、**高いほど近い**。`similarity_threshold` の充足は「類似度 ≥ threshold」。一次判定の異常スコアは `1 − 最大類似度`（0 に近いほど正常）とし、固定閾値との比較（`anomaly_score > threshold` で Positive）で導出する。
- **Rationale**: 一次検出（PatchCore on DINOv2）と同型の先行研究群が cosine を採用しており（Research Log の文献調査）、それと尺度を揃えることが要件 2.5 の趣旨に合う。Flat インデックスなので厳密計算。類似度計算を `prototype_store` に一元化することで要件 2.5 を構造的に保証する。L2 正規化済みベクトルでは L2 と cosine は順位同値なので、後段で L2 系実装（anomalib の PatchCore は Euclidean）と接続する場合も「特徴を L2 正規化してから流す」前提を守れば最近傍の選択は一致する。
- **Trade-offs**: 埋め込みのノルム情報を捨てる（ViT 特徴では方向のみが意味を持つという先行研究の経験則に従う）。L2 距離ベースの一次検出（Mahalanobis 等）とはスケールが異なるが、それらは primary-anomaly-detection の所有であり、本スコープの合成一次判定には影響しない。
- **Follow-up**: Phase 8 の実パイプライン統合時に patch-feature-store の実メトリック（および anomalib 実装を使う場合の正規化前提）と突合する（Revalidation Trigger）。

### Decision: `params` は method 判別の専用モデル

- **Context**: §13 未決。method ごとのパラメータ形の確定。
- **Alternatives Considered**:
  1. 自由な `dict[str, float]` — 検証が弱く、不正キーが実行時まで漏れる。
  2. method で判別される専用 pydantic モデル — 構造検証（要件 5.2）で不正を静的に拒否できる。
- **Selected Approach**: `params` は常に JSON オブジェクト。`LabelOverride` と method null（`KeepPrimary`／`ReviewRequired`）は空オブジェクト `{}` を要求、`ScoreReweight` は `{"weight": float}`（weight > 0）、`ThresholdAdapt` は `{"threshold_delta": float}`（有限値）。未知キーは拒否（`extra="forbid"`）。
- **Rationale**: §6.2 の例示（`params.weight`／`params.threshold_delta`）と §8.1 サンプル（`params: {}`）にそのまま対応。
- **Trade-offs**: 将来 method が増える場合はモデル追加が必要だが、enum 自体の拡張と同時なので追加コストは実質ゼロ。
- **Follow-up**: なし。

### Decision: `prototype_ids` の充足は ANY（最大類似度 ≥ threshold）

- **Context**: 要件 2.2 の充足条件の量化が未指定。
- **Alternatives Considered**:
  1. ALL（全プロトタイプが閾値以上）— §9 規則 2 の「一部が残れば残存分で適用」と矛盾する（一部欠落で常に適用不能になる）。
  2. ANY（いずれか 1 つが閾値以上）— リストを選言的アンカー集合として扱う。
- **Selected Approach**: `max(cosine(roi_embedding, p) for p in prototype_ids) >= similarity_threshold` で充足。
- **Rationale**: 設計メモ §9 規則 2 の残存分適用の意味論から直接導出。補正レコードは「既知パターンの代表点集合」であり、どれか 1 つに近ければ当該パターンに該当する。
- **Trade-offs**: なし（ALL 意味論が必要なユースケースは設計メモに存在しない）。
- **Follow-up**: なし。

### Decision: `match.scope` の廃止（適用条件はドメイン軸＋プロトタイプ類似度に限定）

- **Context**: 設計レビュー（2026-07-29）の指摘（上記 Research Log「`match.scope` の要否」）。推論時に入力パッチが持たない値（`defect_class` 等）を適用条件に置くと、当該レコードは永続的に不一致となる。
- **Alternatives Considered**:
  1. scope を維持 — `defect_class` を条件に持つレコードが静かに死ぬ。来歴を適用条件フィールドに混ぜる二重の意味を許す。
  2. scope を「推論時に既知のキー」に限定 — キーごとの可否判定という新たな規約が必要になり、既知のキー（`measurement` 等）はカテゴリ文脈としてドメイン軸で表現できるため、独立機構としての存在理由が残らない。
  3. scope を廃止 — 適用条件を「カテゴリ文脈＝ドメイン軸」「外観＝プロトタイプ類似度」の 2 系統に限定する。
- **Selected Approach**: 廃止を採用。`match` は `prototype_ids`／`similarity_threshold` のみ。`PatchInput` から scope 照合用の属性フィールドを外し、matching はドメイン軸＋類似度の AND 判定に簡素化する。欠陥クラス等の判定来歴は `source_ref` → 独立監査ログが保持する。
- **Rationale**: 推論時に確定する情報だけが適用条件たりうる。判別力の実体は 4 ドメイン軸と埋め込み類似度にあり、scope に置ける値は「照合できないもの（来歴）」か「ドメイン軸に置くべきもの」のどちらかだった。フィールド設計原則（1 フィールド 1 意味・不要フィールドを作らない）にも整合する。
- **Trade-offs**: ドメイン軸に収まらない推論時既知の条件が将来必要になった場合の表現手段を当面持たない。その場合はドメイン軸の追加（design.md Revalidation Triggers「ドメイン軸の変更」）か、optional フィールドとしての scope 再導入（後方互換な追加）で対応する。
- **Follow-up**: 判定スキーマは llm-feedback-structuring と共有する語彙のため、設計メモ §6.3・§9.1・§8.1 サンプルを同時に更新した（Revalidation Trigger「フィールド名・型・enum 値の変更」に該当）。

### Decision: specificity の暫定定義（辞書式: 非 any ドメイン軸数 → 類似度条件の有無）

- **Context**: §9.1 の specificity 判定の厳密化は §13 で未決だが、要件 6.3・7.1 の決定的競合解決には定義が必要。本スコープは `any` ワイルドカードのみ（上位クラス階層なし）。類似度条件の任意化（下記 Decision）により、同一ドメイン軸数でも「プロトタイプ照合で絞られたレコード」と「ドメイン全域に効くレコード」の粒度差が生じる。
- **Alternatives Considered**:
  1. 辞書式比較（第 1 キー: 非 `any` ドメイン軸数 0–4、第 2 キー: `match.scope` の条件キー数）— 当初案。`match.scope` の廃止により第 2 キーが消滅した。
  2. 非 `any` ドメイン軸数（0–4）の単純比較 — ドメイン全域のレコード（類似度条件なし）とプロトタイプ照合つきレコードが同点になり、広域の閾値調整が個別補正を recency で上書きしうる。
  3. 辞書式比較（第 1 キー: 非 `any` ドメイン軸数 0–4、第 2 キー: 類似度条件の有無）— 適用範囲が狭い（＝より具体的な意図の）レコードが常に勝つ。
- **Selected Approach**: 3 を採用。第 1 キーで大きい方、同点なら類似度条件ありが勝つ。なお同点は優先順位チェーンの後続段（ReviewRequired 短絡 → safety → recency → element_id）で決着する。
- **Rationale**: §4.2 の「装置指定 → 材料指定 → 工程全体（`any`）」の合成順はドメイン軸の具体数に基づく順序であり、第 2 キーは「specificity＝適用範囲の狭さ」という同じ原理を `match` 条件へ延長したもの。
- **Trade-offs**: Phase 7 で上位クラス階層（階層距離）が入ると再定義が必要。`decision/resolution.py` に定義を局所化して差し替え可能にする。
- **Follow-up**: Phase 7 着手時に上位クラスマッチを含めて再検証（design.md の Revalidation Triggers に記載）。

### Decision: `match` の類似度条件は対で任意（類似度条件なし＝ドメイン軸のみの広域補正）

- **Context**: 設計レビュー（2026-07-30）で「特定ドメイン（装置・材料）だけ判定閾値を調整する」ような、参照する入力パッチ（プロトタイプ）を持たない補正のユースケースが提起された。従来スキーマは `match.prototype_ids`（min_length=1）と `similarity_threshold` が必須で、この種のレコードを表現できない。
- **Alternatives Considered**:
  1. 類似度条件を必須のまま維持 — `similarity_threshold` を極端に下げて全マッチさせるハックでしか表現できず、意図が読めないレコードになる。
  2. `match` フィールド自体を省略可能にする — 要件 5.1 の 8 フィールド解釈（全フィールドの列挙）と llm-feedback-structuring との共有語彙の形を崩す。
  3. `prototype_ids`／`similarity_threshold` を対で任意にする — `match` は必須のまま、`{}` で「類似度条件なし」を表す。片方だけの指定は構造検証で拒否。
- **Selected Approach**: 3 を採用。matching は「指定された条件のみの AND」（要件 5.4 の文言どおり）で評価し、類似度条件を持たないレコードはドメイン軸のみで適用可否を判定する（要件 2.6）。あわせて specificity を辞書式（非 `any` 軸数 → 類似度条件の有無）に拡張し（上記 Decision）、ドメイン全域のレコードが同ドメインのプロトタイプ照合レコードを recency で上書きしないようにする。さらに soft method の params と action の方向整合（`OverrideNegative` は `weight` < 1／`threshold_delta` > 0、`OverridePositive` は逆）を構造検証で強制する（要件 5.6。広域 `ThresholdAdapt` は params の符号が実効果を決めるため、action との矛盾定義の混入リスクが高い）。
- **Rationale**: 要件 5.4 は元々「指定されたすべての条件を満たす」という AND の意味論であり、条件の欠如＝恒真は自然な拡張。ドメイン軸照合・specificity・優先順位チェーンはプロトタイプと独立に動作するため、判定パイプラインの構造変更を伴わない。
- **Trade-offs**: 類似度条件なしの `OverrideNegative` 方向レコード（閾値引き上げ等）は、当該ドメイン全域の感度を下げる最も影響の大きい形のレコードになる。運用ガードレール（`threshold_delta`／`weight` の許容範囲、広域レコードの承認フローの重さ）は設計メモ §13 の未決事項とした。
- **Follow-up**: 判定スキーマは llm-feedback-structuring と共有する語彙のため、設計メモ §6.2・§6.3・§9.1・§13 を同時に更新した（Revalidation Trigger「フィールド名・型・enum 値の変更」に該当。JSON Schema 成果物の再配布）。

### Decision: action と method の役割分担（soft method はスコア経由で二次判定を導出）

- **Context**: 要件 3.1（OverrideNegative 適用 → Negative）と要件 4.2（ScoreReweight → 再構成後スコアと閾値の比較で導出）は、素朴に読むと OverrideNegative × ScoreReweight で矛盾しうる。
- **Alternatives Considered**:
  1. action を常に優先（soft method でもラベル強制）— method の 3 方式比較（researches.md §5 の検証軸）が無意味になる。
  2. method が計算方式を決め、action は変更方向の意図を表す — 設計メモ §6.2 の「LabelOverride＝ハード、ScoreReweight＝ソフト」の区別と一致。
- **Selected Approach**: method が二次判定の計算方式を決める。`LabelOverride` は action の方向へ無条件で上書き（要件 3.1・3.2 はこの経路で成立）。`ScoreReweight`／`ThresholdAdapt` は params で再構成したスコア／閾値の比較結果を二次判定とする（パラメータ次第でラベルが変わらないことも設計上の正常動作）。
- **Rationale**: §6.1／§6.2 が action（効果の方向）と method（方式）を明示的に別軸として定義しており、ソフト方式の存在意義は「スコア経由の緩やかな補正」にある。
- **Trade-offs**: soft method では action の方向が保証されないが、これは方式比較実験（Phase 8）の観測対象そのものである。
- **Follow-up**: なし（design.md のコンポーネント定義に反映済み）。

### Decision: 不正なドメイン定義はロード時に fail-fast（例外＋全違反理由の報告）

- **Context**: 要件 5.2「当該定義を拒否し、拒否理由を報告する」の拒否粒度（ファイル単位で除外して継続 vs 全体停止）が未指定。
- **Alternatives Considered**:
  1. 不正ファイルのみ除外して継続 — 有効レコード集合が暗黙に変わり、判定結果が静かに変化する（誤補正の混入防止という Requirement 5 の Objective に反する）。
  2. fail-fast（1 ファイルでも不正ならロード全体を例外で停止し、検出した全違反を構造化して報告）— 検証は運用開始前（ロード時）に完結する。
- **Selected Approach**: fail-fast を採用。`DomainValidationError` が違反一覧（ファイル・パス・理由）を保持する。
- **Rationale**: 設計メモ §11 は「検証は publish 前に実施し、合格したものだけを publish」という fail-fast 思想であり、Phase 0–3 の fixture 運用では部分縮退の必要がない。
- **Trade-offs**: 大量ドメイン運用での部分縮退はできないが、それは Phase 4 以降の publish ゲートの責務。
- **Follow-up**: なし。

### Decision: パッケージは `src/correction_layer/` の層サブパッケージ構成、依存方向は import-linter で機械検査

- **Context**: greenfield のためパッケージ構成を新規決定。roadmap の他 spec（feature store 等）が今後兄弟パッケージとして並ぶ。clean architecture の依存方向（`docs/package-dependency-direction.md`）をディレクトリ構造として可視化したい。
- **Alternatives Considered**:
  1. フラットな単一パッケージ＋import 方向の規約（人力レビュー）— 依存規則がドキュメント上の約束に留まり、違反の検出がレビュー品質に依存する。
  2. `api/`／`usecase/`／`entity/` の技術レイヤ名ディレクトリ — Architecture Pattern Evaluation で不採用にした「技術レイヤ名がドメインを語らない」問題を再導入する。
  3. ドメインを語る層名のサブパッケージ＋import-linter — 層をディレクトリで可視化しつつ、依存規則を CI で機械検査できる。
- **Selected Approach**: `src/correction_layer/` 単一パッケージを層サブパッケージで構成する: `model/`（コア型・レコード。最内側）、`boundary/`（検証・ロード・ストアの入力境界）、`decision/`（判定ロジック）、`engine.py`（composition root）。依存方向（`model` ← `boundary`／`decision` ← `engine`、`boundary` と `decision` は相互不干渉、`decision` 内は互いに独立）は `import-linter` の layers／independence 契約として `pyproject.toml` に定義し、`lint-imports` を CI で実行する。pytest は `pythonpath = ["src"]` で解決。dev 依存に `hypothesis>=6` と `import-linter>=2` を追加。
- **Rationale**: 段階計画 Phase 0 の「`src/` パッケージ構成、pytest、ruff の整備」に対応。層名は design.md の層呼称（モデル・入力境界・判定ロジック）と `docs/package-dependency-direction.md` の用語（schema／decision）に揃え、汎用技術レイヤ名を避ける。依存規則の担保を人力レビューから機械検査に格上げする。
- **Trade-offs**: 階層が 1 段深くなるが、Phase 4 以降で versioning／ontology を外側パッケージとして追加する際の置き場が明確になる。
- **Follow-up**: 後続 spec が `src/` に参加する際は同じ命名規約（役割ベースの snake_case）に従う。versioning／ontology 追加時は import-linter 契約に外側の層を追記する。

### Decision: Phase 0–3 のドメイン定義 JSON はバージョン管理メタを持たない簡易スキーマ

- **Context**: §8.1 の正式アーティファクトは、トップレベルの versioning メタ（`domain_id`／`domain_version`／`built_against_bank_snapshot_id` 等。Phase 4–6 の責務）と、要素単位の `ontology_version`（§6.3。Phase 7 の責務）を含む。
- **Selected Approach**: ドメイン軸 4 つ（`process`／`material`／`equipment`／`unit_of_work`、`any` 可）を持つ `domain` オブジェクトと `elements[]`（8 フィールドのレコード）のみの簡易スキーマを本 spec のフィクスチャ契約として所有する。
- **Rationale**: Phase 1–3 は永続化を持たないため（段階計画の基本方針）、正式アーティファクトのスキーマを先取りすると Phase 4 で二重定義・手戻りになる。要件 5.1 の列挙フィールド（8 個）とも一致する。
- **Trade-offs**: Phase 4 でトップレベルメタの追加が必要だが、`elements[]` のレコード形は §6.3 のうち要素単位 `ontology_version` を除いた 8 フィールドの部分集合なので前方互換（`ontology_version` は Phase 7 で追加）。
- **Follow-up**: Phase 4 着手時にトップレベルスキーマを正式アーティファクト形へ拡張。

## Risks & Mitigations

- specificity の暫定定義が Phase 7（上位クラス階層）で変わる — 定義を `decision/resolution.py` の単一関数に局所化し、hypothesis の総順序性質テストを差し替え時の回帰ゲートにする。
- 浮動小数点比較の境界（`anomaly_score > threshold`・`similarity >= similarity_threshold`）の不一致 — 比較の向き・等号の有無をデータモデル定義に明文化し、境界値テストを必須にする。
- `recorded_at` 同時刻の衝突 — チェーン最終段の `element_id` タイブレークで総順序が保証される（§9.1 rule5）。hypothesis で同時刻ケースを生成して検証する。
- 合成一次判定（kNN＋固定閾値）が実物（primary-anomaly-detection）と乖離する — 一次判定を `decision/primary.py` に隔離し、Phase 8 で差し替える seam を design.md の境界コミットメントに明記。

## References

- `docs/structured-json-versioning/correction-layer.md` — 判定スキーマ（§6）・解決規則と優先順位チェーン（§9）の権威
- `docs/structured-json-versioning/versioning-model.md` — 削除の表現（§3.1）・ドメイン合成順（§4.2）
- `docs/structured-json-versioning/file-layout-and-samples.md` — レコード JSON サンプル（§8.1）
- `docs/structured-json-versioning/operations.md` — 検証 2 段構え（§11）・未決事項（§13）
- `docs/incremental-development-plan.md` — Phase 0–3 の段階計画（本スコープの定義元）
- `docs/library-adoption-proposal.md` — hypothesis 採用・ルールエンジン見送りの根拠
- `docs/researches.md` — §3.1（重み固定）・§3.2-5/6（補正レイヤ・最終判定）・§5（3 方式比較の検証軸）
- `docs/2025-2026_survey.md` — 異常検知研究動向（DINOv2/v3・training-free・retrieval）
- 距離尺度の原典: PatchCore（[arXiv:2106.08265](https://arxiv.org/abs/2106.08265)、公式実装 faiss `IndexFlatL2`）、MuSc（[arXiv:2401.16753](https://arxiv.org/abs/2401.16753)、L2）、AnomalyDINO（[arXiv:2405.14529](https://arxiv.org/abs/2405.14529)、cosine 距離を式 3 で明示）、Dinomaly（[arXiv:2405.14325](https://arxiv.org/abs/2405.14325)、cosine）、HiMatch-AD（[arXiv:2606.22556](https://arxiv.org/abs/2606.22556)、cosine）、AnomalyVFM（[arXiv:2601.20524](https://arxiv.org/abs/2601.20524)、特徴比較に cosine）
- `.kiro/steering/roadmap.md` — spec 分割と shared seams
