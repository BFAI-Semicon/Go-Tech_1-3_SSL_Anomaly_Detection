# ライブラリ採用提案

[構造化 JSON バージョン管理・補正レイヤ設計メモ](./structured-json-versioning/README.md) の実装で、
精度・品質・開発コストを改善できるライブラリの調査結果（2026-07 調査）。
**「補正レイヤの判定ロジック」以外はほぼ全て、実績あるライブラリで自作コードを大幅に減らせる**。
段階的開発計画は [incremental-development-plan.md](./incremental-development-plan.md) を参照
（本文中の Phase 番号は同計画のフェーズを指す）。

## 採用優先度まとめ

1. **即採用（低コスト・確実に効く）**: `hypothesis`、`curies` + `rdflib`、`instructor`、`filelock`、
   stdlib `sqlite3`、`deepdiff`
2. **スパイクの価値あり（当たれば自作コードを大幅削減）**: Lance / LanceDB によるメモリバンク版管理の置き換え
3. **見送り**: DVC / lakeFS、ルールエンジン、OWL 推論

## 1. オントロジー処理（§5）— 自作すると一番バグりやすい領域

| ライブラリ                | 置き換え対象                                                                                                |
| ------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `curies`（biopragmatics） | CURIE⇔IRI の展開・圧縮、prefix map 管理、**CURIE prefix remapping**                                         |
| `rdflib`                  | SemiKong TTL のロード、IRI 実在検証（§11 の 2 段目）、`rdfs:subClassOf` 推移閉包（§4.2 の上位クラスマッチ） |
| `pySHACL`（任意）         | SHACL shapes による統制語彙検証（§11 が言及する流用先そのもの）                                             |

- `curies` は trie ベースの高速 prefix 照合に加え、CURIE prefix remapping / rewiring のユーティリティを
  標準装備しており、§5.2 の remap 表適用の実装がほぼそのまま載る。
- `rdflib` の `transitive_objects()` で subClassOf 閉包が数行で取れるため、§13 未決の
  「閉包焼き込み vs 稼働時 TTL ロード」はどちらの案もほぼ同コストになり、意思決定が軽くなる。
- CURIE パースの端ケース（コロン含む LocalName、重複 prefix）を自作すると事故りやすいため採用を強く推奨。

## 2. テスト品質 — `hypothesis`（property-based testing）

- §9.1 の優先順位チェーンは「**総順序である**」（反対称・推移律・全域性）という数学的性質が要件そのもの。
  ランダム生成したレコード集合に対し「任意の 2 要素で勝敗が一意」「順序の推移律が成立」「同一入力なら決定的」
  を検証すると、タイブレークの抜け（recency 同時刻、specificity 同点の見落とし等）を機械的に炙り出せる。
- バージョン管理側でも「publish → ロールバック → 再現で状態が一致する」ラウンドトリップ性質のテストに使える。
- Phase 3〜4 の品質を底上げする、費用対効果が最も高い一手。

## 3. メモリバンクの版管理 — Lance / LanceDB（スパイク検証を推奨）

設計では `banks/<snapshot_id>/`（FAISS インデックス＋メタデータ層＋系譜メタ）を自作する計画だが、
**Lance 形式はこの塊をネイティブ機能で持つ**：

- **zero-copy バージョニング＋タグ＋ブランチ**（各版が差分のみ保持。タグ＝不変ポインタは §7.1 の
  snapshot_id に、ブランチは §2 の「単一親の系譜・ロールバック後の分岐」にそのまま対応）。
- ベクトル検索（IVF_PQ 等）＋**スカラーフィルタ（`domain_id` 等のメタデータ）を同一データセットで**実行でき、
  FAISS＋自作メタデータ層の 2 層構成（§2.1）を 1 層にできる。
- 保持世代の cleanup／compaction が組込み（§13 未決の GC 方針に相当）。

トレードオフ（機能不足ではなく、設計メモの前提書き換え＋精度確認が採用コスト）：

