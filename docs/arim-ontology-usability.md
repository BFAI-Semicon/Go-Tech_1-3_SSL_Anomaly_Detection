# ARIM メタデータ語彙の本開発での利用可能性調査

[NIMS-ARIM](https://www.nims.go.jp/arim/)（マテリアル先端リサーチインフラ）は実験データ共用を
目的とした国のデータ基盤で、半導体を含む実験データの登録時に実験メタデータを付与する。
そのメタデータ体系を、[設計メモ §5](./structured-json-versioning/ontology.md) の統制語彙
（Process / Materials / Equipment / Measurements / Units-of-work の CURIE 参照）として
利用できるかの調査結果（2026-07-28 調査）。
SemiKong 側の網羅性調査は [semikong-ontology-coverage.md](./semikong-ontology-coverage.md) を参照。

**結論：SemiKong の代替にはならないが、補完源として利用価値がある。**
権威語彙として CURIE 参照するのではなく、`proj:` 拡張語彙を設計する際のソース
（工程ファミリーのチェックリスト・日英ラベル辞書・マッピング先）としての利用を推奨する。

## ARIM のメタデータ体系は 3 層

調査の結果、ARIM の「オントロジー」に相当するものは単一ではなく、3 層に分かれている。

### 1. RDE 登録スキーマ（JSON Schema、オントロジーではない）

データ構造化システム [RDE](https://nanonet.go.jp/data_service/page/data_structured.html) への
登録は、装置ごとの `invoice.schema.json`（送り状＝手入力実験情報）と `metadata-def.json`
（装置出力から抽出する「選定メタデータ」）で定義される
（[データセットフォルダー構成](https://nanonet.go.jp/data_service/page/dataset_folder.html)、
[RDEToolKit のスキーマ仕様](https://nims-mdpf.github.io/rdetoolkit/usage/metadata_definition_file/)）。
JSON Schema（2020-12）ベースで日英ラベル・型・単位・参照情報を持つが、
**IRI で識別される概念体系ではない**。本開発の CURIE 参照の権威にはならない。

### 2. カタログ分類タグ（フラットなファセット）

[ARIM データポータル](https://nanonet.go.jp/data_service/)の検索軸は
**設備分類**（リソグラフィ／膜加工・エッチング／成膜装置／熱処理・ドーピング／
表面処理・洗浄／組立・パッケージング／微小加工装置 など約 27 分類）、
**重要技術領域**（7 領域）、横断技術領域、マテリアルインデックス。
[データカタログ作成要綱](https://arim.ims.ac.jp/wp-content/uploads/20241001_DATA_Catalog.pdf)
でタグ付与が要件化されている。工程系の語彙を含むが、UI 用のフラットなタグであり
単体では階層マッチ（§4.2）に使えない。

### 3. MatVoc（NIMS 材料語彙、機械可読・階層あり）

[MatVoc](https://matvoc.wikibase.cloud/)（旧 [matvoc.nims.go.jp](https://matvoc.nims.go.jp/wiki/MatVoc:About)、
Wikibase 実装）が NIMS 材料データプラットフォームの共通語彙で、RDE 等の各システムが
参照する（[NIMS 発表資料](https://doi.org/10.48505/nims.3863)）。SPARQL で確認した実態：

- 各概念に QID（例 `Q2057`）と IRI（`https://matvoc.wikibase.cloud/entity/Q2057`）、
  日英ラベル＋別名（`skos:altLabel`）が付与され、RDF / SPARQL で機械可読。
- **「先端 RI(ARIM) 装置辞書」（Q1882、172 項目）として上記の設備分類とその下位語彙を収録**。
  例: `Q2057`「ドライエッチング（RIE）」は broader プロパティ（P8）で
  `Q1918`「膜加工・エッチング」に接続する 2 階層構造。ECR-RIE、ウェット/ガスエッチング、
  EB リソグラフィ、ナノインプリント、ALD／CVD／PVD 装置等の粒度まである。
- 材料種・分析手法（XPS・XRD・TEM 等）の辞書も持つ。

## 設計メモ §5 の 5 パースペクティブとの照合

| パースペクティブ | ARIM/MatVoc の充足度 |
| ---------------- | -------------------- |
| Process | △ 実体は「装置分類」だがラベルは工程名的。洗浄・熱処理・ドーピング・組立など SemiKong の工程軸に無い家系を持つ。ただし 2 階層・RIE 止まり（DRIE 無し）で浅く、CMP は明示分類が見当たらない |
| Materials | △ 材料語彙はあるが半導体特化ではない |
| Equipment | ○ ARIM 装置辞書 172 項目が最も充実 |
| Measurements | △ 分析・計測「手法／装置」は厚いが、`match.scope.measurement` が想定する計測量（CD 等）の語彙ではない |
| 欠陥クラス | × 無し（`proj:` 拡張のままでよい） |

## 権威語彙として採用しにくい理由

1. **CURIE の可読性**：MatVoc の識別子は不透明な QID（`matvoc:Q2057`）で、設計メモが想定する
   人間可読 CURIE（`semicont:DeepReactiveIonEtchProcess`）と思想が異なる。補正レコードの
   監査・レビューの可読性が落ちる。
2. **版ピン留め不可**：Wikibase は生きた wiki で、SemiKong の git タグに相当する
   「語彙集合全体の不変スナップショット」機構が無い。採用するなら自社でダンプを取得して
   snapshot 化し、レジストリ（§5.2）の `components` に自社管理 ref として載せる必要がある。
3. **IRI 安定性の実績**：`matvoc.nims.go.jp` から `matvoc.wikibase.cloud` への移行が実際に
   発生しており、エンティティ IRI のドメインが変わった。remap 表（§5.2）で吸収可能な種類の
   変更だが、外部依存としてのリスク要因。
4. **階層の表現**：broader が `rdfs:subClassOf` ではなく Wikibase 固有プロパティ（P8）のため、
   §4.2 の推移閉包計算は可能（rdflib で扱える）だが SemiKong と同じコードにはならない。
5. **ライセンス**：ARIM スキーマ・MatVoc 語彙の明示ライセンスが確認できなかった（要法務確認。
   SemiKong と同様の論点）。

## 推奨する利用方法

1. **`proj:` 工程語彙の設計ソースとして利用**：SemiKong の工程軸に欠けている
   洗浄・熱処理・ドーピング・組立等（[semikong-ontology-coverage.md](./semikong-ontology-coverage.md)
   の欠落リスト）を `proj:` で補う際、ARIM 装置辞書 172 項目をチェックリスト・命名の参照元にする。
   国内共用施設の実務で使われている分類なので、現場オペレータの語彙と揃いやすい。
2. **日英ラベル・別名辞書として LLM 構造化に利用**：`llm-feedback-structuring` が自然言語
   コメントから CURIE を引く際の表記ゆれ吸収（「RIE」「ドライエッチング」→ 同一概念）に、
   MatVoc の ja/en ラベル＋ `skos:altLabel` が転用できる。SPARQL 一発で対訳・別名表を抽出可能。
3. **マッピング表の保持**：`proj:` 語彙に `skos:exactMatch` 相当で MatVoc QID への対応を
   持たせておくと、将来 ARIM（RDE）へ実験データを登録・共用する場合のメタデータ相互運用が
   低コストになる。逆に、その計画が無いなら直接依存は増やさないのが妥当。

直接 CURIE 参照する場合は第 3 の prefix（`matvoc:`）追加となり、§5.3 の
「`semicont` と `proj` の 2 つ」という前提の改訂が必要になる。上記 1〜3 の間接利用であれば
設計メモの変更は不要。
