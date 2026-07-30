# Implementation Plan

## 1. 基盤整備

- [ ] 1.1 (P) テスト実行基盤と依存方向契約を整備する
  - pytest の pythonpath／testpaths、dev 依存（hypothesis・import-linter）、および層間 import 契約をプロジェクト設定へ追加する
  - ruff・lint-imports・pytest を Python 3.12 で実行する CI workflow を追加する
  - 完了時: 空のテストでも pytest が `src` を解決して起動でき、CI 定義に ruff／lint-imports／pytest が含まれる
  - _Requirements:_ 1.4
  - _Boundary:_ project-tooling
  - _Depends:_ none

- [ ] 1.2 (P) コア型とポート契約を定義する
  - 一次／最終ラベル、定義側・入力側ドメイン軸、パッチ入力、一次判定・最終判定の共有型を定義する
  - 入力側ドメイン軸はいずれかの軸が any のとき拒否し、定義側は any を許容する
  - 類似度取得とドメイン軸照合の Protocol、近傍ヒット、軸パターン型を定義する
  - 完了時: 入力側 any 拒否と定義側 any 許容がテストで確認でき、SimilaritySource／AxisMatcher 契約が参照可能である
  - _Requirements:_ 8.1
  - _Boundary:_ types, ports
  - _Depends:_ none

- [ ] 1.3 合成プロトタイプストアで近傍検索を提供する
  - 合成プロトタイプ集合を L2 正規化して保持し、最近傍検索と指定 id 群への類似度計算を同一 cosine 尺度で提供する
  - 空集合・非有限値・ゼロノルム・次元不一致・不正な k は構築時または照会時に拒否する
  - FAISS の型や関数を公開 API に出さない
  - 完了時: 既知ベクトルで最近傍の id・類似度が厳密に一致し、未正規化照会も正規化済み入力と同結果になる
  - _Requirements:_ 1.1, 1.2, 2.5
  - _Boundary:_ prototype_store
  - _Depends:_ 1.2

- [ ] 1.4 合成データフィクスチャとテスト用ビルダを用意する
  - 単一／複数ドメイン・不正系を含む手書きドメイン定義フィクスチャを用意する
  - 合成埋め込み・プロトタイプストア・エンジン組み立て用のテストビルダを用意する
  - 完了時: フィクスチャとビルダだけで近傍検索可能なストアをテストから構築できる
  - _Requirements:_ 1.1, 1.4
  - _Boundary:_ test-fixtures
  - _Depends:_ 1.1, 1.3

## 2. 補正レコードと入力境界

- [ ] 2.1 補正レコードモデルと構造制約を実装する
  - 補正レコード 8 フィールド、action／method enum、method 別 params、match、有効レコード型を定義する
  - action×method 規約、類似度条件の対制約、action と params の方向整合、未知フィールド拒否、UTC recorded_at を構築時に強制する
  - 完了時: 許容／拒否の全組合せと params・match 制約が単体テストで確認できる
  - _Requirements:_ 4.4, 5.1, 5.3, 5.5, 5.6
  - _Boundary:_ records
  - _Depends:_ 1.2

- [ ] 2.2 ドメイン定義の構造検証と違反報告を実装する
  - pydantic モデルから JSON Schema を生成し、raw 文書の構造違反を統一違反型へ全件変換する
  - pydantic 意味制約違反を semantic 違反へ変換する
  - 完了時: フィールド欠落・型不一致・enum 定義外の違反理由が報告され、JSON Schema 成果物を取得できる
  - _Requirements:_ 5.2, 5.3, 5.5, 5.6
  - _Boundary:_ schema
  - _Depends:_ 2.1

- [ ] 2.3 有効レコード集合と軸パターン索引を実装する
  - 全有効レコードと軸パターン索引を持つ不変集約を実装する
  - 注入された軸照合器が返すパターンで索引を引き、線形走査せず候補を返す
  - 完了時: 索引エントリの和が全レコードと一致し、同一入力で候補順が安定する
  - _Requirements:_ 6.1, 6.2
  - _Boundary:_ domain_set
  - _Depends:_ 2.1

- [ ] 2.4 ドメイン定義のロードと複数ドメイン合成を実装する
  - 複数パスのドメイン定義を構造検証・意味検証・element_id 横断一意性の順で検証し、違反はファイル別に集約して失敗する
  - 全ドメインの有効要素だけを展開して集約を構築する（削除は不在で表現）
  - 索引データの登録のみ行い、照合意味論は持たない
  - 完了時: 複数ドメイン合成、不正混在時の全違反報告、element_id 重複の cross_file 報告が確認できる
  - _Requirements:_ 1.1, 5.2, 5.3, 5.5, 5.6, 6.1, 6.4
  - _Boundary:_ domain_loader
  - _Depends:_ 1.4, 2.2, 2.3

