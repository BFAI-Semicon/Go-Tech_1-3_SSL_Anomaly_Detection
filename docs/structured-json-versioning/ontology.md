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
  各要素の `ontology_version`（authored 版タグ）に記録する（§6.3）。`element_id` ごとに異なる版が混在しうる。
  ドメインファイルにも、不変な domain CURIE タプルを解釈するための **`domain_source_ontology_version`**（作成時版）を記録する。
- **SemiKong は semver を持たない**（配布は日付タグ＝例 `260313-stable`／`stable` ブランチ）。よって
  `semicont` は**版番号ではなく git ref（タグ/コミット）でピン留め**し、版番号は自社側だけが採番する。
- **オントロジーの定義（prefixes / remap 表 / 各コンポーネントの source・ref）は版をキーにした
  「グローバルレジストリ」に一元管理する**（§5.2）。ドメインファイルは定義を複製せず版キーだけを持つ。
- **`domain_source_ontology_version` の意味**：ドメインの active／候補オントロジー版ではなく、作成時の domain
  CURIE タプルを解釈するための不変な版。要素の版とは独立しており、後から新しい版の要素が追加されても更新しない。
- 欠陥タイプ分類は SemiKong では手薄なため、自社名前空間 `proj:` で拡張する。
- ライセンス/法務確認が必要（SemiKong はコードが MIT だが、オントロジー資産は上流ライセンス/条件を
  持ちうる）。正確な IRI は実際の `ontology.ttl` から取り込む。

### 5.1 オントロジーのバージョンアップ対応

語彙が更新（SemiKong の採用替え、または自社 `proj` の編集）されても、**publish 済みのドメイン版アーティファクトは
不変**。各要素の CURIE は要素自身の `ontology_version`、domain CURIE は `domain_source_ontology_version` に対して
書かれている。版を「上げる」対象の単一フィールドは存在せず、版キーのレジストリに版を追加する。
複合語彙バージョンは **`semicont`（git ref）と `proj`（自社版）のどちらが変わっても上がる**。以下の方針で扱う。

- **`ontology_version` は要素単位で自己記述**（§6.3）。過去の判定再現には当時の語彙版が必要。
- **`domain_source_ontology_version` は作成時の domain CURIE の解釈元として凍結**する。別版の要素が追加されても更新しない。
- **版の定義（prefixes / remap 表 / コンポーネント）はグローバルレジストリに版キーで追加する**（§5.2）。
  remap 表はドメインごとに散らばらず、`1.2.0 → 1.3.0` の 1 箇所で管理する（`semicont` 由来・`proj` 由来を同枠で）。
- 必要なら影響ルールを新 CURIE で再表明（要素を差し替え）し、その要素に新 `ontology_version` を刻む。
- **`domain_id` は凍結**（§4.1）。domain CURIE を remap しても再計算せず、ドメイン同一性・アーティファクト連続性を保つ。
- **ドメイン版アーティファクトは目標オントロジー版に正規化して生成**する。`domain_source_ontology_version`
  から、各要素の `match.scope` は要素の版から、それぞれレジストリの remap を適用し、`match.scope` は目標版へ
  正規化して格納する。作成時版・採用要素の authored 版・目標版ごとの domain 表現を
  `domain_representations_by_ontology_version` に格納し、正規化先を `target_ontology_version` で示す。
  稼働系の判定には目標版に対応する domain と正規化済み要素だけを使う。要素の authored 版は要素単位の
  `ontology_version` タグで判別し、**正規化前の元 CURIE は独立監査ログ（`source_ref` 先）が保持**する
  （スナップショットは稼働系向けの正規化値に一本化し、原本は監査ログに委譲する）。次の目標版へ上げる際は、
  格納済みの正規化値にレジストリの remap を前方適用して再生成する。
- **昇格は評価ゲートを通す**。オントロジー変更の種類で判定への影響が異なるため、`evaluation-framework`
  で escape/overkill の回帰を確認してから promote する。ドメイン単位で段階的に上げてよい。

オントロジー変更の種類と影響:

