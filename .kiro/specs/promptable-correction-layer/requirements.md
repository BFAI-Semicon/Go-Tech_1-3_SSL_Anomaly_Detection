# Requirements Document

## Introduction

一次検出の異常スコアだけでは、現場が許容する既知パターンの過検出（False Positive）を抑制できない。本機能（補正レイヤ、promptable-correction-layer）は、欠陥候補 ROI の埋め込みとプロトタイプ記憶の近傍照合、および HITL 由来の構造化 JSON の適用条件を推論時に統合し、一次判定（Positive=異常候補／Negative=正常）を再構成して最終判定（NG／許容／要確認）を返す（researches.md §3.1、§3.2-5、§3.2-6、§5）。

判定スキーマ（補正レコードの action／method／match）と競合解決の優先順位チェーンは `docs/structured-json-versioning/README.md` 配下の設計メモ（§6・§9、correction-layer.md）に従う。本 requirements のスコープは、ユーザー指示により `docs/incremental-development-plan.md` の Phase 0–3（判定ロジック本体）に限定する。Phase 0–3 は永続化を持たず、合成データのみで判定ロジックを固める段階である。

## Boundary Context

- **In scope**（Phase 0–3 相当）:
  - 合成データ（合成プロトタイプ集合と手書きのドメイン別補正定義）のみでの一連の判定処理の検証可能性（Phase 0）
  - ROI 埋め込みとプロトタイプの近傍照合、類似度閾値判定、補正レコード適用による最終判定の最小フロー（Phase 1）
  - 補正レコードの判定スキーマ全フィールドの解釈：4 action × 3 method＋null、match（prototype_ids／similarity_threshold の対、または類似度条件なし＝ドメイン軸のみで適用）、構造検証（フィールド有無・型・enum）による不正定義の拒否（Phase 2）
  - 複数ドメインの補正定義の合成（`any` ワイルドカードまで）と、優先順位チェーン（specificity → ReviewRequired 短絡 → safety → recency → element_id）による決定的な競合解決（Phase 3）
- **Out of scope**:
  - バージョン管理一式：版付き不変アーティファクト・マニフェスト・昇格・ロールバック・element_id 採番カウンタの永続化（Phase 4–6、設計メモ §2–§4・§7）
  - `priority.json` による明示的な優先順位上書き（Phase 6、設計メモ §9.1）
  - メモリバンク版互換ゲート、dangling `prototype_ids` の skip／remap、expiry（有効期限）切れプロトタイプの間引き連動（Phase 5、設計メモ §9 規則 2。brief の expiry 制約はこの段階で扱う）
  - オントロジー統合：CURIE 実在検証（検証 2 段目）・上位クラス階層マッチ・remap（Phase 7、設計メモ §5・§11）
  - 実パイプライン統合と比較実験の実行：補正方式の切替実験、条件ソース（ROI のみ／言語のみ／併用）の切替実験（Phase 8、researches.md §5 の実験対応）
  - プロトタイプの登録・coreset 管理（patch-feature-store が所有）、構造化 JSON の生成（llm-feedback-structuring が所有）、補正効果の定量評価（evaluation-framework が所有）
- **Adjacent expectations**:
  - 本番では、プロトタイプ近傍検索は patch-feature-store、適用条件の構造化 JSON は llm-feedback-structuring、一次判定（異常スコア・ROI 候補）は primary-anomaly-detection が提供する。本スコープではこれらをすべて合成データで代替し、データ契約（判定スキーマ）のみを設計メモに従って固定する。
  - 補正レコードのフィールド名・意味（element_id／action／method／params／match／recorded_at／attributed_to／source_ref）は設計メモ §6 を共有語彙として llm-feedback-structuring と共有する。

## Requirements

### Requirement 1: 合成データによる骨格検証

**Objective:** 開発者として、補正レイヤの一連の判定処理を合成データだけで動かして検証したい。それにより、上流コンポーネント（特徴抽出・特徴量ストア・一次検出・構造化）の完成を待たずに判定ロジックを固められる。

#### Acceptance Criteria (Requirement 1)

