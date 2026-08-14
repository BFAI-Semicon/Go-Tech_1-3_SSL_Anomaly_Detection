# Research & Design Decisions

## Summary

- **Feature**: `patch-feature-store`
- **Discovery Scope**: New Feature（`src/` に 3 つ目のパッケージを新設するグリーンフィールド。ただし上流 `feature_extraction` の出力契約と、下流 `promptable-correction-layer` の識別子期待に挟まれた統合設計）
- **Key Findings**:
  - FAISS 1.14.3 の `IndexIDMap2(IndexFlatIP)` は、int64 の外部識別子・`remove_ids`・`reconstruct`・`SearchParameters.sel` による ID セレクタ検索をすべて満たす。要件の識別子ライフサイクル（安定・不再利用・除外）を索引側の作り込みなしで実現できる。
  - 実測で 50 万件・384 次元に対する 1 クエリの近傍探索が約 8 ミリ秒。1 画像の全パッチ（約 26 万）を逐次登録する設計は成立せず、登録要求単位のバッチ最近傍が必須である。
  - `versioning-model.md` と `correction-layer.md` は「識別子は安定・不再利用」「集約で新 id を発番する場合は旧→新の対応表を残す」「追従は補正側の責務」を定めている。本設計は集約時に必ず新 id を発番する側に倒し、対応表の提示までを本 spec の責務とした。
  - `operations.md` §13 が未決としている距離尺度は、既存 `correction_layer.boundary.prototype_store`（`IndexFlatIP` + 行 L2 正規化）と `MatchCriteria.similarity_threshold` の `[-1, 1]` 検証に整合させ、コサインで確定できる。

## Research Log

### 上流 `feature_extraction` の出力契約と型の再利用

- **Context**: 登録入力の型を新規に定義するか、上流の型を再利用するかを決める必要があった。
- **Sources Consulted**: `src/feature_extraction/model/features.py:21-56`、`src/feature_extraction/model/types.py:8-46`、`src/feature_extraction/__init__.py`、`.kiro/specs/ssl-vit-feature-extraction/design.md`
- **Findings**:
  - `PatchFeatureSet` は `image_id` / `split` / `image_label` / `embeddings` `(N, D)` / `positions` `(N, 2)` / `domain` / `provenance` / `identity` / `conditions` を持ち、要件 4.2 が求める位置・ドメインタグ・由来キーをそのまま供給する。
  - `ExtractorIdentity` は steering `tech.md:102-103` が列挙する 5 項目に加えて `feature_layer` と `feature_layout` を持つ。要件 6.3 の 5 項目を含む上位集合であり、比較対象を全フィールドにすれば要件を満たす。
  - `DomainTags` は 3 軸（`process` / `material` / `equipment`）で、`versioning-model.md:170` の 4 軸（`unit_of_work` を含む）とは異なる。上流が供給しない軸を本機能が作らない方針（要件 4.6）に従い、3 軸で扱う。
  - 上流のパッケージルート `__init__.py` は `boundary` を eager import する。`feature_extraction.model.features` の import だけで torch と anomalib が読み込まれることを実測（13.3 秒）で確認した。一方 grimp の静的グラフでは `feature_extraction.model.features` から torch への経路は存在しない。
- **Implications**: 登録入力は `PatchFeatureSet` をそのまま受け取る。型の再定義をしない。import-linter の禁止契約には影響しないが、実行時に torch が読み込まれる事実は設計に明記する。

### FAISS の能力確認

- **Context**: 識別子の安定性・除外・種別フィルタ・k 超過の扱いを、索引側でどこまで賄えるかを確定する必要があった。
- **Sources Consulted**: インストール済み `faiss-cpu` 1.14.3 に対する実行確認
- **Findings**:
  - `IndexIDMap2(IndexFlatIP(d))` に `add_with_ids` で任意の int64 識別子を与えられる。`remove_ids(IDSelectorBatch)` で削除でき、削除後も残存識別子の `reconstruct` と検索は正しく動く。削除済み識別子の `reconstruct` は `RuntimeError` になる。
  - `search(q, k, params=SearchParameters(sel=...))` が `IndexIDMap2` 越しに機能し、`IDSelectorBatch`（包含）と `IDSelectorNot`（除外）の双方が使える。
  - `k` が対象件数を超えると識別子 `-1` とパディングスコア `-FLT_MAX` が返る。呼び出し側で除去が必要。
  - 性能（WSL2 CPU、D=384、単一試行）: 50 万件の `add` 0.38 秒、1024 クエリ・k=1 のバッチ検索 8.27 秒、除外セレクタ付き 7.87 秒、生存半数の包含セレクタ付き 5.97 秒。10 万件では同条件で 4.05 / 1.43 / 1.24 秒（初回計測に BLAS のウォームアップを含む）。
