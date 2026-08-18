# 調査と設計判断

## Summary

- **Feature**: `primary-anomaly-detection`
- **Discovery Scope**: Extension（実装済み 2 パッケージの上に新規 2 パッケージを積む）
- **Key Findings**:
  - `patch_feature_store` は正常特徴ベクトルの読み出しを公開していない。Requirement 2 の
    入力供給元はストアではなく合成ルートに置くしかない。
  - 近傍距離はコサイン距離で `[0, 2]` に収まる。埋め込み次元に依存しないため、
    Requirement 3.4 の共通尺度をこの性質の上に構築できる。
  - `PatchFeatureSet` は画像 H/W を持たないが、`positions` と `patch_stride` から
    厳密に復元できる。上流のタイル配置が画像全面を被覆するため。
  - CLI を `primary_anomaly_detection` 内に置くと `evaluation_framework` との
    パッケージ間相互依存が発生する。合成ルートは別パッケージにする必要がある。

## Research Log

### 正常メモリバンクの公開契約

- **Context**: Requirement 2 の「正常分布の推定に用いる正常特徴」の供給元が未確定と
  requirements.md に明記されており、design phase で解決する必要がある。
- **Sources Consulted**: `src/patch_feature_store/engine.py`、`model/query.py`、
  `model/ports.py`、`catalog/admission.py`、`__init__.py`。
- **Findings**:
  - 公開メソッドは `register` / `search_normal` / `similarities` / `describe` /
    `find_prototypes` / `resolve` / `operations` / `reselect_coreset` / `prune_expired` /
    `build_bank` / `bank_composition` / `save` / `restore`。
  - `similarities()` は指定した prototype_id 群に対するクエリとの内積を返すだけで、
    ベクトルそのものは返さない。
  - ベクトル復元 `reconstruct()` は `VectorIndex` port のメソッドであり、
    `PatchFeatureStore` の公開面には出ていない。
  - `_identity` も非公開。`accept_query` はストアが保持する値と「問い合わせに載せた値」を
    比較するだけで、ストア自身の同一性メタを外へ返す公開 API は無い。
- **Implications**: ストアから正常特徴を取り出す経路は無い。ストアに読み出し API を足すのは
  `patch-feature-store` の公開契約変更であり本 spec の境界外。したがって Requirement 2 の
  入力は呼び出し側が渡す。同一性メタも同様に、正常分布を生成した抽出器を知っているのは
  合成ルートだけなので、Requirement 9.5 の期待値は合成ルートから検出器へ渡す。

### 距離尺度と正規化

- **Context**: Requirement 3.2（共通尺度への変換）と 3.4（埋め込み次元非依存）の実現方法。
- **Sources Consulted**: `boundary/faiss_index.py`、`catalog/admission.py`、
  `feature_extraction/boundary/timm_backbone.py`、`.kiro/steering/tech.md`、
  `docs/visa-validation-gate.md`。
- **Findings**:
  - 登録・問い合わせの両方でベクトルは L2 正規化される。索引は `IndexFlatIP`。
  - 正規化を行うのはストア内部（`_normalized_registration_vectors` /
    `_normalized_query_vector`）であり、`PatchFeatureSet.embeddings` は未正規化のまま渡ってくる。
    抽出器側の正規化は入力画素の平均・分散正規化（`_normalize_and_pad`）と backbone final norm
    だけで、埋め込み行の L2 正規化は行わない。
  - `NeighborHit.distance = 1 - inner_product`。単位ベクトル同士なので範囲は `[0, 2]`。
  - ゲート文書も「埋め込み次元が異なると L2 距離の絶対値を横並びにできない。正規化方法を
    統一し、運用点は分位点で与える」と明記している。
- **Implications**: k 近傍側は理論上限 2 で割るだけで次元非依存の `[0, 1]` になる。
  Mahalanobis は自由度 `D` のカイ分布に従うため、`sqrt(D)` を尺度パラメータにした
  飽和写像で `[0, 1)` に揃える。あわせて、正常特徴が抽出器から直接渡る Mahalanobis 経路では
  誰も L2 正規化していない状態が起こり得るため、較正側が自分で正規化する必要がある
  （下記 Decision 参照）。

### パッチ位置と画素格子

