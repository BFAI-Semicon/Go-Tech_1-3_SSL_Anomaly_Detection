# Research & Design Decisions

## Summary

- **Feature**: `ssl-vit-feature-extraction`
- **Discovery Scope**: New Feature（グリーンフィールド。`src/` に 2 つ目のパッケージを新設する）
- **Key Findings**:
  - anomalib 2.6.0 の `TimmFeatureExtractor` は `output_fmt="NLC"` を実際に備え、ViT ではバックボーン名に `vit` を含むだけで `forward_intermediates` 経路に入る。パッチトークンのみが返り、CLS・register トークンは `return_class_token=False` で除外される。
  - `requires_grad=False` はパラメータを凍結しない。forward 時に `eval()` と `no_grad()` を適用するだけであり、重み固定を保証するには明示的な凍結が必要。
  - CUDA 上ではバッチ内のタイル数が変わると出力がビット単位で変化する（最大差 5e-3）。`torch.use_deterministic_algorithms(True)` でも解消しない。バッチサイズを固定すればプロセスをまたいで再現する。
  - anomalib の `ImageBatch.collate` は形状混在時に「最大辺を持つ 1 枚の形状」へ全件をリサイズし、アスペクト比を壊す。DataLoader を経由しない設計が必要。
  - anomalib に `Tiler` は存在するが、非公開 API・強いステートフル性・タイル座標を返さない・`stride=None` で例外という問題があり、本機能の要件を満たさない。
  - `.venv` の `opencv-python-headless` が壊れており `import cv2` が失敗する。`anomalib.data` / `anomalib.models` が import できず、実装着手前の解消が必要。
  - 重い依存を層に閉じ込める検査は `layers` 契約では行えず、`forbidden` 契約と session option `include_external_packages = true` が必要。実測で `correction_layer` に対する外部 forbidden 契約が期待どおり動作することを確認した。

## Research Log

### anomalib TimmFeatureExtractor の実装仕様

- **Context**: 要件 3・4 の中核。バックボーン切替と前処理条件の統一が、この 1 コンポーネントの引数でどこまで表現できるかを確定する必要があった。
- **Sources Consulted**: `.venv/lib/python3.12/site-packages/anomalib/models/components/feature_extractors/timm.py`（インストール済みソース、全 365 行）、および実機実行。
- **Findings**:
  - シグネチャは `(backbone, layers, pre_trained=True, requires_grad=False, output_fmt="NCHW", return_class_token=False, norm=True, dynamic_img_size=True)`。
  - 経路選択は `output_fmt == "NLC" or "vit" in backbone.lower()` の 1 行で決まる。この経路では `layers` は `"blocks.<int>"` 形式のみ受け付ける。
  - ViT 経路では `patch_size`・`num_prefix_tokens`・`out_dims`（= `num_features`）が属性として得られる。CNN 経路では `out_dims`（`feature_info.channels()`）と `reductions`（`feature_info.reduction()`）が得られる。
  - `norm` 引数は `forward_intermediates` にのみ渡る。CNN の `features_only` 経路では無視される。
  - 入力の高さ・幅は patch size の倍数でなければ `AssertionError`。
  - 実測形状: `vit_small_patch16_dinov3`、入力 `(2, 3, 512, 768)` で NLC は `(2, 1536, 384)`、NCHW は `(2, 384, 32, 48)`。
- **Implications**: パッチストライドと埋め込み次元は公開属性から取得できるため、ViT と CNN を 1 つのアダプタで扱える。一方 `norm` の非対称性は「前処理条件を全バックボーンに同一の解釈で適用する」（4.2）と衝突するため、設計側で明示的に拒否する必要がある。

### timm の DINOv3 対応と重みリビジョン