- **Implications**: 索引アダプタは Flat + IDMap2 で足りる。識別子の retire と間引きは `remove_ids` に写像でき、種別・ドメイン・バンクの絞り込みはセレクタで表現できる。逐次登録は非現実的で、バッチ検索を前提にする。

### anomalib の coreset 実装

- **Context**: `docs/library-adoption-proposal.md:71-76` が「coreset は自作せず anomalib から呼ぶ」と定めているため、API と制約を確認する必要があった。
- **Sources Consulted**: `.venv/.../anomalib/models/components/sampling/k_center_greedy.py`、実行確認
- **Findings**:
  - `KCenterGreedy(embedding: torch.Tensor, sampling_ratio: float)` は絶対件数ではなく比率を取り、`coreset_size = int(n * sampling_ratio)` で件数を決める。`select_coreset_idxs()` が行インデックスの `list[int]` を返す。
  - 目的件数 `M` に対して `sampling_ratio = (M + 0.5) / n` とすれば `M` 件になる。`(M, n)` が `(3,10) (7,10) (19,50) (1,3) (33,100) (2,3)` のいずれでも成立することを確認した。
  - 開始点は `torch.randint`、次元削減は `SparseRandomProjection(eps=0.9)`（`random_state` 未指定）であり、既定では実行ごとに結果が変わる。`torch` / `numpy` / `random` の 3 つのグローバル seed を設定すると同一結果になることを確認した。
  - 入力は torch テンソルであり、`anomalib` と `torch` の import を伴う。
- **Implications**: 採用する。ただし比率変換と決定性の確保はアダプタ側の責務として設計に含める。ポートは行インデックスを返す契約にし、`catalog` と `engine` を torch から切り離す。

### 識別子ライフサイクルと補正レイヤの期待

- **Context**: 集約時に既存識別子を継続するか新識別子を発番するかを確定する必要があった。要件 1.4 / 1.5 / 1.6 と 3.4 / 3.5 は「発番された場合」を条件節にしており、設計側の決定に委ねられている。
- **Sources Consulted**: `docs/structured-json-versioning/versioning-model.md:44-81`、`docs/structured-json-versioning/correction-layer.md:84-96`、`src/correction_layer/model/records.py:86-98`、`.kiro/specs/patch-feature-store/requirements.md:146`
- **Findings**:
  - `versioning-model.md:62-65`: 識別子は安定・不再利用で、除外は論理的 retire（tombstone）。未参照であることを理由に除外しない。
  - `versioning-model.md:80-81`: マージで新 `prototype_id` を発番する場合は旧→新の対応表を残す。
  - `correction-layer.md:92-94`: 参照先が変わった補正レコードは remap で追従し、解決不能なものは当該スナップショットで非適用（skip）。追従の実行は補正側。
  - `correction-layer.md:88-89`: 依存は「補正 → メモリバンク」の一方向。coreset は補正レコードを参照しない。
  - `records.py:86-98`: `MatchCriteria.similarity_threshold` は `[-1, 1]` の有限値として検証される。
- **Implications**: 集約後のプロトタイプは重心が変わるため、既存識別子を継続すると同じ識別子が別ベクトルを指す。しきい値判定の意味が黙って変わることを避け、新識別子の発番と対応表記録に倒す。間引き判定に補正レコードを持ち込まない（要件 5.7）ことも設計上の禁止事項として明示する。

### バンク構成と正常のみ検証プロトコル

