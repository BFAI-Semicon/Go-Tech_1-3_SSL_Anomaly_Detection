# 構造化 JSON バージョン管理・補正レイヤスキーマ設計メモ

Promptable Patch Retrieval パイプラインにおける、HITL 由来の運用スキーマ（構造化 JSON）と
メモリバンクのバージョン管理方針、および補正レイヤ（`promptable-correction-layer`）が消費する
判定スキーマの設計メモ。関連 spec は `llm-feedback-structuring` / `patch-feature-store` /
`promptable-correction-layer`（`.kiro/specs/`）。

## 1. 全体アーキテクチャ（コンテナ構成）

| コンテナ | 役割                                                                                  |
| -------- | ------------------------------------------------------------------------------------- |
| frontend | ROI 注釈・自然言語コメント入力・検出結果表示（UI のみ）                               |
| api      | HITL 入力受付、注釈の蓄積、バッチビルド起動、active バージョンの参照仲介              |
| worker   | ①稼働系推論（active バージョンで欠陥検出） ②HITL バッチ（次バージョンのビルド・検証） |

- 今回のプログラム本体は **worker** 上で動作する。
- 反映は **バッチ**（リアルタイムではない）。
- `promptable-correction-layer` は UI を持たない純粋な推論処理なので frontend とは分離し、worker に載せる。
- frontend との接点は UI ではなく、構造化 JSON と ROI/スコアの **データ契約**。

## 2. 稼働系と更新系の分離（バージョン昇格モデル）

Blue-Green 型のアーティファクト昇格モデルを採用する。

```text
[稼働バージョン Vn]  ← worker が読み取り専用で欠陥検出（メモリバンク + 構造化JSON をピン留め）
        │
        │ HITL（ROI注釈＋NL→LLM構造化→検証→監査ログ）で蓄積
        ▼
[候補バージョン Vn+1] ← 別ジョブでビルド（追記 / coreset再選択 / expiry間引き）
        │
        │ evaluation-framework で検証（escape/overkill 等）
        ▼
    昇格（active ポインタを原子的に切替）→ Vn+1 が新しい稼働系に
```

- **メモリバンクと構造化 JSON は 1 組（バージョンタプル）として原子的に昇格・ロールバックする。**
  補正レイヤは両方を同時に参照するため、片方だけ更新するとプロトタイプと適用条件がズレて誤補正になる。
- 稼働系は **不変バージョンを読み取り専用**で参照するのでロック競合が起きない。
- 昇格は active ポインタ（マニフェスト）の原子的な差し替えで行う。

## 3. バージョン管理方式：イベントソーシング（追記専用）

- **バージョン軸 = 追記ログの連番 `revision`。** `(ドメイン, revision)` で状態が一意に決まる。
- 変更・削除・再有効化はすべて「新しい `revision` のレコード追記」に還元される（一様な操作）。
- 履歴は不変（過去は書き換えない）。監査・再現性・ロールバックを非破壊で担保。
- **独立した 2 つのバージョン軸**が存在し、いずれも**レコード単位で自己記述**する（過去行は書き換えない）:
  - `revision`: ログ位置（＝内容の版、本節）
  - `ontology_version`: 自社の複合語彙版（`semicont` は git ref ピン＋`proj` は自社版。§5.1、読み取り時に remap）
- **自前の JSON 構造版（`*_schema_version`）は持たない。** 我々が変更タイミングを支配でき、
  変更頻度も低いため。ただし将来の破壊的変更に備え、次を規約とする:
  - **「`schema_version` フィールドが無い＝バージョン `1.0`」と解釈する。**
  - 破壊的なスキーマ変更を行う時点で初めて `schema_version` を導入する（既存行は書き換えず `1.0` 扱い）。
  - `meta.json` / `priority.json` / スナップショットは再生成・現行形式への書き直しが可能なため、
    構造版は不要（旧形式を保持する運用に変える場合のみ再検討）。

### 3.1 削除の表現：論理削除フラグではなく `NoOverride`