- **Context**: 既定バックボーンの実在性、埋め込み次元、重みの入手経路とリビジョン固定手段の確認。
- **Sources Consulted**: `timm.list_models("*dinov3*")`、`timm/models/eva.py`、`timm/models/_factory.py` の `parse_model_name`、`timm/models/_hub.py` の `hf_split`、`huggingface_hub` 1.23.0 の `HfApi.model_info` と `try_to_load_from_cache`。
- **Findings**:
  - DINOv3 は 12 モデル。埋め込み次元は small 384 / base 768 / large 1024 / huge+ 1280 / 7B 4096。すべて patch size 16、prefix トークン 5（CLS 1 + register 4）。
  - 実装クラスは `timm.models.eva.Eva` であり `VisionTransformer` ではない。位置エンコーディングは RoPE で `pos_embed is None`。タイルサイズ変更時の位置埋め込み補間が発生しない。
  - `get_intermediate_layers`（DINOv2 系の慣例）は存在しない。`forward_intermediates` を使う。
  - timm ミラー（`timm/vit_small_patch16_dinov3.lvd1689m`）は gated ではなく、未認証でダウンロードできる。Facebook 公式リポジトリは manual gate。
  - モデル名を `hf-hub:<repo>@<revision>` 形式にするとリビジョンを固定できる（`hf_split` が `@` で分割）。固定版とタグ指定版の重みが一致することを実測で確認。
  - `pretrained_cfg` から `input_size` / `mean` / `std` / `interpolation` / `hf_hub_id` / `tag` / `license` が取得できる。
  - `.eupe_lvd1689m` タグは非商用研究限定ライセンス。`lvd1689m` タグは `dinov3-license`。
- **Implications**: 重みリビジョンは「明示指定 → HF キャッシュのスナップショットパス → `None`」の順で解決でき、ネットワーク前提を持ち込まずに要件 6.4 を満たせる。既定バックボーンのタグ選択にはライセンス上の注意が必要（本 spec は選択肢を提供するのみで、採用判断は運用側）。

### 推論の決定性（要件 3.3）

- **Context**: 「同一画像・同一設定で同一のパッチ特徴を返す」を、GPU 実行を前提にどこまで保証できるかの確定。
- **Sources Consulted**: 実重み `vit_small_patch16_dinov3.lvd1689m` を用いた CPU / CUDA（torch 2.13.0+cu130）での実測。
- **Findings**:
  - 同一プロセス・同一形状の反復は、追加設定なしでビット単位一致（DINOv3 に dropout / drop-path がない）。
  - `inference_mode` / `no_grad` / 通常実行の 3 者は数値的に完全一致。
  - バッチ内要素数が変わると出力が変わる。CUDA 既定で最大差 5e-3、決定性フラグを全部立てても 4.3e-6、float64 でも 8.7e-15 残る。GEMM のリダクション順序に由来し、決定性 API では解消できない。
  - バッチサイズを固定すると、別プロセス実行でもハッシュが一致する。
  - CPU と GPU の結果は一致しない（最大差 1.45e-4）。
  - 充填値の内容は保持行に影響しない。CPU 上の小規模モデル（Conv + BatchNorm + LayerNorm、`eval` + `inference_mode`）で、実 5 枚 + 充填 3 枚のバッチの充填内容を 0 と乱数で入れ替えても保持 5 行がビット単位で一致した。`eval` 実行では BatchNorm が running statistics を使い、LayerNorm がトークン内で閉じるため、標本間で統計が混ざらない。
- **Implications**: 再現性は「固定バッチサイズ + `eval` + `inference_mode` + 同一デバイス」で成立する。端数バッチのパディングが必須であり、`tile_batch_size` と `device` は出力に記録すべき条件になる。充填値は `0.0` で足り、保持行の数値にも「有限値のみ」の事後条件にも影響しない。デバイス間の一致は保証できないため、設計の制約として明示する。

### anomalib のデータ読み込み経路

- **Context**: 要件 1.4（ネイティブ解像度の保持）と 1.5（型の閉じ込め）の実現方法の確定。
- **Sources Consulted**: `anomalib/data/datamodules/image/{visa,folder}.py`、`anomalib/data/datasets/base/image.py`、`anomalib/data/dataclasses/generic.py`、`anomalib/models/components/base/anomalib_module.py`、および合成データセットでの実測。
- **Findings**:
  - `Visa` / `Folder` に `image_size` や `transform` 引数は存在しない。リサイズ責務はモデル側 `PreProcessor` にある。
  - `Dataset.__getitem__` は `ImageItem` を返し、`image` は `tv_tensors.Image` の float32 `[0,1]`、`gt_label` は bool スカラー、`gt_mask` は `tv_tensors.Mask`。
  - DataModule 単体ではリサイズが一切かからないことを実測（1200x800 と 1000x900 がそのまま返る）。
  - `ImageBatch.collate` は形状混在時、`argmax` で「最大の辺長を持つ 1 枚」の `(H, W)` を選び、全件をその形状へ `resize` する。パディングではない。256x256 と 512x512 と 300x900 を混ぜると全件が 300x900 になり、アスペクト比が壊れる。
  - `setup()` を呼ぶまで `train_data` / `test_data` 属性は存在しない。
  - VisA は SHA256 検証付きで自動ダウンロードされる。anomalib の docstring はライセンスを CC BY-NC-SA 4.0 と書いているが、`docs/visa-validation-gate.md` は配布元根拠で CC BY 4.0（商用可）としており、法務判断は配布元を根拠にする方針である。