- `prototype_id`：設計は「FAISS の int64 ID そのもの」（§2.1）だが、Lance ではインデックスのネイティブ ID
  ではなく**アプリ管理の通常カラム**として持つことになる（Lance 内部の row id は compaction で振り直される
  ため ID に使えない）。機能上は問題なく、非再利用の保証が書き込み側ロジックにあるのは FAISS でも同じだが、
  §2.1 の文言の書き換えが要る。
- スナップショット管理：`banks/<snapshot_id>/`＋系譜メタ（§8.3）を自作せず Lance の版・タグ・ブランチに
  委譲するため、§8.3 の記述と食い違う（採用時は設計側を改訂）。
- 精度：FAISS Flat は厳密 kNN、Lance の IVF_PQ 等は近似検索。`match.similarity_threshold` の適用判定が
  近傍距離に依存するため、再現率低下による補正の取りこぼしがないか確認が必要（厳密検索も可能だが速度と
  トレードオフ）。

**Phase 5（bank 版管理）に入る前に 1〜2 日のスパイクで「系譜・ロールバック・メタフィルタが要件を満たすか」を
検証し、満たせば自作の snapshot 管理コード一式を削除できる**、という位置づけ。

## 4. LLM 構造化（llm-feedback-structuring）— `instructor`

- vLLM の OpenAI 互換エンドポイント＋`guided_json` は計画済みだが、`instructor` を挟むと
  **pydantic モデル → 構造化出力 → 検証失敗時の自動リトライ（エラー内容をプロンプトに還流）** のループが数行になる。
- [plan.md](./plan.md) のリスク「LLM JSON 化の逸脱」への対策（スキーマ検証＋失敗時監査ログ）の実装コストを
  直接下げる。既存依存（pydantic 2、openai）とも整合。

## 5. 一次判定・coreset — anomalib の内部実装を流用

- 依存済みの anomalib には PatchCore の **k-center greedy coreset サンプリング**・異常スコア計算・
  AUROC/AUPRO 等の評価メトリクスが実装済み。
- `patch-feature-store` の coreset 再選択（brief の In スコープ）と `evaluation-framework` の指標計算は、
  自作せず anomalib / torchmetrics / scikit-learn から呼ぶ構成にすると、精度面の検証済み実装をそのまま得られる。

## 6. 小粒だが効く stdlib＋軽量ライブラリ

- **原子的ポインタ差し替え（§7.1）**: `os.replace()`（stdlib、POSIX で原子的）＋ `filelock` で単一ライタを強制。
  自作ロックは書かない。
- **`element_id` 単調カウンタ（§6.3）**: stdlib `sqlite3` の 1 テーブル。ACID・クラッシュ耐性が無料で付き、
  §13 未決の「原子的インクリメント・クラッシュ耐性」が即決できる。監査ログ（append-only）も同じ SQLite に
  置けば backstop 再構築も SQL 1 本。
- **publish 前 identity 不変 assert（§11）**: `deepdiff` で前版との構造比較
  （不変対象フィールドの diff が空であること）。

## 7. 見送りを推奨するもの

- **DVC / lakeFS**（アーティファクト版管理）: 汎用のファイル版管理としては強力だが、本設計のマニフェストは
  「タプル意味論・部分ロールバック時の新マニフェスト発行」というドメイン固有ロジックが本体で、そこは結局自作になる。
  JSON ファイル＋ポインタの自作は十分小さいので、導入コストに見合わない
  （リモート同期が必要になった時点で DVC を「置き場」として再検討で十分）。
- **ルールエンジン**（durable-rules 等）: §9.1 のチェーンは決定性・監査可能性が命で、宣言的エンジンに委ねると
  かえってブラックボックス化する。ここは自作＋hypothesis が正解。
- **owlready2 の推論機能**: subClassOf 閉包だけなら rdflib で足り、OWL リーズナーは過剰。