- 削除フラグ（tombstone）は持たない。
- 削除は「そのドメインの最新版に **`judgment: "NoOverride"`（一次判定を上書きしない）** を意味するレコードを追記」して表現する。
- 有効集合の解決は「各 `element_id` について最新 `revision` の `judgment` を適用」で一様。
- **「何もしない ≡ 削除」を厳密にするため、コンパクション時に「最新が `NoOverride` の要素」は有効スナップショットから物理的に除外する**（ログには履歴として残す）。これにより他要素との優先順位解決で真の削除と挙動が一致する。
- 意味は「今後の廃止（deprecation）」であり「過去の撤回（retraction）」ではない。誤登録の由来
  （`retired` 等）は独立監査ログに記録する（レコード本体には持たない。履歴は改変しない）。
- 再有効化は、実 `judgment` を持つ新 `revision` を追記すれば可能。

## 4. ドメイン単位のバージョン管理

- **1 ドメイン = 1 追記ログ（別ファイル）。** `revision` はドメインごとに独立採番。
- 昇格・ロールバックはドメイン単位（他ドメインに波及しない）。
- 稼働系は担当ドメインのログだけをロード（ドメイン分割ロード）。

### 4.1 ドメインキーと 4 桁スラッグ

- ドメインキー = `(process, material, equipment, unit_of_work)` の複合キー。
- ディレクトリ名（スラッグ）は **固定順序 4 桁**：`process__material__equipment__unit`。
  - `site`（Facilities）はキーに含めない（4 桁に確定）。
  - `Measurements` はキーではなく `match.scope` の条件に使う。
- 指定しない軸は **明示トークン `any`** で埋める（空欄を `_` で埋める方式は非推奨：判読・パースが脆い）。
- ディレクトリ名は人間可読ラベル。**正キーはタプルから初回生成する `domain_id`（ハッシュ）。**
- **`domain_id` は初回採番後は不変の不透明キーとして凍結する。** CURIE タプルは記述的属性に過ぎず、
  オントロジー改名等で CURIE が変わっても `domain_id` は再計算しない（既存ログとの連続性を保つ。§5.1）。

### 4.2 「工程全体」の表現（2 通り）

1. **特定工程を材料・装置問わず適用** → `process` は固定、他軸を `any`。
   例: `drie__any__any__wafer/`（CURIE 側は `material: "*"`, `equipment: "*"`）
2. **工程ファミリ全体に適用** → ワイルドカードではなく **上位クラス CURIE** を使う。
   例: `dryetch__any__any__wafer/`（`process: "semicont:DryEtchProcess"`）

稼働系は「装置指定 → 材料指定 → 工程全体（`any`）→ 上位工程クラス」の順（specificity 優先）に
合成して適用する。これは §9.1 の優先順位チェーンの第 1 段（specificity）と同一の考え方。

## 5. SemiKong オントロジー整合

参照方式は **CURIE 参照（軽量）**。採用するのは **5 パースペクティブ**：
Process / Materials / Equipment / Measurements / Units-of-work。

| フィールド                 | SemiKong モジュール               | 値の例（CURIE）                       |
| -------------------------- | --------------------------------- | ------------------------------------- |
| `domain.process`           | `05-foundry-idm/.../etching`      | `semicont:DeepReactiveIonEtchProcess` |
| `domain.material`          | `08-materials`                    | `semicont:SiliconNitride`             |
| `domain.equipment`         | `07-wfe/etch`                     | `semicont:PlasmaEtchSystem`           |
| `domain.unit_of_work`      | Units of work                     | `semicont:Wafer`                      |
| `match.scope.measurement`  | Measurements and quality          | `semicont:CriticalDimension`          |
| `match.scope.defect_class` | quality（語彙が薄いため自社拡張） | `proj:PolymerResidue`                 |

- 値を自由文字列でなく CURIE 参照にすることで、統制語彙からの補完・表記ゆれ防止・機械検証が得られる。
- レコードで使う語彙は **`semicont`（SemiKong・上流）と `proj`（自社拡張）の 2 つ**で、更新契機が独立する
  （SemiKong 採用替え／自社の欠陥語彙編集）。この 2 つを束ねた**自社の複合語彙バージョン**を
  **レコード単位の `ontology_version`** に記録する（§6.3）。これが唯一の権威であり、`element_id` ごとに
  異なる `ontology_version` が混在しうる。
- **SemiKong は semver を持たない**（配布は日付タグ＝例 `260313-stable`／`stable` ブランチ）。よって
  `semicont` は**版番号ではなく git ref（タグ/コミット）でピン留め**し、版番号は自社側だけが採番する。