- **Implications**: DataModule を「準備と分割」にだけ使い、DataLoader を使わず Dataset を直接反復する構成にすれば、collate の破壊的リサイズを構造的に回避でき、`batch_size=1` という運用上の約束に頼らずに済む。

### anomalib Tiler の採用可否

- **Context**: タイル化を自作するか既存実装を採用するかの判断。
- **Sources Consulted**: `anomalib/data/utils/tiler.py`（全 473 行）と実測。
- **Findings**:
  - `anomalib.data.utils.__all__` にも `anomalib.data` にも含まれない非公開 API。
  - `stride=None` は docstring と異なり `AttributeError` になる。既定値が `None` の `TilerConfigurationCallback` は有効化すると即座に落ちる。
  - `tile()` が `batch_size` / `input_h` / `resized_h` などをインスタンス属性へ書き込み、`untile()` がそれに依存する。可変サイズ画像を扱うと直前の呼び出しに暗黙依存する。
  - 端部はゼロパディング（右下）で埋める。
  - タイルが元画像のどこ由来かを返さない。
  - 全タイルを一括で返すためストリーミングできない。
- **Implications**: 本機能に必要な「タイル座標の保持」「固定バッチでの逐次投入」「パディングなしの被覆」をいずれも満たさない。自作する。

### 下流 spec が期待する契約

- **Context**: 出力契約が下流の想定と食い違わないことの確認。
- **Sources Consulted**: `.kiro/specs/patch-feature-store/brief.md`、`.kiro/specs/primary-anomaly-detection/brief.md`、`.kiro/specs/evaluation-framework/brief.md`、`.kiro/specs/promptable-correction-layer/design.md`、`docs/normal-only-validation-plan.md`、`docs/visa-validation-gate.md`、`.kiro/steering/roadmap.md`。
- **Findings**:
  - 補正レイヤの確定契約は `roi_embedding: np.ndarray`（shape `(dim,)`、有限値、L2 ノルム > 0）。L2 正規化は照会側の `PrototypeStore` が所有する。
  - 補正レイヤのドメイン軸は `unit_of_work` を含む 4 軸。本 spec の要件は 3 軸（工程・材料・装置）。
  - `evaluation-framework` は「バックボーンごとにパッチグリッドと埋め込み次元が異なる」ため、各結果行に抽出器同一性メタの添付を要求する。
  - `primary-anomaly-detection` はヒートマップ再構成のためパッチ位置情報に依存する。データセット読み込みは本 spec の所有と明記されている。
  - `normal-only-validation-plan` は、グループキー（ウェハ ID・ロット ID・撮像日）のメタデータ保持を本 spec の所有としている。
- **Implications**: 埋め込みは `numpy` float32 で公開し、L2 正規化は行わない。ドメイン軸は要件どおり 3 軸に留め、4 軸への変換は境界外として明示する。位置情報は元画像座標で持たせる。

### 既存コードベースの規約