- **Context**: Requirement 4.2（元画像と同じ画素格子）の実現に画像 H/W が要る。
- **Sources Consulted**: `feature_extraction/geometry/tiling.py`、`geometry/patch_positions.py`、
  `engine.py`、`model/features.py`。
- **Findings**:
  - `_axis_origins` は最後の原点を `size - tile_size` に必ず揃える。タイルは画像全面を被覆する。
  - この端寄せにより、`overlap = 0` でも画像サイズが `tile_size` の倍数でなければ最後のタイルが
    隣のタイルと重なる。重なりは設定値だけからは決まらない。
  - `FeatureExtractionEngine.__init__` が `tile_size % patch_stride == 0` を強制する。
  - `patch_positions` はタイルごとに `patch_stride` 刻みで `(top, left)` を並べる。
  - 以上より `max(top) = H - patch_stride`、`max(left) = W - patch_stride` が厳密に成立する。
  - `PatchFeatureSet` には H/W フィールドが無い。
- **Implications**: `positions` からの復元が唯一の権威ある経路。呼び出し側から H/W を
  別途受け取ると、特徴集合と食い違ったときに検出できない。復元を採用し、上流のタイル配置規則の
  変更を revalidation trigger に明記する。

### anomalib VisA データセットの取り扱い

- **Context**: Requirement 9 の安全な失敗と、Requirement 8.3 のカテゴリ制限。
- **Sources Consulted**: `feature_extraction/boundary/anomalib_source.py`、
  `docs/visa-validation-gate.md`、`uv run python` による `CATEGORIES` の実測。
- **Findings**:
  - `visa_image_source()` は内部で `datamodule.prepare_data()` を呼ぶ。
    未取得なら確認なしにダウンロードが始まる（ゲート文書の既知の罠 1）。
  - `apply_cls1_split()` は `root/split_csv/1cls.csv` を読んで `root/visa_pytorch/` へ
    画像を複製する。読み取り専用ストレージでは失敗する（同 2）。
  - `CATEGORIES` は 12 要素のタプルで実測確認済み。
  - anomalib の `Visa` が準備済みと見なすのは `{root}/visa_pytorch/{category}` と
    `{root}/{category}` の 2 つだけで、配布元が作る `VisA_pytorch/1cls/{category}` は
    どちらにも当たらない。ただし `root` に `.../VisA_pytorch/1cls` を渡せば
    2 つ目の経路で認識される。
- **Implications**: 検証は `visa_image_source()` の**呼び出し前**に置く。準備済みの場合は
  書き込み可否を要求しない（読み取り専用の準備済みデータで回せるようにするため）。
  1cls 配置を準備済みと認めるなら、guard は判定だけでなく
  「`visa_image_source()` へ渡す root」も返す必要がある（下記 Decision 参照）。

### 指標の前倒し実装と依存方向

- **Context**: Requirement 7.3 が要求する image-level AUROC / AUPRO は
  `evaluation-framework` の所有で、現時点で未実装。
- **Sources Consulted**: `.kiro/steering/roadmap.md`（Shared seams）、
  `.kiro/specs/evaluation-framework/brief.md`、`.kiro/specs/primary-anomaly-detection/brief.md`、
  `pyproject.toml`（import-linter contracts）。
- **Findings**:
  - roadmap と両 brief が「呼び出しは合成ルート（CLI）に限る」「循環依存にしない」と明記。
  - `evaluation-framework` の brief は「指標モジュールは検出側の実装に依存させず、
    スコアと正解ラベル／マスクだけを受け取る純粋な形にする」としている。
  - steering は「パッケージ間の依存も一方向。逆流と相互依存は両向きの forbidden 契約で止める」。
- **Implications**: 指標モジュール単体は循環しないが、`evaluation-framework` 全体は
  `primary-anomaly-detection` に依存する（roadmap の依存順）。したがってパッケージ単位で
  `primary_anomaly_detection → evaluation_framework` を作れない。合成ルートを別パッケージに
  切り出す。

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations |
| --- | --- | --- | --- |
| 単一パッケージ + app 層 | CLI を検出パッケージ内に置く | ファイル数が少ない | パッケージ間相互依存が発生する |
| 検出パッケージ + 合成ルートパッケージ | CLI を `visa_gate` に分離 | 依存が一方向。steering に整合 | パッケージが 1 つ増える |
| CLI を scripts のみに置く | 実装を全部シェル起動スクリプトに | 最小 | pytest から起動できない（Req 10.1 不可） |