- **Context**: 要件 7 のバンクが何を単位に、どこまでの再現性を持つべきかを確定する必要があった。
- **Sources Consulted**: `docs/normal-only-validation-plan.md:41-79, 185-190`、`docs/visa-validation-gate.md:64-66`
- **Findings**:
  - 固定サイズのバンクを B 個作り、各画像をそれを含まないバンクで評価する。折数 K を振るのではなくバンクサイズを独立の軸にする。
  - 分割単位はウェハ ID / ロット ID / 撮像日。近重複がバンク側と評価側に分かれると過検出率が楽観的に出る。
  - バンクの構築・サブサンプル・coreset は `patch-feature-store` の所有、分割プロトコルと指標は `evaluation-framework` の所有。
  - バンクサイズは枚数だけでなくパッチ数でも揃える必要がある。
- **Implications**: バンク仕様は「由来キーの包含・除外 + サイズ + シード」とし、構成条件としてメンバー識別子とパッチ数（寄与パッチ数の合計）を保持する。プロトタイプ件数とパッチ数を別に持つのは、集約により両者が一致しなくなるためである。

### 永続化形式の選択

- **Context**: FAISS の索引ファイルをそのまま保存するか、ベクトルとメタデータを自前形式で持つかを決める必要があった。
- **Sources Consulted**: `.kiro/steering/roadmap.md:52-55`、`docs/library-adoption-proposal.md:38-62`、`docs/structured-json-versioning/file-layout-and-samples.md:16-18, 83-84`、`pyproject.toml:10-37`
- **Findings**:
  - Lance / LanceDB は Phase 5 前のスパイク対象であり、判断までは FAISS 前提の記述を維持すると roadmap が定めている。
  - parquet を読み書きする依存（`pyarrow`）は入っていない。
  - Phase 5 のディスクレイアウトは `banks/<snapshot_id>/` に FAISS インデックス＋メタデータ層＋版メタを置く形で構想されている。
- **Implications**: 本 spec は版管理を持たないため、`banks/<snapshot_id>/` を先取りしない。Flat 索引は生ベクトルそのものなので、`numpy.save` したベクトルから決定的に再構築できる。索引バイナリとベクトルの二重保持を避け、`vectors.npy` を唯一の権威にする。メタデータは依存追加なしで扱える JSON / JSON Lines にする。

### 既存コードベースの規約

- **Context**: 新規パッケージの層構成・公開 API・テスト規約・import 検査を既存に揃える必要があった。
- **Sources Consulted**: `.kiro/steering/structure.md`、`.kiro/steering/tech.md`、`pyproject.toml:85-169`、`src/feature_extraction/**`、`src/correction_layer/**`、`tests/test_public_api.py`
- **Findings**:
  - 層は `model` → 中間層 → `engine` の一方向で、中間層の名前は関心事で決める。中間層のモジュール同士は互いに import しない。
  - 重い外部依存は `boundary` に閉じ、`pyproject.toml` の import-linter 契約で CI 検査する。`root_packages` は既に複数形。
  - boundary の公開はファクトリ関数で行い、具象クラス名を公開面の契約にしない。
  - テスト関数名は `test_should_...`、決定性・集合等価は hypothesis を使う。
- **Implications**: 中間層を `catalog`（台帳と純粋ロジック）と `boundary`（FAISS・anomalib・I/O・時刻）に分け、`catalog` の 6 モジュールを独立に保つ。台帳同士の結合は `engine` が行う。

## Architecture Pattern Evaluation

- **レイヤード + ポート注入（採用）**: 既存 2 パッケージと同じ形。差し替え点（索引・coreset・永続化・時刻）を Protocol にでき、テストで外部依存を外せる。中間層の独立制約により、台帳同士の結合コードが `engine` に集まる点が唯一の負担。
- **索引とメタデータを 1 層に統合（不採用）**: Lance / LanceDB を使えばベクトル検索とスカラーフィルタを 1 データセットで扱えるが、`docs/library-adoption-proposal.md:61-62` と roadmap が Phase 5 前のスパイク事項と定めており、本 spec では前倒ししない。
- **バンクごとに独立索引（不採用）**: バンク数 × ベクトルのメモリ増と、集約・間引きとの整合維持コストが増える。主索引上の ID セレクタで同じ観測結果が得られる。
- **状態を持つ台帳を `boundary` に置く（不採用）**: 台帳は外部 I/O でも外部ライブラリでもない純粋なメモリ構造であり、`boundary` に置くと「外部境界を閉じ込める層」という既存の役割定義が崩れる。