- **Context**: 2 つ目のパッケージが既存の層パターン・型スタイル・テスト規約に一致する必要がある。
- **Sources Consulted**: `src/correction_layer/**`、`tests/**`、`pyproject.toml`、`mise.toml`、`.github/workflows/python-ci.yml`、import-linter 2.13 の `application/use_cases.py`。
- **Findings**:
  - 層は `model`（型・Protocol）→ `boundary` / `decision` → `engine`。サブパッケージの `__init__.py` は空、公開面はルートの `__all__` のみ。
  - 外部由来の値は pydantic（`extra="forbid"`）、内部の値オブジェクトは frozen dataclass、閉じた語彙は `StrEnum`、差し替え口は `Protocol`（`@runtime_checkable` なし、実装は継承しない）。
  - 重い依存は `import faiss as _faiss` のように boundary 内に閉じ、内部 Protocol で型を隠す。
  - 例外は独自クラスを濫造せず `ValueError` 中心。構造化情報が必要な 1 箇所だけ独自例外（`DomainValidationError`）。メッセージは英語・小文字始まり・`!r` で実測値併記。
  - Python コードに docstring とコメントを書かない。テストは `test_should_*` 命名、`@pytest.fixture` を使わず `conftest.py` のプレーン関数を import。hypothesis は `@st.composite` + `@settings(max_examples=80)`。
  - `[tool.importlinter]` は `root_package`（単数形）。import-linter 2.13 は単数形を `root_packages` へ正規化し、複数形がある場合は単数形を破棄する。複数パッケージ検査には複数形への書き換えが必要。
  - 既存 4 契約はすべて `layers` / `independence` であり、外部パッケージの import を検査する契約はない。`forbidden` 契約で外部パッケージを指定するには session option の `include_external_packages` が必要で、無い場合は `_check_external_forbidden_modules` が `ValueError` を送出する（`importlinter/contracts/forbidden.py:220-234`）。TOML の真偽値は reader が `"True"` へ正規化するため `include_external_packages = true` で有効になる（`importlinter/adapters/user_options.py:105-108`）。
  - `forbidden` 契約は間接 import も検査する一方、グラフに存在しない forbidden module は検査対象から除外されるだけで失敗にならない（`forbidden.py:99-103`。存在検査は `source_modules` にのみ適用される）。実測でも `correction_layer.model` を source、`torch` / `timm` / `anomalib` を forbidden とした契約が KEPT になり、`faiss`（グラフに存在）に対しては実際に連鎖探索が走ることを確認した。
  - `mise.toml` に Python の lint / test タスクは存在しない。CI が `ruff` → `lint-imports` → `pytest` を実行する唯一の経路。
- **Implications**: 新規パッケージは同じ層パターンで作り、`pyproject.toml` の import-linter 設定を複数パッケージ対応へ変更する。それ以外の設定ファイル変更は不要。

## Architecture Pattern Evaluation

- **レイヤード + ポート注入（採用）** — 既存 `correction_layer` と同じ層構成。規約と import-linter 契約が既にあり、
  層違反を CI で検出できる。層をまたぐ変更でファイル数が増える点は許容する。
- **Vertical Slice（不採用）** — 機能単位でファイルをまとめる案。機能追加は局所化するが、既存 1 パッケージと構成が
  不整合になり、`.kiro/steering/structure.md` の層パターン指針に反する。
- **anomalib モデルとして実装（不採用）** — `AnomalibModule` を継承して Lightning に載せる案。学習・推論の枠組みを
  流用できるが、`PreProcessor` の既定リサイズと `ImageBatch.collate` に縛られ、ネイティブ解像度保持とタイル化の
  要件と衝突する。

## Design Decisions

### Decision: タイル端部を原点クランプで被覆する

- **Context**: 要件 2.2 は端部を欠落させない被覆を求める。割り切れない寸法の扱い方に複数の選択肢がある。
- **Alternatives Considered**:
  1. ゼロパディング（anomalib `Tiler` と同じ）— 端部タイルを規定サイズまで 0 で埋める。
  2. 原点クランプ — 最終タイルの原点を `size - tile_size` にし、直前のタイルと余分に重ねる。
  3. 端部タイルのみサイズを縮める — ViT の入力制約（patch size の倍数）を破るため検討から除外。
- **Selected Approach**: 原点クランプ。
- **Rationale**: パディング画素は実在しない内容であり、そこから生成されたパッチ特徴が正常メモリバンクに混入すると、下流の距離分布に人工的な偏りを持ち込む。クランプなら全パッチが実画素に対応する。
- **Trade-offs**: 端部で重なりが設定値より大きくなり、同一領域のパッチが重複する。重複の排除は下流の責務として境界外に置いた。
- **Follow-up**: 画像寸法がタイルサイズ未満の場合は被覆規則が定義できないため `ValueError` で拒否する。実データでこの条件が発生しないことを入力アダプタ側で確認する。

