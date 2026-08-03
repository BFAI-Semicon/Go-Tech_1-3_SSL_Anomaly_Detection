# 段階的開発計画

[構造化 JSON バージョン管理・補正レイヤ設計メモ](./structured-json-versioning/README.md) の実装に向けた、
最小限動くものから徐々に機能を追加する開発計画。
各フェーズで使うライブラリは [library-adoption-proposal.md](./library-adoption-proposal.md) の採用提案に従う
（選定理由・トレードオフは同ドキュメントを参照）。

## 基本方針

- 各フェーズは「動く状態＋pytest での確認」で完結させ、次フェーズはその上に積む。
- 実データ・実 LLM・実 SemiKong に依存する部分は最後まで遅延し、**合成データ（fixture）で先に骨格を検証**する。
- 設計メモの §13（未決事項）は、それが**ブロックするフェーズに入って初めて確定**する（前倒しで悩まない）。
- 複雑さの塊を「補正レイヤ本体（Phase 1–3）」「バージョン管理（Phase 4–6）」「オントロジー（Phase 7）」の
  3 つに直交分離し、1 度に 1 つだけ導入する。
- Phase 1–3 は永続化を持たないため、スキーマの手戻りがあってもファイル形式のマイグレーションが発生しない。
  設計変更のコストが一番安い時期に判定ロジックを固める。

## フェーズ計画

各フェーズの粒度は 1〜2 週間程度を想定。

### Phase 0: 骨格と合成データ

- `src/` パッケージ構成、pytest、ruff の整備。
- 合成 fixture：ランダム埋め込み数百件の FAISS Flat インデックス（＝ミニメモリバンク）、手書きのドメイン JSON 1 個。
- **確認**: fixture のロードと kNN 検索が通る。

### Phase 1: 最小 E2E スライス（バージョン管理なし）

補正レイヤの心臓部だけを最短で動かす。

- 固定パス 1 ファイルのドメイン JSON をロード → 一次判定（kNN スコア＋固定閾値）→
  補正 1 レコード適用（`OverrideNegative` × `LabelOverride` のみ）→ 最終判定（NG／許容）を返す。
- `match` は `prototype_ids` ＋ `similarity_threshold` のみ。specificity・競合解決・
  マニフェスト・オントロジーは**すべて無し**。
- **確認**: 「一次で Positive のパッチが、登録済みプロトタイプに近ければ許容に反転する」テストが通る。
  補正レイヤの価値（過検出抑制）が最初に目に見える。

### Phase 2: スキーマ完成と検証（§6・§11 の 1 段目）

- pydantic でレコード全フィールド（`element_id` / `action` / `method` / `params` / `match` /
  `recorded_at` / `attributed_to` / `source_ref`）をモデル化し、4 action × 3 method＋`null` を実装。
- jsonschema による構造検証（§11 の 1 段目のみ。CURIE 実在検証は Phase 7 へ）。
- ドメイン軸の CURIE は**不透明文字列扱い**（文字列の完全一致だけで照合）。
- §13 の「`params` の持ち方」「`similarity_threshold` の距離尺度」をここで確定する（実装がブロックされるため）。
- **確認**: 4 action それぞれの一次→二次変換、不正 JSON の reject。

### Phase 3: 競合解決チェーンと複数ドメイン（§9.1・§4.2）

- 複数ドメイン JSON のロードと合成インメモリ索引（`any` ワイルドカードのみ。上位クラス CURIE 階層は Phase 7 へ）。
- 優先順位チェーン実装：specificity → `ReviewRequired` 短絡 → safety → recency → `element_id`。
- `KeepPrimary` の能動マスク（広域遮蔽）と削除（フォールバック）の挙動差をテストで固定。
- **確認**: チェーン各段のタイブレークを網羅するテーブル駆動テスト。設計上一番壊れやすい部分なので厚めに。
  加えて `hypothesis` の property-based testing で総順序の性質（勝敗の一意性・推移律・決定性）を検証する。

### Phase 4: 版付きアーティファクトとマニフェスト（§3・§7）