## 3. 判定ロジック

- [ ] 3.1 合成一次判定を実装する
  - 解決済みの最大類似度から異常スコアを算出し、固定閾値と比較して Positive／Negative を返す
  - ストアへ直接依存せず、解決済み類似度と閾値のみを受け取る
  - 完了時: 異常スコアが閾値を超えるときだけ Positive、等号側は Negative になる
  - _Requirements:_ 1.3
  - _Boundary:_ primary
  - _Depends:_ 1.2

- [ ] 3.2 ExactAny ドメイン軸照合を実装する
  - 具体 4 軸から any 落とし込みを含む適合パターンを specificity 降順で返す照合器を実装する
  - 未知ドメイン入力でも広域パターンが返ることを検証する
  - 完了時: 16 パターンが specificity 降順で返り、未知ドメインでも広域パターンが返る
  - _Requirements:_ 6.2
  - _Boundary:_ axis_matching
  - _Depends:_ 1.2

- [ ] 3.3 類似度条件による適用対象選別を実装する
  - ドメイン軸適合済み候補に対し、類似度条件の有無に応じて適用対象を選別する
  - 指定時は prototype_ids のいずれかが閾値以上なら適用、未達は除外。未指定なら候補をそのまま適用対象にする
  - 完了時: 閾値ちょうどで充足、未達除外、類似度条件なし通過がテストで確認できる
  - _Requirements:_ 2.1, 2.2, 2.3, 2.6, 5.4
  - _Boundary:_ matching
  - _Depends:_ 2.1

- [ ] 3.4 action×method による二次判定を実装する
  - LabelOverride／ScoreReweight／ThresholdAdapt と KeepPrimary の一次→二次変換を実装する
  - ReviewRequired は受け取らない前提とし、スコア再構成と閾値適応の式を設計どおりに適用する
  - 完了時: OverrideNegative／OverridePositive／KeepPrimary と適用可能 method の全経路で二次判定ラベルが期待どおりになる（ReviewRequired は対象外）
  - _Requirements:_ 3.1, 3.2, 3.3, 4.1, 4.2, 4.3
  - _Boundary:_ correction
  - _Depends:_ 2.1

- [ ] 3.5 優先順位チェーンによる競合解決を実装する
  - specificity → ReviewRequired 短絡 → safety → recency → element_id の順で勝者または保留を一意に決める
  - 短絡時は代表 element_id を集合内最大とし、具体 KeepPrimary による広域遮蔽を含めてテーブル駆動で固定する
  - 解決結果の一意性・入力順非依存・全域性を property-based に検証する
  - 完了時: チェーン各段の競合ケースと決定性性質がテストで確認できる
  - _Requirements:_ 3.4, 6.3, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7
  - _Boundary:_ resolution
  - _Depends:_ 2.1

- [ ] 3.6 AxisMatcher と DomainSet 索引の等価性を検証する
  - ExactAny 照合器と軸パターン索引を組み合わせ、candidates が全レコード走査のドメイン軸照合結果と同一集合になることを検証する
  - 未知ドメイン入力でも any レコードを引けることを検証する
  - 完了時: 索引候補と全走査結果が一致し、未知ドメインでも any レコードが引ける
  - _Requirements:_ 6.2
  - _Boundary:_ axis_matching, domain_set
  - _Depends:_ 2.3, 3.2

## 4. オーケストレーションと統合検証

- [ ] 4.1 補正エンジンと公開 API を組み立てる
  - 類似度源・軸照合器・ドメイン集合・一次閾値を受け取り、候補抽出→類似度解決→一次判定→選別→競合解決→補正→最終判定へ合成する
  - 適用対象なしは一次判定を最終判定へ写像し、Positive→NG／Negative→許容／保留→要確認とする
  - 公開 API はドメイン操作の型・エンジン・合成用組み立て入口のみとし、モデル重み更新や永続化を行わない
  - 完了時: 合成データだけで判定を完了でき、最終判定ラベルと applied_element_id の契約を満たす
  - _Requirements:_ 1.1, 1.4, 2.4, 3.4, 8.1, 8.2
  - _Boundary:_ engine
  - _Depends:_ 1.3, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6

- [ ] 4.2 エンドツーエンド判定シナリオを検証する
  - 一次 Positive が近傍プロトタイプ条件で許容へ反転する最小シナリオを検証する
  - 適用候補なしの通過、ReviewRequired による要確認、削除フォールバックと KeepPrimary 遮蔽の対比を検証する
  - 完了時: 上記シナリオが合成フィクスチャのみで再現し、最終判定が期待どおりになる
  - _Requirements:_ 1.4, 2.2, 2.4, 3.1, 3.4, 6.4, 7.6, 8.1
  - _Boundary:_ e2e-validation
  - _Depends:_ 4.1