### Decision: 固定バッチサイズで推論し、端数をパディングする

- **Context**: 要件 3.3 の再現性。CUDA ではバッチ内要素数によって出力がビット単位で変わることを実測で確認した。
- **Alternatives Considered**:
  1. バッチサイズ 1 に固定 — 再現性は得られるがスループットが著しく落ちる。
  2. 可変バッチのまま許容し、再現性を「おおむね一致」に緩める — 要件 3.3 を満たさない。
  3. 固定バッチサイズ + 端数パディング + 余剰破棄。
- **Selected Approach**: 3。
- **Rationale**: 実測で、バッチサイズを固定すると別プロセス実行でもハッシュが一致した。スループットを犠牲にせずに要件を満たせる。
- **Trade-offs**: 端数分の無駄な計算が生じる。`tile_batch_size` が出力の同一性に影響する条件になるため記録が必要になる。
- **Follow-up**: `tile_batch_size` と `device` を `ExtractionRuntimeConfig` にまとめ、`ExtractionConditions.runtime` として記録する。デバイスをまたぐ一致は保証しないことを設計に明記する。

### Decision: DataLoader を使わず anomalib の Dataset を直接反復する

- **Context**: 要件 1.4（暗黙のリサイズなし）。`ImageBatch.collate` が形状混在時にアスペクト比を壊すリサイズを行う。
- **Alternatives Considered**:
  1. `batch_size=1` の DataLoader を使う — 運用上の約束に依存し、設定ミスで壊れる。
  2. `external_collate_fn` を差し替える — anomalib の内部拡張点に依存する。
  3. DataModule を `prepare_data` / `setup` にだけ使い、Dataset を直接反復する。
- **Selected Approach**: 3。
- **Rationale**: collate を構造的に経由しないため、設定ミスによる暗黙リサイズが起こり得ない。ダウンロードと split ロジックは DataModule から得られる。
- **Trade-offs**: DataLoader のワーカー並列を使えない。1 画像単位の処理が主であり、律速はタイル推論側なので影響は小さい。
- **Follow-up**: モデル側 `PreProcessor` を一切構成しないこと（構成すると `_update_augmentations` 経由で Resize が注入される）。

### Decision: タイル化を自作し、anomalib `Tiler` を採用しない

- **Context**: Build vs Adopt。既存実装があるならまず採用を検討する。
- **Alternatives Considered**: `anomalib.data.utils.tiler.Tiler` の採用。
- **Selected Approach**: `geometry/tiling.py` に自作する。
- **Rationale**: `Tiler` は非公開 API で、タイル座標を返さず（要件 2.3・5.1 を満たさない）、ゼロパディングで端部を埋め（上記の決定と衝突）、`tile()` の呼び出し結果をインスタンス状態に持つため可変サイズ画像で事故が起きやすい。`stride=None` で例外になる既知の不具合もある。
- **Trade-offs**: 重なり領域の平均化と `untile` 相当のロジックを失うが、本 spec は再構成を必要としない（ヒートマップ再構成は下流の責務）。
- **Follow-up**: 実装は純関数に閉じ、hypothesis で全域被覆を検証する。

### Decision: 抽出は単一層に限定する

- **Context**: PatchCore 系は複数層の特徴を連結するのが一般的だが、要件は層の選択に言及していない。
- **Alternatives Considered**:
  1. 複数層を連結する — CNN では層ごとに空間解像度が異なるため共通グリッドへの補間が必要になり、パッチ位置の意味が層ごとにずれる。
  2. 単一層に限定し、層名を設定と同一性メタに含める。
- **Selected Approach**: 2。
- **Rationale**: 現在の要件が求めるのは「固定次元の特徴ベクトル列」と「条件の記録」であり、多層融合は要求に含まれない。単一層ならパッチストライドが 1 つに定まり、位置写像が自明になる。
- **Trade-offs**: 多層融合が有効だと判明した場合、`feature_layer` を複数値へ拡張する契約変更が必要になる。これは再検証トリガーとして記録する。

### Decision: 前処理条件は「要求」と「解決済み」で型を分ける