- **オントロジーの定義（prefixes / remap 表 / 各コンポーネントの source・ref）は版をキーにした
  「グローバルレジストリ」に一元管理する**（§5.2）。`meta.json` にはオントロジー情報を持たせない。
- **なぜ `meta.json` に単一 `ontology` を置かないか**：レコードごとに `ontology_version` が自己記述されるため、
  ドメイン単位の単一版は「1 ドメイン＝1 版」という誤った含意を生み、稼働／候補の同期も抱える冗長情報になる。
- 欠陥タイプ分類は SemiKong では手薄なため、自社名前空間 `proj:` で拡張する。
- ライセンス/法務確認が必要（SemiKong はコードが MIT だが、オントロジー資産は上流ライセンス/条件を
  持ちうる）。正確な IRI は実際の `ontology.ttl` から取り込む。

### 5.1 オントロジーのバージョンアップ対応

語彙が更新（SemiKong の採用替え、または自社 `proj` の編集）されても、**log.jsonl は不変**であり、
各行の CURIE は「当時の `ontology_version`」に対して書かれている。`ontology_version` はレコード単位で
自己記述されるので、版を「上げる」対象の単一フィールドは存在しない（版キーのレジストリに版を追加する）。
複合語彙バージョンは **`semicont`（git ref）と `proj`（自社版）のどちらが変わっても上がる**。以下の方針で扱う。

- **`ontology_version` はレコード単位で自己記述**（§6.3）。過去の判定再現には当時の語彙版が必要。
- **版の定義（prefixes / remap 表 / コンポーネント）はグローバルレジストリに版キーで追加する**（§5.2）。
  remap 表はドメインごとに散らばらず、`1.2.0 → 1.3.0` の 1 箇所で管理する（`semicont` 由来・`proj` 由来を同枠で）。
- 必要なら影響ルールを新 CURIE で再表明（新 `revision`）し、新規レコードには新 `ontology_version` を刻む。
- **`domain_id` は凍結**（§4.1）。CURIE 改名でドメイン同一性・ログ連続性を失わない。
- **有効スナップショットは目標オントロジー版に正規化して再生成**（派生物なのでレジストリの remap を適用して
  作り直してよい）。生ログは旧 CURIE のまま保全する。
- **昇格は評価ゲートを通す**。オントロジー変更の種類で判定への影響が異なるため、`evaluation-framework`
  で escape/overkill の回帰を確認してから promote する。ドメイン単位で段階的に上げてよい。

オントロジー変更の種類と影響:

| 変更種別                     | log.jsonl への影響               | 判定への影響                                 |
| ---------------------------- | -------------------------------- | -------------------------------------------- |
| 追加のみ（新クラス）         | 既存 CURIE 有効、影響なし        | なし                                         |
| 改名・移動（IRI 変更）       | 旧 CURIE が dangling、remap 必須 | remap 適用＋`domain_id` 凍結なら不変         |
| 非推奨化（deprecated）       | 解決可だが要移行                 | 警告レベル                                   |
| 同一 IRI の意味変更          | 検証は通るが意味が変わる         | **黙って変わりうる（要レビュー）**           |
| 分類階層の再編（subClassOf） | CURIE は有効                     | **階層マッチの合成が変わり判定が変わりうる** |

`ontology_version` の差の現れ方は変更種別で異なる。**改名・移動**では CURIE 型フィールドの**値そのもの**
が変わる（例 `semicont:PlasmaEtchSystem` → `semicont:PlasmaEtchTool`、remap で吸収）。一方**同一 IRI の
意味変更・階層再編**では**値は同一のまま**で、差は `ontology_version` にしか現れない（値だけでは区別
できないため per-record の `ontology_version` が要る）。いずれもフィールドの**キー・構造は不変**
（構造の版は `schema_version` の管轄。§3）。

### 5.2 オントロジーレジストリ（グローバル・版キー）

オントロジーの定義はドメインごとに持たず、プロジェクト共通の 1 ファイルに**版をキー**にして集約する。
版キーは**自社の複合語彙バージョン**で、各エントリが `semicont`（SemiKong の git ref ピン）と `proj`
（自社版）の 2 コンポーネントを持つ。各レコードの `ontology_version` がこのレジストリの該当版
（`components` / `prefixes` / `remap_from`）を引く。