採用は 2 番目。3 番目は `pythonpath = ["src"]` の下で `scripts/` が import できず
Requirement 10.1 を満たせないため却下。

## Design Decisions

### Decision: 合成ルートを別パッケージ `visa_gate` として切り出す

- **Context**: Requirement 7–10 の CLI が `evaluation_framework` の指標を呼ぶ必要がある。
- **Alternatives Considered**:
  1. `primary_anomaly_detection.app` に CLI を置き、非 app 層からの
     `evaluation_framework` import を forbidden contract で禁止する。
  2. CLI を `scripts/` のシェル／Python スクリプトだけに置く。
- **Selected Approach**: `src/visa_gate/` を新設し、`cli` → `gate` → `boundary` → `model` の
  層構成にする。ロジックは持たず、順序と配線と入出力だけを持つ。
- **Rationale**: 案 1 はモジュール単位では循環しないがパッケージ単位では相互依存になり、
  steering の「パッケージ間の依存も一方向」に反する。案 2 は `pythonpath = ["src"]` の下で
  自動テストから起動できず Requirement 10.1 を満たせない。
- **Trade-offs**: パッケージが 1 つ増える。代わりに検出ロジックがデータセット・永続化・指標を
  一切知らない状態を保てる。
- **Follow-up**: import-linter contract を追加し、`primary_anomaly_detection` から
  `visa_gate` / `evaluation_framework` への import を禁止する。

### Decision: ストア隔離と ML ライブラリ隔離を別々の forbidden contract で検査する

- **Context**: 境界コミットメントに「`patch_feature_store` の import は
  `primary_anomaly_detection.boundary` に閉じる」「ML ライブラリは直接 import しない」の
  2 つがある。前者を検査する contract は既存パッケージに前例がなく、後者は
  `boundary` がストア経由で faiss を推移的に引くため既存の書き方をそのまま使えない。
- **Sources Consulted**: `pyproject.toml:206-232`（既存の forbidden contract 2 種）、
  `.venv/.../importlinter/contracts/forbidden.py:56, 72, 131`、
  `src/patch_feature_store/__init__.py:1-4`。
- **Alternatives Considered**:
  1. ML ライブラリ contract の `source_modules` から `boundary` を除く（既存 2 パッケージと同形）。
  2. ML ライブラリ contract をパッケージ全体に張り、`allow_indirect_imports = true` を付ける。
  3. ML ライブラリ contract をパッケージ全体に張ったまま、ストアの import を
     サブモジュール粒度に限定して間接チェーンを作らない。
- **Selected Approach**: 案 2。ストア隔離は別 contract
  （`source_modules = model | scoring | localization | engine`、
  `forbidden_modules = patch_feature_store`）で検査する。
- **Rationale**: 案 1 は `boundary` が検査対象から外れる。既存 2 パッケージが `boundary` を
  除くのは、その `boundary` が ML ライブラリを実際に使うからであり、本パッケージには
  当てはまらない（使うのは numpy と `patch_feature_store` だけ）。案 3 は成立するが、
  `from patch_feature_store import PatchFeatureStore` という素直な書き方が faiss 違反として
  落ちる構造を残す。`allow_indirect_imports = true` は「直接 import だけを違反とする」設定で
  （`forbidden.py:131`）、上流パッケージが内部で何を使うかに contract を左右されなくなる。
- **Trade-offs**: 間接チェーンを見ないため、`primary_anomaly_detection` の内部モジュールが
  「ML ライブラリを import する別の自作モジュール」を経由する抜け道は検出できない。
  本パッケージには ML ライブラリを import するモジュールが 1 つも無いので現時点で穴にならず、
  もし入れるなら ML ライブラリ隔離の宣言自体を見直す場面になる。
- **Follow-up**: 実装時に `PYTHONPATH=src uv run lint-imports` を通し、2 本の contract が
  意図どおり kept になることを確認する。

### Decision: Mahalanobis の正常特徴は合成ルートが供給する

- **Context**: requirements.md が「Requirement 2 の入力となる正常特徴の供給元は未確定」と
  明記し、design phase での解決を求めている。
- **Alternatives Considered**:
  1. `patch_feature_store` に正常ベクトル読み出し API を追加する。
  2. `VectorIndex` port の `reconstruct()` を本パッケージから直接叩く。
  3. 較正の入力を呼び出し側から受け取る。
