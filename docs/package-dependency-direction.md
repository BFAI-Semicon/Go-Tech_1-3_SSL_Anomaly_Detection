# パッケージ依存方向の設計（clean architecture 適用）

[段階的開発計画](./incremental-development-plan.md) の 3 つの塊
（補正レイヤ本体・バージョン管理・オントロジー）を `src/` 内で独立パッケージにする際の
依存方向の検討メモ。clean architecture の原則（依存は常に内側＝ポリシーへ向かう）を
本開発に当てはめると、**内側に来るのは「補正レイヤの判定ロジックとそのスキーマ」であり、
バージョン管理とオントロジーは外側**になる。開発計画のフェーズ順そのものが、
この依存方向の根拠になっている。

## 何が内側かの判定基準

内側に置くべきなのは「このシステム固有の、置き換えの利かないビジネスルール」である。

- **判定スキーマ（レコードモデル）と優先順位チェーン**が、
  [ライブラリ採用提案](./library-adoption-proposal.md) でも
  「補正レイヤの判定ロジック以外はほぼ全て自作を減らせる」と言われている通り、
  唯一の自作価値がある中核。
- **バージョン管理**は「どのレコード集合を有効にするか」を解決する仕組みで、
  ファイルレイアウト・マニフェスト・`os.replace()`・sqlite といった実装詳細の塊。
  典型的なインフラ層。
- **オントロジー**は外部システム（SemiKong TTL）とのアダプタで、
  `rdflib`/`curies` に依存する外部連携層。

## 具体的な依存方向

```text
        app（worker のビルド・推論エントリポイント）
         │ 依存
         ▼
  versioning     ontology        ← 外側。互いに依存しない
         │            │
         ▼            ▼
      decision（優先順位チェーン・照合）
         │
         ▼
      schema（レコード pydantic モデル）   ← 最内側
```

- **schema**（`element_id`・`action`・`match` 等の pydantic モデル）が最内側。
  全員がここに依存し、ここは誰にも依存しない。
- **decision**（一次→二次変換、競合解決チェーン）は schema のみに依存。
- **versioning** は schema に依存（publish 前検証、identity 不変 assert の対象が
  レコードだから）。decision には依存しない。
- **ontology** は schema に依存し、後述の通り decision が定義するインターフェースを実装する。
- **app**（合成ルート）だけが全部を知り、配線する。

## 依存性逆転が必要な 2 箇所

計画のフェーズ構成が、逆転すべき境界を正確に示している。

### 1. ドメイン軸照合（decision ← ontology）

Phase 2–3 ではドメイン軸を「文字列の完全一致＋`any` ワイルドカード」で照合し、Phase 7 で
「上位クラス CURIE 階層マッチ」（§4.2／§9.1）に拡張する（旧 `match.scope` は廃止済みで、
照合対象はドメイン軸のみ）。つまり decision 側は `AxisMatcher` の
ようなプロトコル（抽象）を定義し、

- Phase 2–3: 完全一致＋ `any` ワイルドカードの実装（decision 内蔵でよい）
- Phase 7: `rdfs:subClassOf` 閉包を使う実装（ontology パッケージが提供）

を差し替える形にする。decision が `rdflib` を import することは最後までない。
「CURIE は不透明文字列扱い」という Phase 2 の記述は、まさに decision から見た
CURIE の姿である。

### 2. レコードの入手（decision ← versioning）

Phase 1 は「固定パス 1 ファイルのロード」、Phase 4 以降はマニフェスト経由の解決になる。
decision は「ロード済みのレコード集合（と kNN スコア）を受け取って判定を返す」
純粋関数的な形にし、どこから来たか（固定パスか、active-manifest 解決か）は知らない。
ロード手段の進化（Phase 1→4→6）が判定ロジックに一切触れずに済む。

## versioning と ontology の関係

Phase 7 の「目標版への正規化ビルド」ではオントロジー版への正規化が publish
パイプラインに入るため、一見 versioning → ontology の依存が要りそうに見える。
しかしこれは**ビルドのオーケストレーション（app 層）が両方を順に呼ぶ**構成にすべき
である。versioning は「不変アーティファクトの publish とポインタ差し替え」だけに
責務を絞り、正規化や IRI 実在検証は publish 前のステップとして app 層の
ビルドスクリプトが挟む。こうすると「バージョン管理とオントロジーを直交分離する」
という計画の方針がコード上でも保たれ、Phase 4（versioning だけ）→
Phase 7（ontology 追加）の順に、既存パッケージを改変せず積み上げられる。

## この方向が正しいことの検証方法

各フェーズの成立条件がそのままテストになる。Phase 3 完了時点で decision は
versioning・ontology のどちらも import せずに全テストが通るはず
（実際、計画では両者はまだ存在しない）。逆に言うと、Phase 4 以降で decision に
`manifest` や `curies` への参照を足したくなったら、それは依存方向違反のシグナルである。