```json
{
  "versions": {
    "1.2.0": {
      "components": {
        "semicont": { "source": "github.com/aitomatic/semikong", "ref": "260313-stable" },
        "proj":     { "version": "2026-06-01", "source": "self@commit-9f2c" }
      },
      "prefixes": {
        "semicont": "https://w3id.org/semicont/ontology#",
        "proj": "https://example.com/go-tech/defect#"
      }
    },
    "1.3.0": {
      "components": {
        "semicont": { "source": "github.com/aitomatic/semikong", "ref": "260313-stable" },
        "proj":     { "version": "2026-07-01", "source": "self@commit-abc123" }
      },
      "prefixes": {
        "semicont": "https://w3id.org/semicont/ontology#",
        "proj": "https://example.com/go-tech/defect#"
      },
      "remap_from": {
        "1.2.0": { "proj:PolymerResidue": "proj:PolymerFilm" }
      }
    }
  }
}
```

- 版キー（`1.2.0` / `1.3.0`）は**自社が採番する複合語彙バージョン**。SemiKong のタグとは別物。
- `components.semicont` は**版番号ではなく git ref（タグ/コミット）でピン**（SemiKong に semver が無いため）。
  `components.proj` は自社の版・source。**`proj` だけ変えても複合版は上がる**（上の例は `semicont.ref`
  据え置きで `proj` のみ更新）。source は名前空間ごとなので「上流 1 本」にならない。
- 上流の著作来歴（派生元・公開者・原ライセンス）は**複製しない**（Aitomatic 管理。必要時は `ontology.ttl`
  を参照）。ここで持つのは「どの ref を採用したか」という**採用参照**のみ。
- runtime（スナップショット生成・マッチング）は **per-record `ontology_version` ＋ レジストリ**だけで完結する。
- `prefixes` は版で namespace が変わっても版キーで表現でき、remap 表を一元管理できる。`meta.json` は純粋な
  ドメイン識別に保てる。
- **新規レコードに刻む `ontology_version` はビルドのパラメータで渡す**（例: 候補 Vn+1 ビルド時に
  `--ontology-version 1.3.0`）。ドメインに「現行版」を状態として持たせないことで、稼働／候補の
  同期問題を回避する。

### 5.3 `prefixes` の各接頭辞

CURIE（`prefix:LocalName`）を実 IRI に展開する対応表。使うのは `semicont`（SemiKong・上流）と
`proj`（自社拡張）の 2 つで、いずれもレコードの値で使用する。registry はこの 2 名前空間を版キーで
束ねる（§5.2）。来歴（誰が・いつ）は補正レコードでは `attributed_to` / `recorded_at`、詳細は
`source_ref` 先の独立監査ログが持つ（§6.3）。

| prefix     | 名前空間                              | 正式名称（long name）              | 種別             | このプロジェクトでの役割     |
| ---------- | ------------------------------------- | ---------------------------------- | ---------------- | ---------------------------- |
| `semicont` | `https://w3id.org/semicont/ontology#` | Semiconductor Ontology (SemiKong)  | ドメイン統制語彙 | 工程・材料・装置・単位・計測 |
| `proj`     | `https://example.com/go-tech/defect#` | Project namespace (Go-Tech Defect) | 自社拡張         | SemiKong に無い欠陥クラス    |

- `semicont` の IRI は設計上の想定値。正確な値は実際の `ontology.ttl` から取り込む（§5）。SemiKong は
  semver を持たないため、採用は git ref（例 `260313-stable`／コミット）でピンする（§5.2）。
- `proj` の URI は実運用では自社ドメインに差し替える。SemiKong に既存の語彙は `semicont:`、
  無いものだけ `proj:` で補う。版は自社で採番する。
- `prov` / `dc` は使わない（上流の著作来歴は複製せず、補正レコードの来歴も監査ログに委譲するため）。

## 6. 補正レイヤの判定スキーマ

一次判定（Positive=異常候補 / Negative=正常）に対する二次判定の効果を表す。

### 6.1 `judgment`（判定＝二次判定の効果方向）