- **Selected Approach**: 案 3。`MahalanobisCalibration.fit(normal_features)` が
  `(N, D)` 配列を受け取る。VisA ゲートは `train/good` から抽出した正常パッチ特徴を
  ストア登録と較正の両方に渡す。あわせて **L2 正規化を較正側の責務にする**。
  抽出器は埋め込みを L2 正規化しないため、ゲートが渡す配列は未正規化である。一方
  `detect()` がスコア化するのは L2 正規化後の埋め込みで、ストアも内部で正規化する。
  較正が入力をそのまま使うと平均・共分散だけが別空間に残り、エラーにならずに距離が
  無意味になる。`fit()` / `extend()` で正規化すれば、供給元が誰であってもこの食い違いが
  起きない。ゲート側に正規化を置く案は採らない。合成ルートに数値処理を持ち込むうえ、
  他の呼び出し元が現れたときに同じ手順を再掲する必要が生じるため。
  正規化の定義は `scoring/mahalanobis.py` の `l2_normalize_rows()` 1 箇所に置き、
  `detect()` も同じ関数を呼ぶ。ノルム 0 の行はストアの `admission` と同じく `ValueError` にし、
  `fit` / `extend` / `detect()` の 3 経路で退化入力の扱いを揃える。片方だけが nan を通すと、
  `MAHALANOBIS` 単独構成でストアの検査を経ない経路が無音で壊れるため。
- **Rationale**: 案 1 は `patch-feature-store` の公開契約変更で本 spec の境界外。
  案 2 はストアの内部 port を迂回利用することになり、ストアが所有する
  「何が生存プロトタイプか」の判断を無視してしまう。案 3 は Requirement 2.1 の
  「正常特徴が与えられる」という文言とも一致する。
- **Trade-offs**: 較正対象はストアの現在の生存集合ではなく、呼び出し側が渡した集合になる。
  coreset 再選抜や剪定の影響は較正に反映されない。VisA ゲートでは登録直後の全件を渡すため
  実害は無いが、運用時にストアの内容と較正が乖離し得ることを制約として記録する。
- **Follow-up**: 運用フェーズで乖離が問題になった場合、`patch-feature-store` 側に
  「較正用の正常ベクトル取得」を新しい公開操作として提案する。本 spec では行わない。

### Decision: 正規化は次元非依存の固定写像にする

- **Context**: Requirement 3.4 が「埋め込み次元が異なるバックボーン間でも同一の正規化規則」を
  要求している。
- **Alternatives Considered**:
  1. 画像内 z-score または順位化。
  2. 正常集合上のスコア分位点で割る。
  3. 理論スケールによる固定写像。
- **Selected Approach**: 案 3。k 近傍は `mean(コサイン距離) / 2`、
  Mahalanobis は `d / (d + sqrt(D))`。
- **Rationale**: 案 1 は画像ごとに尺度が変わるため image-level AUROC の比較が壊れる。
  案 2 は正常集合全件をスコア化する必要があり、k 近傍側は正常件数分の FAISS 検索が追加で走る。
  案 3 はコサイン距離の理論上限 2 とカイ分布の尺度 `sqrt(D)` という既知の性質だけを使い、
  テスト入力にも正常集合の再走査にも依存しない。
- **Trade-offs**: 飽和写像は大きな距離を圧縮するため、極端な外れ値の差が縮む。
  ROI の運用点は分位点で与える（Req 3.5）ので、単調性が保たれていれば実害は無い。
- **Follow-up**: バックボーン比較実験で融合重みの意味が保たれるかを確認する。

### Decision: Mahalanobis 較正は十分統計量で保持する

- **Context**: Requirement 2.4 が「追加分を含めて正常分布を推定し直す」再較正を要求している。
- **Alternatives Considered**:
  1. 較正時の正常特徴配列をそのまま保持し、追加時に連結して再計算する。
  2. 件数・和ベクトル・スキャッタ行列だけを float64 で保持する。
- **Selected Approach**: 案 2。あわせて、そこから求めた共分散の Cholesky 因子も保持する。
  分解の成否が Requirement 2.3 の判定そのものなので `fit` / `extend` の時点で確定させる必要があり、
  結果を捨てると `scores()` ごとに分解し直すことになる。