- **Context**: 要件 4.3 は未指定時に既定を適用し、適用した条件を出力へ記録することを求める。
- **Selected Approach**: `PreprocessingConfig`（各項目 optional）を境界で解決し、`ResolvedPreprocessing`（全項目具体値）を `ExtractorIdentity` に格納する。
- **Rationale**: 既存パッケージの `DomainAxes` / `ConcreteDomainAxes` と同じ「定義では未指定可・実行時は具体値のみ」の型分離であり、下位層が設定ソースを再解決する構造を防げる。
- **Trade-offs**: 型が 1 つ増える。記録の正確さと引き換えに許容する。

### Decision: 重い依存の封じ込めを import-linter の forbidden 契約で検査する

- **Context**: 本設計の中心的な不変条件は「torch / timm / anomalib を `boundary` に閉じる」ことである。これを宣言だけに留めると、`geometry` や `engine` への import 混入が CI をすり抜ける。
- **Alternatives Considered**:
  1. `layers` 契約だけで担保する — 内部モジュール間の向きしか見ないため、`geometry/tiling.py` の `import torch` を検出できない。
  2. 公開面のテスト（戻り値の型と `__all__` に anomalib / torch 名が出ないこと）だけで担保する — 型の露出は検出できるが、内部での import 混入は検出できない。
  3. `forbidden` 契約で `model` / `geometry` / `engine` から `torch` / `timm` / `anomalib` への import を禁止する。
- **Selected Approach**: 3（1 と 2 は併用する）。
- **Rationale**: `forbidden` 契約は間接 import も検査するため、`boundary` を経由した到達も破断として報告される。CI は既に `lint-imports` を実行しており、追加のツールも実行経路も要らない。
- **Trade-offs**: `include_external_packages = true` により外部パッケージを含めたグラフ構築が必要になり、検査時間が増える。実測では既存 32 ファイルの検査が 0.3 秒台で完了しており、許容範囲である。
- **Follow-up**: `boundary` 内（`timm_backbone` / `anomalib_source` → `backbone_identity`）と `model` 内（`ports` → `features` → `config` → `types` / `layout`）の一方向も `layers` 契約として明示する。既存 `correction_layer` に相当契約があり、新規側だけ欠落させない。

### Decision: 抽出器の同一性と実行条件を別の設定型に分ける

- **Context**: 出力側では `ExtractorIdentity`（同一性）と `ExtractionConditions`（条件）を分けている。入力側の `BackboneConfig` に `tile_batch_size` と `device` を同居させると、同じ抽出器をデバイス違いで走らせる構成で `BackboneConfig` が 2 つ必要になり、要件 4.1 の「設定の変更だけで切り替える」が実行条件の再指定を伴う。
- **Alternatives Considered**:
  1. `BackboneConfig` に実行条件を残す — 型は 1 つで済むが、1 フィールド群が 2 つの意味を持ち、切替の単位と実行の単位が分離できない。
  2. 実行条件を `TimmPatchExtractor.load` の個別引数にする — 型は増えないが、`ExtractionConditions` へ記録する際に呼び出し側が値を組み直す必要があり、記録値と適用値が食い違う余地が残る。
  3. `ExtractionRuntimeConfig`（`tile_batch_size`・`device`）へ分離し、`load` の第 3 引数として受け取り、そのまま `runtime` プロパティで公開して `ExtractionConditions.runtime` に記録する。
- **Selected Approach**: 3。
- **Rationale**: 「どの抽出器か」と「どう実行したか」が別の型になり、`ExtractorIdentity` / `ExtractionConditions` の出力側の分離と対称になる。記録する値は適用した設定オブジェクトそのものであり、組み直しが発生しない。
- **Trade-offs**: 設定型が 1 つ増え、port のプロパティが `tile_batch_size` / `device` の 2 つから `runtime` の 1 つへ変わる。前処理条件の「要求と解決済みを分ける」決定と同じく、型の追加は記録の正確さと引き換えに許容する。

### Decision: CNN レイアウトと backbone final norm の組み合わせを拒否する

