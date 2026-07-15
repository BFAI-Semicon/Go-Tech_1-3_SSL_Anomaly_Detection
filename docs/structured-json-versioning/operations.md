# 稼働系ロード・検証・環境依存・未決事項（§10–§13）

> 親: [設計メモ索引](./README.md)。章番号は全体で連続（`§x.y` 参照は同ディレクトリの対応ファイル。§2–§4→[versioning-model.md](./versioning-model.md)、§5→[ontology.md](./ontology.md)、§6/§9→[correction-layer.md](./correction-layer.md)、§7/§8→[file-layout-and-samples.md](./file-layout-and-samples.md)）。

## 10. 稼働系のロードと検索

- 稼働系は起動時に有効スナップショットをロードし、**ドメイン（工程・材料・装置）をキーにした
  インメモリ索引**を構築する（線形スキャン禁止）。
- これにより、マッチ計算はファイル全体サイズではなく「該当ドメインの有効ルール数」に比例し、
  ファイルが大きくなっても検索性能が劣化しない。
- ログ（source of truth）と有効スナップショット（稼働系がロード）の 2 層構成でファイル肥大に対処する。
- バージョン昇格の反映はリロード（または Blue-Green で新インスタンスにロードして原子的に切替）。

## 11. 検証（2 段構え）

1. **構造検証**（`jsonschema`）：フィールド有無・型・enum（`action` / `method`）。
2. **統制語彙検証**：`domain.process` 等の CURIE が SemiKong オントロジーに実在するクラスかを照合
   （TTL をロードして IRI 集合で検証、または SHACL shapes を流用）。
   → 「オントロジーに無い工程名は登録できない」ガードとなり、`patch-feature-store` の
   「検証済みのみ登録」ガードと整合する。

- 検証は**追記前**に実施し、**合格したレコードだけを `log.jsonl` に追記**する（検証済みは構造上の
  不変条件になるため、per-record の `schema_validated` フラグは持たない）。
- **検証失敗は独立監査ログに記録**する（`llm-feedback-structuring` の監査ログ責務）。レコード本体には
  来歴詳細を持たず、`source_ref` で監査ログを辿る。

## 12. 環境・依存の前提（参考）

- Python 3.12 固定。torch は cu130 index（x86-64 / aarch64 いずれも cp312 wheel 提供）。
- anomalib は DINOv3 対応 PR がマージされるまで PR 作者 fork の `feature/dinov3` を暫定使用
  （`pyproject.toml` `[tool.uv.sources].anomalib`）。
- FAISS は aarch64 のため `faiss-cpu`。
- torch/anomalib を環境間で同一バージョンに揃え、デバイス非依存に実装すればソースは共通。

## 13. 未決事項

- `params` の持ち方（`method` 別のパラメータ。§6.2 の `weight` / `threshold_delta` 等）の確定。
- 採用する SemiKong レイヤ／クラスの確定 IRI 取り込み、およびライセンス法務確認。
- §9.1 の specificity 判定の厳密化（`match.scope` の部分一致・多軸指定時の具体度スコアの定義）。
- §4.2／§9.1 の上位クラスマッチング方式：有効スナップショットの `ontology_version` に対応する
  `rdfs:subClassOf` 推移閉包をスナップショット生成時に焼き込むか、稼働系がピン留めされた TTL をロードして
  解決するか。多重継承時の specificity（階層距離）と推論範囲も併せて確定する。
- §9.1 recency の厳密な全順序が必要なら、単一ライタが全ドメイン横断の global event id を採番する案
  （`recorded_at` の時計スキュー・同時刻衝突への対策）。
- オントロジーレジストリ（§5.2）のスキーマ確定：`remap_from` の連鎖解決（`1.2.0→1.3.0→1.4.0`）や
  クラス削除・分割（1 対多 remap）の表現。`proj` 版の採番規則（日付／semver）の確定。
- 「同一 IRI の意味変更」を検知する手段（ontology diff・SHACL 差分・回帰評価の運用）。
- `ontology_version` の remap 連鎖関数の実装方針（`schema_version` は破壊的変更を行う時点で導入）。
- メモリバンク版とドメイン版の**粒度非対称**の運用ルール（§2・§4）：`memory_bank` snapshot のロールバックは
  全ドメインに波及するグローバル操作、per-domain JSON ロールバックは局所操作。両者を混在させたときの
  承認フロー・評価ゲート（`evaluation-framework`）の当て方、および `banks/` の保持世代数・GC 方針。
- 分布が大きく乖離するドメインを物理分割（`researches.md §3.3`）する場合の、メモリバンク版軸の扱い
  （グローバル 1 軸のまま複数索引を内包するか、パーティション別版＋部分スワップにするか）。