- **Rationale**: 案 1 は `N x D` を保持し続ける。`D = 384`、`N = 10^6` で約 1.5GB。
  案 2 はスキャッタ行列と Cholesky 因子の `(D, D)` 2 枚（約 2.4MB）で済み、しかも
  「全件をまとめて較正した結果」と数学的に一致する。
- **Trade-offs**: スキャッタ行列の累積は桁落ちし得るため float64 で持つ。`extend()` のたびに
  Cholesky を取り直すため、追加較正のコストは分解 1 回分になる。
- **Follow-up**: `fit(A).extend(B)` と `fit(concat(A, B))` の一致をテストで固定する。

### Decision: 共分散にリッジ項を入れない

- **Context**: PaDiM 系の実装は共分散に `eps * I` を足して特異性を回避することが多い。
- **Alternatives Considered**:
  1. `eps * I` を足す、または Ledoit-Wolf 縮約を使う。
  2. 経験共分散のみを使い、不足時はエラーにする。
- **Selected Approach**: 案 2。`N < D + 1` または Cholesky 失敗でエラー。
- **Rationale**: Requirement 2.3 が「共分散を定めるのに不足している場合はエラー」を明示的に
  要求している。リッジ項や縮約を入れると常に計算できてしまい、この要件が働かなくなる。
- **Trade-offs**: 正常特徴が少ない条件では使えない。VisA の `train/good` はパッチ数が
  埋め込み次元を大きく超えるため実行上の制約にならない。
- **Follow-up**: 実データで `N < D + 1` が現実的に起きるようであれば、縮約推定の採否を
  requirements phase に差し戻して再検討する。

### Decision: 重なり領域の合成は算術平均

- **Context**: Requirement 4.3 は「同一入力に対して同一の値となる規則」だけを要求している。
- **Alternatives Considered**: 最大値、算術平均。
- **Selected Approach**: 算術平均。寄与和と寄与回数を別配列に積んで最後に除算する。
- **Rationale**: 加算は交換則を満たすためパッチ走査順に依存せず決定的。最大値も決定的だが、
  タイル境界付近の画素だけが重なりによって系統的に高くなり、タイル格子模様が出る。
- **Trade-offs**: 小さな欠陥が重なり領域にあると平均で薄まる。この薄まりは `overlap = 0` でも
  回避できない。`feature_extraction/geometry/tiling.py` の `_axis_origins` は最終タイル原点を
  必ず `size - tile_size` へ寄せるため、画像サイズが `tile_size` の倍数でなければ端のタイルが
  重なる。anomalib の datamodule はリサイズを強制せず画像はネイティブ解像度で得られる
  （`docs/visa-validation-gate.md` の「リサイズを強制しない」）ので、ゲート既定の
  `tile_size = 512` では端の重なりが常時発生する前提で扱う。
- **Follow-up**: 端寄せで重なる配置（`overlap = 0` かつ非倍数サイズ）で ROI の再現性を確認し、
  重なり幅に対する代表スコアの薄まり量を測る。

### Decision: ドメイン鍵は engine が 1 回解決し、2 方式の非対称を許容する

- **Context**: Requirement 6.2 は「ドメインタグで分布を選択する」と要求するが、k 近傍は
  ストアの `DomainCriteria`、Mahalanobis は `Mapping[DomainTags, ...]` の鍵という別の語彙で
  引き当てる。両者の対応が未定義だと、同じ `DomainTags` でも該当有無が食い違う。
- **Sources Consulted**: `patch_feature_store/model/criteria.py`（`DomainCriteria` の軸と
  空集合の意味）、`patch_feature_store/engine.py` の `_normal_search_selection`、
  `design.md` の `MahalanobisCalibrationSet.select`。
- **Findings**:
  - `DomainCriteria` は軸ごとの集合で、空集合の軸は「無指定（何にでも一致）」。したがって
    `DomainTags` の `None` 軸を空集合に写すと、k 近傍の候補集合は鍵より広くなる。
  - 較正側は鍵ごとに独立した平均・共分散を持つ。軸を緩めた集合に対応する分布を
    既存の較正から合成する手段は無い（十分統計量を足せるのは同じ母集団の追加分だけ）。