1. When 合成プロトタイプ集合とドメイン別補正定義のフィクスチャが読み込まれた, the 補正レイヤ shall 近傍検索と補正判定を実行可能な状態を構築する。
2. When ROI 埋め込みに対する近傍検索が要求された, the 補正レイヤ shall 最近傍プロトタイプの識別子と類似度を返す。
3. When 合成データ上で一次判定が要求された, the 補正レイヤ shall 近傍類似度スコアと固定閾値により一次判定（Positive／Negative）を導出する。
4. The 補正レイヤ shall 実計測データ・実 LLM 出力・外部オントロジー定義に依存せず、合成データのみで一連の判定処理を完了する。

### Requirement 2: 近傍照合と補正レコードの適用判定

**Objective:** 品質管理者として、既知の許容パターンに近い過検出が適用条件に基づいて自動補正されることを望む。それにより、False Positive の確認負荷を削減できる。

#### Acceptance Criteria (Requirement 2)

1. When 一次判定を伴うパッチが入力された, the 補正レイヤ shall 当該パッチの ROI 埋め込みと登録済みプロトタイプとの類似度照合を実行する。
2. When match の prototype_ids に含まれるプロトタイプとの類似度が similarity_threshold の条件を満たした, the 補正レイヤ shall 当該補正レコードを適用対象と判定する。
3. If プロトタイプとの類似度が similarity_threshold の条件に達しない, then the 補正レイヤ shall 当該補正レコードを適用対象から除外する。
4. If 適用対象の補正レコードが存在しない, then the 補正レイヤ shall 一次判定をそのまま最終判定として返す。
5. The 補正レイヤ shall match の similarity_threshold を近傍検索と同一の類似度尺度で解釈する。
6. Where 補正レコードの match が類似度条件（prototype_ids／similarity_threshold）を持たない, the 補正レイヤ shall ドメイン軸の条件のみで当該レコードの適用可否を判定する。

### Requirement 3: 補正操作（action）の解釈

**Objective:** 運用担当者として、HITL 由来の補正指示の 4 種類の操作（過検出抑制・見逃し救済・現状維持・人間確認）が意図どおり一次判定へ作用することを望む。それにより、現場の判断を判定へ正確に反映できる。

#### Acceptance Criteria (Requirement 3)

1. When 一次判定 Positive の入力に LabelOverride 方式の OverrideNegative レコードが適用された, the 補正レイヤ shall 二次判定を Negative（許容）にする（ScoreReweight／ThresholdAdapt 方式の二次判定は要件 4.2／4.3 の再計算結果に従う）。
2. When 一次判定 Negative の入力に LabelOverride 方式の OverridePositive レコードが適用された, the 補正レイヤ shall 二次判定を Positive（NG）にする（ScoreReweight／ThresholdAdapt 方式の二次判定は要件 4.2／4.3 の再計算結果に従う）。
3. When KeepPrimary レコードが適用された, the 補正レイヤ shall 一次判定を変更せずに保持する。
4. When ReviewRequired レコードが適用された, the 補正レイヤ shall 最終判定を保留（要確認）とし、人間の確認対象として出力する。

### Requirement 4: 補正方式（method）の解釈

**Objective:** 研究開発者として、3 つの補正方式（ラベル上書き・スコア再重み付け・閾値適応）それぞれの効果を検証できることを望む。それにより、補正方式間の比較検証（researches.md §5）の基盤が得られる。

#### Acceptance Criteria (Requirement 4)

1. When LabelOverride 方式のレコードが適用された, the 補正レイヤ shall スコアと閾値を再計算せずに判定ラベルを action の方向へ直接上書きする。
2. When ScoreReweight 方式のレコードが適用された, the 補正レイヤ shall params の重み付けパラメータで異常スコアを再構成し、再構成後のスコアと閾値の比較で二次判定を導出する。
3. When ThresholdAdapt 方式のレコードが適用された, the 補正レイヤ shall params の閾値適応パラメータで判定閾値を適応させ、適応後の閾値との比較で二次判定を導出する。
4. Where action が KeepPrimary または ReviewRequired である, the 補正レイヤ shall 当該レコードの method を null として解釈する。

### Requirement 5: 補正レコードの構造検証

**Objective:** 運用担当者として、不正な補正定義が判定に使われる前に拒否されることを望む。それにより、誤った補正の混入を防げる。

#### Acceptance Criteria (Requirement 5)

