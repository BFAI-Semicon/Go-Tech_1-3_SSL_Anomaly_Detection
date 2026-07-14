# SemiKong オントロジー整合・レジストリ・prefixes（§5）

> 親: [設計メモ索引](./README.md)。章番号は全体で連続（`§x.y` 参照は同ディレクトリの対応ファイル。§2–§4→[versioning-model.md](./versioning-model.md)、§6/§9→[correction-layer.md](./correction-layer.md)、§7→[file-layout-and-samples.md](./file-layout-and-samples.md)）。

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