- **Alternatives Considered**:
  1. 較正側にも軸ごとの緩和を実装し、部分一致した鍵の統計量を合算して分布を作る。
  2. k 近傍側の変換を完全一致に狭め、`None` 軸を「値が `None` であること」として扱う。
  3. 解決は engine の 1 関数に集約し、鍵の意味を「`DomainTags` 値そのもの」と定義した上で、
     引き当て範囲の非対称は許容する。
- **Selected Approach**: 案 3。`_resolve_domain_scope` が鍵を 1 回決め、同じ値を両方式へ渡す。
  各方式は独立にフォールバックを判定し、片方だけ該当ありでもエラーにしない。
- **Rationale**: 案 1 は十分統計量の合算対象を「異なる母集団の合成」に広げることになり、
  Requirement 2.4 が保証する `fit(A).extend(B) == fit(concat(A, B))` の意味を崩す。
  案 2 はストアの検索語彙を本 spec の都合で再定義することになり、境界外の挙動に依存する。
- **Trade-offs**: 同じ鍵で k 近傍は該当あり・Mahalanobis は該当なしという状態が起こり得る。
  この場合 Mahalanobis だけがプール較正に落ち、`domain_fallback_applied` が true になる。
  どちらの方式が落ちたかは記録に残らない。方式別のフォールバック記録は
  Requirement 6.4 が求めていないため持たせない。
- **Follow-up**: 方式ごとの落ち先を区別する必要が出たら、`domain_fallback_applied` を
  方式別のマップに広げる（`ScoringProvenance` の契約変更として扱う）。

### Decision: `domain_scope` は要求した鍵を記録する

- **Context**: Requirement 6.5 は「使用したドメイン範囲を記録する」と書くが、
  フォールバックが起きたときに「要求した鍵」と「実際に使った範囲（プール）」のどちらを
  指すのかが決まっていない。
- **Alternatives Considered**:
  1. フォールバック時は `domain_scope` を `None` に書き換え、実際に使った範囲を表す。
  2. `domain_scope` は要求した鍵のままにし、落ち先は `domain_fallback_applied` で表す。
- **Selected Approach**: 案 2。`domain_scoped` が false のときだけ `None` になる。
- **Rationale**: 案 1 は 1 つのフィールドに「要求」と「結果」の 2 つの意味を持たせ、
  `None` が「ドメイン限定していない」と「限定したが落ちた」の両方を意味してしまう。
  2 フィールドに分ければどちらの状態も曖昧さなく復元できる。
- **Trade-offs**: 読み手は 2 フィールドを併せて解釈する必要がある。
- **Follow-up**: なし。

### Decision: カテゴリ一覧は `visa_gate.model` の定数として写す

- **Context**: Requirement 8.3 のカテゴリ制限を `anomalib...CATEGORIES` で行うと、
  `model` 層と `cli` 層が anomalib を import することになる。
- **Sources Consulted**: `.kiro/steering/structure.md:68-69`（torch / timm / anomalib / faiss の
  import は `boundary` 限定、`model` は numpy で書く）、`docs/visa-validation-gate.md:97`。
- **Alternatives Considered**:
  1. `model/config.py` から `anomalib...CATEGORIES` を import する。
  2. 12 件を `VISA_CATEGORIES` として写し、上流との一致を `boundary` のテストで照合する。
- **Selected Approach**: 案 2。
- **Rationale**: 案 1 は steering の層制約に直接反する。ゲート文書が `CATEGORIES` を
  `choices` にすると書いているのは値の出所の指定であって、import 位置の指定ではない。
- **Trade-offs**: anomalib 側の一覧が変わると定数が古くなる。これを検知する回帰テストを
  1 本置いて代償する（`pytest.importorskip("anomalib")` 付き）。
- **Follow-up**: なし。

### Decision: guard は判定と同時に「渡す root」を返す

- **Context**: `research.md` の既知リスクは 1cls 配置も準備済みとして認識すると決めたが、
  anomalib が見るのは `{root}/visa_pytorch/{category}` と `{root}/{category}` の 2 つだけで、
  guard が準備済みと判定しても抽出側が同じデータに到達できない。
- **Alternatives Considered**:
  1. guard は `None` を返し、root の解決を `extraction_assembly` にもう一度書く。
  2. 1cls 配置を対象外にし、`visa_pytorch` 配置だけを準備済みとする。
  3. guard が解決した root を返し、`extraction_assembly` はそれを受け取るだけにする。