| 変更種別                     | ドメイン版アーティファクトへの影響 | 判定への影響                                 |
| ---------------------------- | ---------------------------------- | -------------------------------------------- |
| 追加のみ（新クラス）         | 既存 CURIE 有効、影響なし          | なし                                         |
| 改名・移動（IRI 変更）       | 旧 CURIE が dangling、remap 必須   | remap 適用＋`domain_id` 凍結なら不変         |
| 非推奨化（deprecated）       | 解決可だが要移行                   | 警告レベル                                   |
| 同一 IRI の意味変更          | 検証は通るが意味が変わる           | **黙って変わりうる（要レビュー）**           |
| 分類階層の再編（subClassOf） | CURIE は有効                       | **階層マッチの合成が変わり判定が変わりうる** |

`ontology_version` の差の現れ方は変更種別で異なる。**改名・移動**では CURIE 型フィールドの**値そのもの**
が変わる（例 `semicont:PlasmaEtchSystem` → `semicont:PlasmaEtchTool`、remap で吸収）。一方**同一 IRI の
意味変更・階層再編**では**値は同一のまま**で、差は `ontology_version` にしか現れない（値だけでは区別
できないため、要素の `ontology_version` タグと `domain_source_ontology_version` で解釈元を保持する）。いずれも
フィールドの**キー・構造は不変**（構造の版は `schema_version` の管轄。§3）。

### 5.2 オントロジーレジストリ（グローバル・版キー）

オントロジーの定義はドメインごとに持たず、プロジェクト共通の 1 ファイルに**版をキー**にして集約する。
版キーは**自社の複合語彙バージョン**で、各エントリが `semicont`（SemiKong の git ref ピン）と `proj`
（自社版）の 2 コンポーネントを持つ。各要素の `ontology_version` とドメインファイルの
`domain_source_ontology_version` がこのレジストリの該当版（`components` / `prefixes` / `remap_from`）を引く。
版キーの内容は publish 後不変とする（過去アーティファクトの解釈を安定させるため）。

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
        "semicont": { "source": "github.com/aitomatic/semikong", "ref": "260701-stable" },
        "proj":     { "version": "2026-07-01", "source": "self@commit-abc123" }
      },
      "prefixes": {
        "semicont": "https://w3id.org/semicont/ontology#",
        "proj": "https://example.com/go-tech/defect#"
      },
      "remap_from": {
        "1.2.0": {
          "proj:PolymerResidue": "proj:PolymerFilm",
          "semicont:PlasmaEtchSystem": "semicont:PlasmaEtchTool"
        }
      }
    }
  }
}
```

- 版キー（`1.2.0` / `1.3.0`）は**自社が採番する複合語彙バージョン**。SemiKong のタグとは別物。
- `components.semicont` は**版番号ではなく git ref（タグ/コミット）でピン**（SemiKong に semver が無いため）。
  `components.proj` は自社の版・source。どちらか一方だけ変えても複合版は上がる（上の例では両方を更新）。
  source は名前空間ごとなので「上流 1 本」にならない。
- 上流の著作来歴（派生元・公開者・原ライセンス）は**複製しない**（Aitomatic 管理。必要時は `ontology.ttl`
  を参照）。ここで持つのは「どの ref を採用したか」という**採用参照**のみ。
- build 時のアーティファクト生成は **要素の `ontology_version`・ドメインの `domain_source_ontology_version` ＋
  レジストリ**で解釈元を確定し、目標版へ正規化する。稼働系のマッチングは正規化済みアーティファクトを使い、
  レジストリは引かない（§8.1）。
- `prefixes` は版で namespace が変わっても版キーで表現でき、remap 表を一元管理できる。ドメインファイルは
  domain CURIE の作成時版だけを持ち、定義自体は持たない。
- **新規要素に刻む `ontology_version` はビルドのパラメータで渡す**（例: 候補 Vn+1 ビルド時に
  `--ontology-version 1.3.0`）。ドメインに「現行版」を状態として持たせないことで、稼働／候補の
  同期問題を回避する。
- **新規ドメイン作成時は同じビルドパラメータを `domain_source_ontology_version` に刻み、その後は更新しない**。

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