- **Context**: 要件 4.2 は前処理条件を全バックボーンに同一の解釈で適用することを求める。`TimmFeatureExtractor` の `norm` 引数は CNN 経路で無視される。
- **Alternatives Considered**:
  1. 黙って無視する — 条件が揃っていないのに揃っているように見え、比較実験の前提を壊す。
  2. CNN 側に独自の正規化を実装する — バックボーン固有の学習済み最終 norm とは別物であり、「同一の解釈」にならない。
  3. 構築時に `ValueError` で拒否する。
- **Selected Approach**: 3。
- **Rationale**: 条件が適用できないことを実行前に明示できる。比較実験の設計は `evaluation-framework` の責務であり、本 spec は不整合を検出して伝えるのが正しい振る舞いである。

## Risks & Mitigations

- **`opencv-python-headless` の破損で `anomalib.data` が import できない** — 実装タスクの前提条件として再インストールを行う。解消しない限り入力アダプタのテストは実行できない。
- **1 画像あたりのパッチ特徴がメモリを圧迫する（8000x8000、タイル 512 で約 400 MB）** — `PatchFeatureSet` を画像単位で完結させ、逐次処理を可能にする。永続化とストリーミングは `patch-feature-store` の責務として境界外に置く。
- **デバイス・ドライバの差で数値が変わる** — 再現性の保証範囲を「同一デバイス・同一ランタイム」と設計に明記し、`device` を条件として記録する。
- **DINOv3 の重みライセンス（`dinov3-license`、タグにより非商用研究限定）** — 本 spec はバックボーン名を設定として受け取るのみで、採用可否の判断は運用・法務側に残る。既定値の選択時に `lvd1689m` タグと `.eupe_lvd1689m` タグを区別する。
- **`TimmFeatureExtractor` の経路選択がバックボーン名の文字列一致（`"vit" in name`）に依存する** — `feature_layout` を設定として明示し、返却テンソルの次元数で整合を検証する。
- **import-linter の設定変更漏れで新パッケージが検査対象外になる** — `root_packages` への書き換えを実装タスクに含め、契約違反が CI で検出されることを確認する。
- **`anomalib` の型が公開面に漏れる** — 公開 API に anomalib / torch の型が現れないことをテストで検証する（既存の FAISS 非露出テストと同じ方式）。加えて `forbidden` 契約で `model` / `geometry` / `engine` からの import 自体を禁止し、型の露出と import の混入を別々の手段で検出する。

## References

- `.venv/lib/python3.12/site-packages/anomalib/models/components/feature_extractors/timm.py` — `TimmFeatureExtractor` の実装（経路選択、`norm` の適用範囲、公開属性）
- `.venv/lib/python3.12/site-packages/anomalib/data/dataclasses/generic.py` — `ImageBatch.collate` の形状混在時の挙動
- `.venv/lib/python3.12/site-packages/anomalib/data/utils/tiler.py` — `Tiler` の仕様と `stride=None` の不具合
- `.venv/lib/python3.12/site-packages/timm/models/eva.py` — DINOv3 の実装クラスと `forward_intermediates`
- `.venv/lib/python3.12/site-packages/timm/models/_hub.py` — `hf-hub:<repo>@<revision>` のリビジョン解決
- `.venv/lib/python3.12/site-packages/timm/models/_builder.py` — `custom_load` タグの重み取得経路（HF hub 非対応の警告）
- `.venv/lib/python3.12/site-packages/importlinter/contracts/forbidden.py` — 外部 forbidden module の前提条件とグラフ不在時の扱い
- `.venv/lib/python3.12/site-packages/importlinter/adapters/user_options.py` — TOML 真偽値の正規化
- `docs/researches.md` §3.1、§3.2、§3.3、§4、§5、§6、§10 — 重み固定方針、パッチ数のオーダー、比較用バックボーン、layer norm の条件統一
- `docs/visa-validation-gate.md` — 入力アダプタの責務、バックボーン比較で揃える条件、collate の罠、ライセンス
- `docs/normal-only-validation-plan.md` — 由来キーによるグループ分割とリーク防止、本 spec が所有するメタデータ
- `.kiro/steering/structure.md` / `tech.md` / `roadmap.md` — 層パターン、採用ライブラリ、共有 seam
- `.kiro/specs/promptable-correction-layer/design.md` — `roi_embedding` の数値契約と正規化の所有