- **Selected Approach**: 案 3。`resolve_prepared_visa_root()` が検証と解決を 1 か所で行う。
  判定は 4 ケースの **first-match** とし、順序は
  (1) `visa_pytorch/{category}`、(2) `VisA_pytorch/1cls/{category}`、(3) `{category}`、
  (4) 未取得 とする。「いずれかに一致」だと複数配置が同時に存在したときに返す root が
  実装者判断になるため、順序付きで定義する。#1 を先頭にするのは anomalib 自身の判定順
  （`visa.py:180-191` が `visa_pytorch/{category}` → `{category}` の順に見る）に合わせるため。
  #2 を #3 より先にするのは、#3 だけが複製と書き込みを伴うためである。
  書き込み可否の検証は #3 と #4 に対して行う。`apply_cls1_split()` が
  `{root}/visa_pytorch/` へ 12 カテゴリ分を複製するので、#3 は「取得済みだが準備に書き込みが
  必要」な状態にあたり Requirement 9.4 の対象になる（#1 / #2 は読み取り専用でも回せる）。
- **Rationale**: 案 1 は「どの配置を準備済みと見るか」の規則が 2 か所に分かれ、片方だけ
  変えたときに guard は通るが抽出が落ちる状態になる。案 2 は前処理済みデータの流用という
  現実的な運用（約 16GB の再取得と全カテゴリ複製の回避）を捨てる。
- **Trade-offs**: 関数名と戻り値が「検証」から「検証＋解決」に広がる。名前を
  `ensure_visa_dataset_ready` から `resolve_prepared_visa_root` に変えて意味を合わせる。
- **Follow-up**: MVTec など他データセットを足すときは、データセット別の解決規則を
  boundary 内で分ける（配置規則はデータセット固有の知識）。

### Decision: `--backbone` はプリセットキーに限定する

- **Context**: Requirement 8.1 がバックボーンを引数で受け取ることを要求している。
- **Alternatives Considered**:
  1. timm のモデル名を自由入力させ、特徴層とレイアウトを名前から推定する。
  2. `BackboneConfig` を完全形で持つプリセット表を用意し、キーを選ばせる。
- **Selected Approach**: 案 2。初期プリセットは `docs/visa-validation-gate.md:58` が挙げる
  比較対象 4 種（DINOv3・DINOv2・DINO・`wide_resnet50_2`）で、値は timm 1.0.28 で実測して
  確定した。`vit_small_patch16_dinov3.lvd1689m` / `vit_small_patch14_dinov2.lvd142m` /
  `vit_small_patch16_224.dino` はいずれも depth 12・`embed_dim` 384 で、最終ブロックを指す
  `feature_layer` は `blocks.11`。`wide_resnet50_2.tv_in1k` は `layer3` の `reduction` が 16。
  あわせて**タイル設定をプリセットに含める**。
- **Rationale**: `BackboneConfig` は `feature_layer` と `feature_layout` を必須とし、
  `blocks.<int>` かどうかの検証まで行う。モデル名からこれらを推定する規則は存在せず、
  推定を書けば新しい暗黙契約を作ることになる。タイル設定を含めるのは、
  `FeatureExtractionEngine` が `tile_size % patch_stride == 0` を構築時に要求する一方
  （`ssl-vit-feature-extraction/design.md:427`）、DINOv2 の timm 実装だけ patch 14
  （実測: `patch_embed.patch_size == (14, 14)`）で `512 % 14 != 0` になるためである。
  全プリセット共通の `tile_size = 512` を置くと、`--backbone dinov2` が構築時 `ValueError` で
  必ず落ちる。逆に全体を 518 に寄せると patch 16 系が落ちる。
- **Trade-offs**: プリセットに無いバックボーンを試すには表への追記が要る。`dinov2` だけ
  `tile_size = 518` になり、`docs/visa-validation-gate.md:62` の「タイル化・パッチ化のサイズを
  揃える」を厳密には満たせない。もっともパッチストライドが 14 と 16 で異なる時点で
  パッチグリッドは揃わず、同文書も「バンクサイズはパッチ数でも揃える」として差の存在を
  前提にしている。実値は `run_conditions.json` に残るため比較時に追える。