| 値                 | 一次 → 二次         | 意味                                     | 旧称   |
| ------------------ | ------------------- | ---------------------------------------- | ------ |
| `OverrideNegative` | Positive → Negative | 過検出抑制（既知の許容パターン）         | 許容   |
| `OverridePositive` | Negative → Positive | 見逃し救済（エスカレーション）           | 不許容 |
| `ReviewRequired`   | 任意 → 保留         | 人間へエスカレーション                   | 要確認 |
| `NoOverride`       | 変更なし            | 補正を放棄し一次判定を維持（＝削除表現） | (削除) |

### 6.2 `method`（補正方式）※ `judgment` と別軸

`researches.md` §5 の 3 方式比較に対応。

| 値               | 内容                                                 |
| ---------------- | ---------------------------------------------------- |
| `LabelOverride`  | ラベルを直接上書き（ハード）                         |
| `ScoreReweight`  | スコアを重み付けで調整（ソフト、`params.weight`）    |
| `ThresholdAdapt` | 判定閾値を適応（`params.threshold_delta` 等）        |
| `null`           | `judgment` が `NoOverride` / `ReviewRequired` のとき |

方向（`judgment`）× 方式（`method`）の 2 次元で表現し、`params` に方式ごとのパラメータを持たせる。

### 6.3 レコードのフィールド

- `ontology_version`: レコード単位の**自社複合語彙版**（`semicont` の git ref ＋ `proj` 版を束ねる）。
  定義（components / prefixes / remap）はグローバルレジストリを版キーで引く（§5.2）。旧版は remap でロード（§5.1）
  - 自前の JSON 構造版（`schema_version`）は持たない。無い＝`1.0` とみなす（§3）。
- `revision`: ドメイン内追記ログの連番（＝バージョン軸）
- `element_id`: 論理要素の安定 ID（編集は同一 ID で新 `revision`）。**全ドメインで一意**
  （全体1ファイルの `priority.json` §9.1 がこれをキーに順序付けるため）
- `judgment` / `method` / `params`: 上記 2 軸
- `match`: 適用条件（`prototype_ids` / `similarity_threshold` / `scope`）
- `valid_to`: 失効時刻（expiry。コンパクションで除外判定。§9 規則3）
- `recorded_at`: トランザクション時刻（コミット時刻、UTC）。as-of 参照・順序補助
- `attributed_to`: 実施者（HITL 担当者）。最小の来歴
- `source_ref`: 独立**監査ログへの外部キー**（注釈アクティビティ ID）。詳細な来歴（出典・LLM モデル・
  検証結果など）は監査ログ側が保持する（`llm-feedback-structuring` の監査ログ独立モジュール）

> **競合時の優先順位は per-record フィールドを持たない。** 別 `element_id` が同一入力にマッチした
> 場合は §9 の決定的な優先順位チェーン（specificity → safety → recency → `element_id`）で解決し、
> 例外的に人手で順序を固定したいときのみ全体1ファイルの `priority.json`（§9.1）で上書きする。

## 7. ファイルレイアウトとマニフェスト

```text
versions/
├── manifest.json                       # 全ドメインの版を束ねる（版付き）
├── ontology_registry.json              # オントロジー定義（版キー：components / prefixes / remap）共通（§5.2）
├── priority.json                       # 任意：全体1ファイルの優先順位明示上書き（派生・再生成可能。§9.1）
└── domains/
    ├── drie__sin__plasmaetch__wafer/   # 完全指定ドメイン
    │   ├── meta.json                   # 不変メタ（domain_id / domain のみ。ontology は持たない）
    │   └── log.jsonl                   # 追記専用ログ（1 行 1 レコード）
    └── drie__any__any__wafer/          # DRIE 工程全体（材料・装置を問わない）
        ├── meta.json
        └── log.jsonl
```

- **`log.jsonl` は JSONL（1 行 1 レコード）**。真の O(1) 追記・クラッシュ耐性・ストリーム parse・
  不変性を得るため、単一 JSON オブジェクトの配列に push する形は採らない。
- **ヘッダ（不変メタ）は `meta.json` に分離**し、`log.jsonl` は純粋な追記専用にする。
- 追記は単一ライタ（バッチビルドジョブ）に限定し、`revision` を原子的に採番する。読み手は並行可。

### 7.1 マニフェスト例

オントロジー版は**ドメインごとに管理**する（各ドメインの `meta.json` が権威）。したがって
マニフェストは全体の `ontology` を持たない。

