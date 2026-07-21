# 構造化 JSON バージョン管理・補正レイヤスキーマ設計メモ（分割済み）

> 本メモはトークン量削減と保守性のため、話題別に [`structured-json-versioning/`](./structured-json-versioning/) へ分割しました。
> 索引は [`structured-json-versioning/README.md`](./structured-json-versioning/README.md) を参照してください。

## セクション → ファイル対応

| セクション            | 話題                                                                   | ファイル                                                                                                         |
| --------------------- | ---------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| §1                    | 全体アーキテクチャ（コンテナ構成）                                     | [structured-json-versioning/README.md](./structured-json-versioning/README.md)                                   |
| §2 / §3 / §4          | バージョン昇格モデル・スナップショット版管理・ドメイン単位管理         | [structured-json-versioning/versioning-model.md](./structured-json-versioning/versioning-model.md)               |
| §5                    | SemiKong オントロジー整合・レジストリ・prefixes                        | [structured-json-versioning/ontology.md](./structured-json-versioning/ontology.md)                               |
| §6 / §9               | 補正レイヤ判定スキーマ・有効スナップショット解決規則・優先順位チェーン | [structured-json-versioning/correction-layer.md](./structured-json-versioning/correction-layer.md)               |
| §7 / §8               | ファイルレイアウト・マニフェスト・JSON サンプル                        | [structured-json-versioning/file-layout-and-samples.md](./structured-json-versioning/file-layout-and-samples.md) |
| §10 / §11 / §12 / §13 | 稼働系ロード・検証・環境依存・未決事項                                 | [structured-json-versioning/operations.md](./structured-json-versioning/operations.md)                           |