- **Follow-up**: 比較実験でプリセットが不足したら表に追記する（設計変更を伴わない）。
  ViT-S/14 と ViT-S/16 のパッチ数差が比較結果に効くようなら、パッチ数を揃える
  部分サンプリングを `evaluation-framework` 側の実験プロトコルとして足す。

### Decision: 実行ディレクトリは条件名 + 連番で採番する

- **Context**: Requirement 8.4 が「先行実行の結果を上書きせずに残す」ことを要求している。
- **Alternatives Considered**: タイムスタンプ付与、条件名のみ、条件名 + 未使用連番。
- **Selected Approach**: `{category}__{backbone}`、既存なら `-2`, `-3`, ... を付ける。
- **Rationale**: タイムスタンプは時計への依存が生まれテストが不安定になる。条件名のみでは
  同一条件の再実行で上書きが起きる。連番は決定的かつ上書きしない。
- **Trade-offs**: 並行実行時に採番が競合し得る。ゲートは単一プロセス実行を前提とする。

## Risks & Mitigations

- **`evaluation_framework` 未実装** — Requirement 7.3 は同パッケージの前倒し実装に依存する。
  本 spec は port と値型を定義し、`boundary/metrics_adapter.py` だけが import する形にする。
  E2E テストは `pytest.importorskip("evaluation_framework")` で skip し、テスト全体を
  失敗させない。ゲートの完全通過は同実装の完了が前提条件であることをタスク側に明記する。
- **import-linter が未実装パッケージ名をどう扱うか未確認** — `include_external_packages = true`
  の下で `evaluation_framework` への import を含むモジュールが解析対象になったとき、
  `lint-imports` が失敗するかは未確認。実装時に `PYTHONPATH=src uv run lint-imports` で
  確認し、失敗する場合は `metrics_adapter.py` を追加するタスクを
  `evaluation_framework` 実装後に回す。
- **近傍探索の逐次呼び出し** — `search_normal` はパッチごとに 1 回。VisA の test 分割全体で
  「画像数 × パッチ数」回の FAISS 検索が走り、実行時間が長くなる。ゲートは配線確認が目的なので
  許容し、バッチ探索が必要になった時点で `patch-feature-store` の契約追加として扱う。
- **バンク単位の突き合わせ範囲を持たない** — `NormalSearchQuery.bank_id` はストア側に存在するが、
  本 spec の要件にバンク単位のスコープ指定は無く、`store_normal_neighbor_search` は常に `None` を
  渡す。渡す口だけ先に開けても呼び出し元が無く値の出所が追えなくなるため、必要になった時点で
  `NormalNeighborSearch` port の契約追加として、渡す呼び出し元と一緒に入れる。
- **登録コスト** — `register()` は登録のたびに既存全体への最近傍探索を行うため、
  `train/good` の規模に対して二次的に効く。`--category` を PCB 系 1 カテゴリに絞ることで
  現実的な規模に保つ。
- **VisA の 1cls レイアウト不一致** — 配布元の前処理済みデータは
  `VisA_pytorch/1cls/{category}` だが anomalib は `{root}/visa_pytorch/{category}` を見る。
  `dataset_guard` は 3 配置（`visa_pytorch/{category}`、`VisA_pytorch/1cls/{category}`、
  `{category}`）をこの順に判定して「取得済み」と認識し、どれでもないときだけ未取得と
  判定する。1cls 配置のときは `visa_image_source()` へ渡す root を
  `data_root/VisA_pytorch/1cls` に解決する（上記 Decision「guard は判定と同時に
  『渡す root』を返す」）。
- **VisA は代理データ** — 半導体検査画像ではないため、ゲート通過は検出性能の妥当性を
  意味しない。暫定下限 0.9 は配線ミス検知の目安であってチューニング目標ではないことを
  CLI の警告文にも明記する。

## References

- `docs/visa-validation-gate.md` — ゲートの合格条件・引数・既知の罠。
- `docs/researches.md` §3.1、§3.2、§3.3、§8 — 一次検出とドメイン別再較正の方針。
- `docs/library-adoption-proposal.md` — ライブラリ採用方針（指標は自作しない）。
- `.kiro/steering/tech.md` / `structure.md` / `roadmap.md` — 依存方向・層構成・spec 分割。
- `.kiro/specs/evaluation-framework/brief.md` — 指標モジュールの純粋性と前倒し範囲。