```json
{
  "manifest_version": 42,
  "domains": [
    { "domain_id": "sha256:3f9a…", "slug": "drie__sin__plasmaetch__wafer", "active_revision": 1023, "log": "domains/drie__sin__plasmaetch__wafer/log.jsonl" },
    { "domain_id": "sha256:7c1e…", "slug": "drie__any__any__wafer",        "active_revision": 1,    "log": "domains/drie__any__any__wafer/log.jsonl" }
  ]
}
```

## 8. JSON サンプル

### 8.1 ドメインの不変メタ（`meta.json`）

`domain_id` と `domain`（CURIE タプル）だけの純粋なドメイン識別。オントロジー情報は持たない
（version は各 log 行の `ontology_version`、prefixes / remap はグローバルレジストリ §5.2 が権威）。
これにより「meta の版は active か候補か」という同期問題がそもそも発生しない。

```json
{
  "domain_id": "sha256:3f9a…",
  "domain": {
    "process": "semicont:DeepReactiveIonEtchProcess",
    "material": "semicont:SiliconNitride",
    "equipment": "semicont:PlasmaEtchSystem",
    "unit_of_work": "semicont:Wafer"
  }
}
```

### 8.2 ドメインの追記ログ（`log.jsonl`、作成 → 編集 → 削除）

1 行 1 レコード。各行が `ontology_version` を自己記述し、過去行は書き換えない
（`schema_version` は持たず、無い＝`1.0` とみなす。§3）。`domain_id` はログがドメイン別ファイルで
`meta.json` が権威のため各行では持たない。整形は可読性のためで、実ファイルは各レコードを 1 行に格納する。

```json
{"ontology_version":"1.2.0","revision":1001,"element_id":"e-8f3a1c","judgment":"OverrideNegative","method":"ScoreReweight","params":{"weight":0.3},"match":{"prototype_ids":["proto-1187","proto-1190"],"similarity_threshold":0.82,"scope":{"defect_class":"proj:PolymerResidue","measurement":"semicont:CriticalDimension"}},"valid_to":"2026-12-01T00:00:00Z","recorded_at":"2026-06-01T09:12:00Z","attributed_to":"op_tanaka","source_ref":"annotation:ann-5521"}
{"ontology_version":"1.2.0","revision":1005,"element_id":"e-8f3a1c","judgment":"OverrideNegative","method":"ScoreReweight","params":{"weight":0.15},"match":{"prototype_ids":["proto-1187","proto-1190","proto-1203"],"similarity_threshold":0.85,"scope":{"defect_class":"proj:PolymerResidue","measurement":"semicont:CriticalDimension"}},"valid_to":"2026-12-01T00:00:00Z","recorded_at":"2026-06-15T14:03:00Z","attributed_to":"op_tanaka","source_ref":"annotation:ann-5602"}
{"ontology_version":"1.2.0","revision":1020,"element_id":"e-8f3a1c","judgment":"NoOverride","method":null,"params":{},"match":null,"valid_to":null,"recorded_at":"2026-07-01T08:00:00Z","attributed_to":"op_tanaka","source_ref":"annotation:ann-5988"}
```

### 8.3 稼働系がロードする有効スナップショット（`revision ≤ 1023` の解決結果）

スナップショットは派生物なので、**目標 `ontology_version` に正規化**して生成する
（レジストリの remap を適用。生ログは混在版のまま保全）。

```json
{
  "ontology_version": "1.2.0",
  "domain_id": "sha256:3f9a…",
  "resolved_at_revision": 1023,
  "effective_elements": [
    {
      "element_id": "e-2b90f4",
      "from_revision": 1012,
      "judgment": "OverridePositive",
      "method": "LabelOverride",
      "params": {},
      "match": { "prototype_ids": ["proto-2041"], "similarity_threshold": 0.90, "scope": { "defect_class": "proj:MicroCrack" } },
      "valid_to": null
    }
  ]
}
```

- `e-8f3a1c` は最新（`revision 1020`）が `NoOverride` のため有効集合から除外される（＝真の削除と同じ挙動）。
- `resolved_at_revision` により、どのバージョンで解決したかを再現できる。

## 9. 有効スナップショット解決規則（コンパクション）

各ドメインで `revision ≤ active_revision` を対象に以下を適用する。