ここで初めて「バージョン管理」を導入する。

- `versions/` レイアウト（`domains/<domain_id>/<domain_version>.json`、`manifests/`、`active-manifest.json`）。
- 単一ライタのビルドスクリプト：ドメイン JSON 全生成 → publish 前検証 → 不変アーティファクト publish →
  新マニフェスト発行 → ポインタ差し替え。ポインタ差し替えは `os.replace()`、単一ライタの強制は `filelock`。
- `element_id` 単調カウンタは stdlib `sqlite3` の 1 テーブル（原子的インクリメント・クラッシュ耐性。
  §13 の永続化仕様はここで最小決定）。
- publish 前の identity 不変 assert（§11）は `deepdiff` で前版と構造比較する。
- **タプル全体ロールバック**（ポインタ差し替えのみ）。部分ロールバックはまだ。
- **確認**: publish → 昇格 → ロールバック → 再現、の一連が冪等に通る。publish 後ファイルの不変性 assert。
  ラウンドトリップ性質（ロールバック→再現で状態一致）は `hypothesis` でも検証する。

### Phase 5: メモリバンク版と互換ゲート（§2.1・§8.3）

着手前に Lance / LanceDB のスパイク（1〜2 日）を実施し、bank 版管理を Lance の版・タグ・ブランチ機能に
委譲できるか判断する（検証項目・トレードオフは
[library-adoption-proposal.md §3](./library-adoption-proposal.md)）。委譲できれば以下の自作範囲が縮小する。

- bank スナップショットメタ（`snapshot_id` / `parent_bank_snapshot_id`）と系譜。
- ドメイン版への `built_against_bank_snapshot_id` 刻印、publish 時の**祖先到達判定**。
- dangling `prototype_ids` の skip／remap（§9 規則 2）。
- **確認**: 別枝 bank で publish が拒否される／間引かれたプロトタイプ参照が silent skip になるテスト。

### Phase 6: 部分ロールバックと priority.json（§7.1・§9.1）

- ドメイン単位ロールバック（現他軸＋旧ドメイン版で新マニフェスト発行）。
- 任意の `priority.json`（全体 1 ファイル、dangling `element_id` 無視）。
- **確認**: 部分ロールバック後もチェーン・priority が壊れないこと。

### Phase 7: オントロジー統合（§5）

最も外部依存が強いので後ろに置く。

- `ontology_registry.json`（版キー・prefixes・remap）、要素の `ontology_version`、
  `domain_source_ontology_version`。
- 目標版への正規化ビルド、`domain_representations_by_ontology_version`。
- CURIE⇔IRI 変換・prefix map・remap 適用は `curies`、SemiKong TTL のロード・IRI 実在検証
  （§11 の 2 段目）・`rdfs:subClassOf` 推移閉包は `rdflib` を使う（必要なら `pySHACL` で shapes 検証）。
- 上位クラス階層マッチ（§4.2 の方式 2）。§13 の「subClassOf 焼き込み vs 稼働時 TTL ロード」
  「specificity 厳密化」をここで確定。
- **確認**: remap を挟んだ再ビルドで判定が不変（改名のみのケース）。

### Phase 8: 実パイプライン統合・評価

- 実物の `patch-feature-store` / `primary-anomaly-detection` / `llm-feedback-structuring` との接続、
  `evaluation-framework` での escape/overkill 回帰ゲート。
- LLM 構造化は `instructor`（pydantic モデル＋検証失敗時の自動リトライ）、coreset 選択・評価メトリクスは
  anomalib / torchmetrics / scikit-learn の実装を流用する。
- brief の比較軸（3 補正方式切替、ROI のみ／言語のみ／併用）の実験対応。

### マイルストーンとの整合

Phase 0–3 は合成データだけで進むので、[milestones.md](./milestones.md) の
「SSL特徴＋ストア基盤」「一次検出＋抽出器比較」を**待たずに前倒し着手可能**。
「HITL＋補正レイヤ」マイルストーンに Phase 8 が収まる。