## Design Decisions

### Decision: 索引方式を FAISS Flat 単一に固定する

- **Context**: brief は Flat / IVF / PQ の選択可能性に触れる。requirements は索引方式を design に送っている。
- **Alternatives Considered**:
  1. 方式を設定で切り替えられるようにする
  2. Flat のみ
- **Selected Approach**: Flat のみ。`IndexIDMap2(IndexFlatIP)` を単一の実装とする。
- **Rationale**: steering `tech.md:37` が Flat（CPU）を宣言している。要件 3.1 の距離、6.2 の再読込後の同一結果、補正レイヤの `similarity_threshold` 判定はいずれも厳密解を前提にする。近似索引は `library-adoption-proposal.md:49-59` が指摘するとおり判定への影響評価が要る。
- **Trade-offs**: 大規模化したときの検索費用は線形に増える。方式切替が必要になった時点で `VectorIndex` の別実装を足せる（ポートは既に分離されている）。
- **Follow-up**: 再検証トリガーに「近似索引への変更」を含めた。

### Decision: 距離尺度をコサインに固定する

- **Context**: `operations.md:48` が距離尺度と FAISS メトリックの対応を未決としている。
- **Selected Approach**: 保持ベクトルを L2 正規化し、`IndexFlatIP` の内積をコサイン類似度として扱う。近傍検索はコサイン距離（1 − 類似度）、識別子指定の問い合わせはコサイン類似度を返す。
- **Rationale**: 既存 `correction_layer.boundary.prototype_store` が同じ表現であり、`MatchCriteria.similarity_threshold` は `[-1, 1]` として検証される。ストア側で別尺度を採ると補正側の判定と食い違う。
- **Trade-offs**: 元ベクトルのノルムを保持しない。ノルムを使う下流処理が現れた場合は保存内容の変更（再検証トリガー）になる。
- **Follow-up**: `operations.md` §13 の未決はストア側についてのみ解消する。補正レイヤ側の記述更新は当該 spec の責務。

### Decision: 集約時に新識別子を発番する

- **Context**: 要件 1.4〜1.6 と 3.4 は「集約後に別の識別子が発番された場合」を条件節にしている。
- **Alternatives Considered**:
  1. 既存識別子を継続し、ベクトルだけ更新する
  2. 新識別子を発番し、集約前識別子を retire して対応表に載せる
- **Selected Approach**: 2。
- **Rationale**: 1 は同じ識別子が別ベクトルを指す状態を作り、補正レコードのしきい値判定の意味が黙って変わる。`versioning-model.md:62-65` の「安定」は「識別子が指す対象が変わらないこと」を含むと解した。
- **Trade-offs**: 集約のたびに対応表が伸び、補正側に追従コストが生じる。対応表の連鎖解決は識別子の単調増加により有限で循環しない。
- **Follow-up**: 対応表の連鎖終端性を property test で確認する。

### Decision: 集約判定を登録要求単位のバッチ最近傍で行う

- **Context**: 逐次判定なら要求内の近接パッチも集約できるが、索引検索が直列化する。
- **Selected Approach**: 要求内の全クエリを 1 回のバッチ検索にかけ、要求内のパッチ同士は集約しない。
- **Rationale**: 要件 1.4 の対象は「既存プロトタイプ」であり、要求内のパッチは既存ではない。実測（50 万件で 1 クエリ約 8 ミリ秒）から逐次判定は運用に耐えない。
- **Trade-offs**: 同一要求内の近接パッチは一時的に重複して登録される。次回登録または coreset 再選択で吸収される。
- **Follow-up**: 重複の程度はストア規模スイープ（`evaluation-framework`）で観測できる。

### Decision: メタデータを登録単位に正規化し、登録記録と操作記録を統合する