1. `element_id` ごとに **最新 `revision` のレコード**を採用する。
2. 最新が `NoOverride` の要素は**除外**する（削除と同義）。
3. `valid_to` 切れ（expiry）の要素は**除外**する。
4. どの有効要素からも参照されなくなった **孤児プロトタイプ**をメモリバンクの有効スナップショットからも除外する（バージョンタプル整合）。
5. 別 `element_id` が同一入力に競合する場合は §9.1 の優先順位チェーンで決定的に解決する。

### 9.1 優先順位チェーン（決定的・導出ベース）

競合解決に専用の per-record `priority` 整数は持たない（同値衝突が起き、結局は総順序規則が別途必要に
なるため）。競合する `element_id` 間は次の**総順序**で一意に決める（すべて既存フィールドから導出）。

1. **specificity**：`domain` タプルと `match.scope` がより具体的な方を優先
   （完全指定 > `any` / 上位クラス。§4.2 のドメイン合成規則と同一の考え方）。
2. **safety rule**：同 specificity なら安全側を優先（`OverridePositive`＝見逃し救済 >
   `OverrideNegative`＝過検出抑制）。見逃しの方が高コストというポリシーを固定する。
3. **recency**：なお同点なら大きい `revision` を優先。
4. **最終タイブレーク**：`element_id` の辞書順（総順序を保証し一意化）。

**任意の明示上書き（`priority.json`、全体1ファイル）**：自動ポリシーに逆らって特定要素を勝たせたい
場合に、`element_id` を優先順に列挙した `priority.json` を **`versions/` 直下に 1 つだけ**置く。存在すれば
チェーンの最上位として適用し、記載のない要素は上記 1〜4 で解決する。これはログ（不変・真実）ではなく
**派生・再生成可能ファイル**であり（§3 のとおり構造版は持たない）、任意。

- **全体1ファイルにする理由**：競合は §4.2 の specificity 合成で**クロスドメインでも発生**するため、
  ドメイン別ファイルでは別ドメイン要素間の順序を表現できない。全体1つの総順序に集約する。
- **前提**：`element_id` は**全ドメインで一意**（§6.3）。
- **dangling 耐性**：ドメインの未昇格・ロールバックで当該 `element_id` が有効スナップショットに
  無い場合がある。**存在しない `element_id` は無視**（エラーにしない）。
- **昇格との関係**：`manifest.json` が参照する `priority.json` を版管理し、active ポインタと一緒に
  原子的に差し替える（ドメイン単位昇格でも全体順序が壊れないようにする）。

```json
{
  "order": ["e-2b90f4", "e-8f3a1c"]
}
```

## 10. 稼働系のロードと検索

- 稼働系は起動時に有効スナップショットをロードし、**ドメイン（工程・材料・装置）をキーにした
  インメモリ索引**を構築する（線形スキャン禁止）。
- これにより、マッチ計算はファイル全体サイズではなく「該当ドメインの有効ルール数」に比例し、
  ファイルが大きくなっても検索性能が劣化しない。
- ログ（source of truth）と有効スナップショット（稼働系がロード）の 2 層構成でファイル肥大に対処する。
- バージョン昇格の反映はリロード（または Blue-Green で新インスタンスにロードして原子的に切替）。

## 11. 検証（2 段構え）

1. **構造検証**（`jsonschema`）：フィールド有無・型・enum（`judgment` / `method`）。
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

- ドメイン識別子の主キー：人間可読スラッグ主体か、ハッシュ主体か（現状はスラッグ＝ラベル、
  `domain_id`＝ハッシュの二本立てを推奨）。
- `params` の持ち方（`weight` / `score_delta` / `threshold` 等）の確定。
- 採用する SemiKong レイヤ／クラスの確定 IRI 取り込み、およびライセンス法務確認。
- §9.1 の specificity 判定の厳密化（`match.scope` の部分一致・多軸指定時の具体度スコアの定義）。
- オントロジーレジストリ（§5.2）のスキーマ確定：`remap_from` の連鎖解決（`1.2.0→1.3.0→1.4.0`）や
  クラス削除・分割（1 対多 remap）の表現。`proj` 版の採番規則（日付／semver）の確定。
- 「同一 IRI の意味変更」を検知する手段（ontology diff・SHACL 差分・回帰評価の運用）。
- `ontology_version` の remap 連鎖関数の実装方針（`schema_version` は破壊的変更を行う時点で導入）。