1. When ドメイン別補正定義が読み込まれた, the 補正レイヤ shall 各レコードの element_id・action・method・params・match・recorded_at・attributed_to・source_ref の全フィールドを解釈する。
2. If 補正定義に必須フィールドの欠落・型不一致・定義外の action もしくは method の値が含まれる, then the 補正レイヤ shall 当該定義を拒否し、拒否理由を報告する。
3. If action と method の組合せが規約に違反する（KeepPrimary／ReviewRequired に null 以外の method、OverrideNegative／OverridePositive に null の method）, then the 補正レイヤ shall 当該定義を拒否する。
4. Where 補正レコードに複数の適用条件（ドメイン軸・match の類似度条件）が含まれる, the 補正レイヤ shall 指定されたすべての条件を満たす入力に対してのみ当該レコードを適用する。
5. If match に prototype_ids と similarity_threshold の一方だけが指定されている, then the 補正レイヤ shall 当該定義を拒否する。
6. If ScoreReweight もしくは ThresholdAdapt の params の値が action の方向と矛盾する（OverrideNegative に weight ≥ 1 もしくは threshold_delta ≤ 0、OverridePositive に weight ≤ 1 もしくは threshold_delta ≥ 0）, then the 補正レイヤ shall 当該定義を拒否する。

### Requirement 6: 複数ドメイン定義の合成と適用範囲解決

**Objective:** 運用担当者として、複数ドメイン（工程・材料・装置・作業単位）の補正定義を同時に有効化し、具体ドメインと広域ドメインのルールを併用したい。それにより、個別条件と工程全体の運用ルールを両立できる。

#### Acceptance Criteria (Requirement 6)

1. When 複数ドメインの補正定義が読み込まれた, the 補正レイヤ shall 全ドメインの有効レコードを合成して照合対象にする。
2. Where ドメイン軸の指定に `any` が含まれる, the 補正レイヤ shall 当該レコードを当該軸の任意の値を持つ入力へ適用可能な広域ルールとして解釈する。
3. When 同一入力に具体ドメインのレコードと広域ドメインのレコードが競合した, the 補正レイヤ shall より具体的な指定を持つレコードを優先する。
4. If 補正レコードがドメイン定義から削除されている, then the 補正レイヤ shall 当該レコードを有効集合に含めず、重なる広域ルールがあればそれへフォールバックする。

### Requirement 7: 競合解決の優先順位チェーン

**Objective:** 運用担当者として、複数の補正指示が同一入力に競合しても結果が一意に決まることを望む。それにより、判定の再現性と説明可能性を保てる。

#### Acceptance Criteria (Requirement 7)

1. When 異なる element_id の複数レコードが同一入力にマッチした, the 補正レイヤ shall specificity、ReviewRequired 短絡、safety、recency、element_id の順で構成される総順序により勝者を一意に決定する。
2. If specificity 同点の勝ち集合に ReviewRequired のレコードが含まれる, then the 補正レイヤ shall 以降の比較を打ち切り、最終判定を保留（要確認）にする。
3. If ReviewRequired で決着しない同一 specificity の競合が生じた, then the 補正レイヤ shall OverridePositive、KeepPrimary、OverrideNegative の順の安全側優先で勝者を決定する。
4. If safety でも競合が決着しない, then the 補正レイヤ shall recorded_at がより新しいレコードを優先する。
5. If recency でも競合が決着しない, then the 補正レイヤ shall element_id がより大きいレコードを優先する。
6. When 具体ドメインの KeepPrimary レコードと広域の上書き系レコードが競合した, the 補正レイヤ shall KeepPrimary を勝者として広域補正を遮蔽し、一次判定を最終判定にする。
7. The 補正レイヤ shall 同一の入力と同一の有効レコード集合に対して常に同一の最終判定を返す。

### Requirement 8: 最終判定の出力と補正の不変制約

**Objective:** 品質管理者として、パッチごとに NG／許容／要確認のいずれかの最終判定を受け取りたい。それにより、過検出の抑制と人間確認の振り分けを運用に組み込める。

#### Acceptance Criteria (Requirement 8)

1. When 補正判定が実行された, the 補正レイヤ shall 最終判定として NG、許容、要確認のいずれかを返す。
2. The 補正レイヤ shall モデル重みの更新を伴わない推論時の条件適用としてのみ補正を実行する。