- **Context**: ドメインタグ・由来キー・担保根拠・annotation メタ・構造化 JSON 参照・適用メタ情報は、いずれも登録要求単位の値である。プロトタイプごとに複製すると 100 万件規模で重複が支配的になる。
- **Selected Approach**: `RegistrationRecord` を権威とし、プロトタイプは寄与ごとに登録 ID と位置だけを持つ。`RegistrationRecord` は要件 8.1 の操作記録そのものでもあるため、メタデータと操作記録を 1 つの型に統合する。
- **Rationale**: 「他の権威データから一意に復元できる値を重複保持しない」というフィールド設計原則に従う。要件 8.1 が求める「担保根拠を含む操作記録」も、統合により join なしで満たせる。
- **Trade-offs**: メタデータ照会（要件 4.3）とドメイン絞り込み（要件 3.6、4.4）が台帳の結合を伴い、`engine` に結合コードが集まる。
- **Follow-up**: `RegistrationRecord.prototype_ids` は登録時点の事実であり、その後の集約・間引きで更新しない旨を設計に明記した。

### Decision: バンクを主索引上の凍結された識別子集合とし、永続化しない

- **Context**: 要件 7.3 は複数バンクの同時保持と検索時指定を、要件 6.1 は永続化対象を列挙している（バンクは含まれない）。
- **Selected Approach**: バンクは bank_id → メンバー識別子集合と構成条件。検索時に包含セレクタとして使う。永続化しない。
- **Rationale**: 要件 7.4 により、同一仕様・同一ストア状態から決定的に再構築できる。永続化すると権威が二重になる。
- **Trade-offs**: 再読込後はバンクを作り直す必要がある。構築後に集約・間引きが起きるとメンバーの一部が生存しなくなる（検索時に生存集合との共通部分を取る）。
- **Follow-up**: 再検証トリガーに「バンクを永続化対象に含める変更」を入れた。

### Decision: 保護対象だけで上限を超える coreset 要求は失敗させる

- **Context**: 要件 5.1（上限以内に収める）と 5.3 / 5.4（保護対象を除外しない）が同時に満たせない状態がありうる。
- **Selected Approach**: 何も除外せず `CoresetSizeLimitError(protected_count, size_limit)` を送出する。
- **Rationale**: どちらかを黙って優先すると、呼び出し側は上限違反にも保護解除にも気付けない。要求自体が充足不能であることを報告するのが誠実である。
- **Trade-offs**: 呼び出し側に上限の再指定または保護の見直しを強いる。
- **Follow-up**: 例外に保護件数と上限を持たせ、次の行動を決められるようにした。

### Decision: annotation メタと適用メタ情報を不透明な文字列マップとして保持する

- **Context**: 要件 4.1 は 3 項目の保持を求めるが、annotation と適用メタのスキーマは `llm-feedback-structuring` と `promptable-correction-layer` の所有であり、まだ確定していない。
- **Alternatives Considered**:
  1. 型付きの構造を本 spec で定義する
  2. 参照文字列だけを持つ
  3. 供給された文字列マップをそのまま保持する
- **Selected Approach**: 3（構造化 JSON への参照だけは単一の参照文字列）。
- **Rationale**: 1 は他 spec の所有物を先取りして定義することになる。2 は要件 4.1 が「メタデータ」「情報」と書く 2 項目を参照に痩せさせる。3 は要件 4.5 / 4.6（未提供のまま保持、生成・正規化をしない）と最も整合する。
- **Trade-offs**: 型安全性が弱い。スキーマ確定後に型付き契約へ置き換える必要がある。
- **Follow-up**: 再検証トリガーに `RegistrationRecord` のフィールド意味変更を含めた。

### Decision: バンク候補から `kind=defect` を除外する

- **Context**: 要件 7.1 は由来キーとサイズだけで候補を規定している。
- **Selected Approach**: 生存かつ `kind != defect` のプロトタイプだけを候補にする。
- **Rationale**: 要件 2.6 により `defect` は正常集合検索から構造的に除外される。バンクに含めると、固定サイズという要件 7 の目的（`normal-only-validation-plan.md:70-74`）に反して実効サイズが黙って縮む。
- **Trade-offs**: 要件文にない制約を 1 つ足している。バンクを `defect` 込みで構成したい用途が将来生じた場合は仕様の追加が要る。

## 一般化・簡素化の記録

- **一般化**: ドメイン限定（要件 3.6）、メタデータ絞り込み（4.4）、バンクの包含・除外（7.1、7.2）は同じ「軸ごとの値集合による一致判定」であり、`DomainCriteria` と `ProvenanceCriteria` の 2 型に統合した。`VectorIndex.search` は複数クエリを受ける契約にし、集約判定のバッチ検索と利用者の単一クエリ検索を同じ入口にした。
- **簡素化**: バンク専用索引、索引方式の設定切替、永続形式のスキーマ版フィールド、次識別子の永続化、除外状態の専用フィールドをいずれも持たない。除外状態は「レコードは存在するが生存集合にも対応表にも無い」ことで表現でき、次識別子は発番済みの最大値から復元できる。
- **採用（build vs adopt）**: 近傍探索は FAISS、coreset は anomalib の k-center greedy を採用した。自作するのは台帳・受け入れ判定・集約規則・間引き規則・バンク構成・永続形式であり、いずれも本プロジェクト固有の運用規則である（`researches.md:223-225` が anomalib の利用範囲を特徴抽出に限定している）。

## Risks & Mitigations

- 登録スループットが線形に悪化する（50 万件で 1 クエリ約 8 ミリ秒）。1 画像の全パッチ登録は成立しない — 設計の Performance 節に実測値と帰結を明記し、上限管理を coreset 再選択に委ねる。上限値の決定は運用側（ストア規模スイープ）へ送る。
- coreset 選択時に候補ベクトル全体を torch テンソルへ複製するため、索引と同規模の一時メモリを要する — 128 GB 統一メモリを前提とし、選択対象を選択可能群に限る（保護群は入力に含めない）。
- 上流パッケージの eager import により、`patch_feature_store` を import しただけで torch と anomalib が読み込まれる（13.3 秒） — 静的な依存契約には影響しないことを grimp で確認済み。実行時コストは上流 spec の公開方式の課題として記録し、本 spec では型の再定義による回避を選ばない。
- annotation メタ・適用メタ情報のスキーマが未確定であり、確定後に契約変更が必要になる — 不透明マップとして保持し、再検証トリガーに含めた。
- バンク構築後の集約・間引きでメンバーが生存しなくなり、評価時の実効サイズが縮む — 検索時に生存集合との共通部分を取る挙動を明示し、構成条件（構築時のメンバーとパッチ数）を保持して差分を観測可能にする。
- `KCenterGreedy` がグローバル RNG に依存する — 要件 5 は coreset の決定性を求めていないため、アダプタはグローバル RNG を操作せず（seed 設定も退避・復元も行わない）、選択結果は非決定のままにする。決定性を要する検証は決定的な代替 `CoresetSelector` を注入して行う。

## References

- `docs/researches.md:115-125, 236-269` — 特徴量ストアの成果物定義と §11 の運用方針（増分追加・汚染防止・coreset・索引方式）
- `docs/structured-json-versioning/versioning-model.md:44-81` — 索引層とメタデータ層の分離、`prototype_id` の安定性、`kind`、`pinned`、マージ時の id 対応
- `docs/structured-json-versioning/correction-layer.md:84-96` — remap 追従と skip の分界、補正 → メモリバンクの一方向依存
- `docs/structured-json-versioning/operations.md:48, 56-60` — 距離尺度の未決事項、`match.prototype_ids` の生成規則
- `docs/normal-only-validation-plan.md:41-79, 185-190` — 複数バンクの構成、グループキー、所有分界
- `docs/library-adoption-proposal.md:38-76` — Lance スパイクの位置づけ、coreset を anomalib から呼ぶ方針
- `.kiro/steering/tech.md:12-19, 37, 95-113` — 層パターン、FAISS Flat（CPU）、バックボーン同一性の運搬
- `.kiro/steering/structure.md:9-11, 41-64` — 層構成、命名規約、公開面の方針
- `.kiro/steering/roadmap.md:52-55, 70-78, 90` — Lance 判断までの FAISS 前提、shared seams、依存順
