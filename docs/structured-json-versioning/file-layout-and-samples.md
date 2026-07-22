# ファイルレイアウト・マニフェスト・JSON サンプル（§7・§8）

> 親: [設計メモ索引](./README.md)。章番号は全体で連続（`§x.y` 参照は同ディレクトリの対応ファイル。§2–§4→[versioning-model.md](./versioning-model.md)、§5→[ontology.md](./ontology.md)、§6/§9→[correction-layer.md](./correction-layer.md)）。

## 7. ファイルレイアウトとマニフェスト

```text
versions/
├── active-manifest.json                # ツリー内で唯一の可変ポインタ（active な manifest を指す。§7.1）
├── ontology_registry.json              # オントロジー定義（版キー：components / prefixes / remap）共通・版キー内容は publish 後不変（§5.2）
├── manifests/                          # バージョンタプルを束ねる版付き不変アーティファクト（archive。§7.1）
│   ├── 41.json
│   └── 42.json
├── priorities/                         # 優先順位明示上書きの版付き不変アーティファクト（任意。§9.1）
│   └── priority-2026-07-01.json
├── banks/                              # メモリバンク側の版付き不変アーティファクト（グローバル1軸・単一親tree。§2・§2.1）
│   ├── mb-2026-06-15/
│   └── mb-2026-07-01/                  # FAISS インデックス＋メタデータ層＋版メタ（snapshot_id / parent_bank_snapshot_id）
└── domains/
    └── sha256_3f9a.../                 # ディレクトリキーは不変の domain_id（§4.1）
        ├── 1023.json                   # ドメイン版アーティファクト（domain_version で識別。不変）
        └── 1024.json
```

- **1 ドメイン = 1 JSON オブジェクト**（`domains/<domain_id>/<domain_version>.json`）。トップレベルのドメイン
  属性（`domain_representations_by_ontology_version` 等）と要素配列を 1 オブジェクトに同居させる（§8.1）。
- 各ドメイン JSON は削除・変更可能なビルド時点の必要最小構成だが、**publish された版アーティファクトは不変**で、
  これが真実（source of truth）になる（§3）。ディレクトリのキーは不変の `domain_id`（表示ラベルのスラッグは
  `manifest` が保持。§4.1）。
- ビルドは単一ライタ（バッチビルドジョブ）に限定し、新規要素の `element_id` は専用の単調カウンタで採番する
  （非再利用。§3.1・§6.3）。`domain_version` はドメイン内で単調増加（§4）。読み手は並行可。
- **タプル全体のロールバックは `active-manifest.json` を過去の manifest へ向け直す 1 回の原子的差し替え**で行う
  （新 manifest を作らない）。`manifests/` は追記専用の不変集合、ポインタだけが任意の版を指せる。1 ドメインだけを
  旧版へ戻す部分ロールバックはこれとは別操作で、新しい manifest を発行して行う（§7.1）。

### 7.1 マニフェストとポインタ

CURIE は、各要素の `ontology_version`、およびドメインファイルの `domain_source_ontology_version` とグローバルな
`ontology_registry.json`（定義＝prefixes / remap / components の権威。§5.2）で解決する。ドメインファイルの
`domain_source_ontology_version` は不変な `domain` タプルの解釈元を示すだけで、ドメインの active／候補オントロジー
版ではない。マニフェストに per-domain のオントロジー版は持たせない。

マニフェストは**稼働状態を構成するバージョンタプル全体**を束ねる：グローバルな `memory_bank`
スナップショット（§2）、任意の優先順位明示上書き `priority`（§9.1）、各ドメインの版アーティファクト（§4）。
`memory_bank` はメモリバンク側の権威で、全ドメインが共有する単一プールなので 1 つだけ持つ。`priority` は版付き
不変アーティファクトを最大 1 つ参照し、フィールドが無い場合は明示上書きなしとする。**マニフェスト自体も版付き
不変アーティファクトとして `manifests/<manifest_version>.json` にアーカイブ**し、どれが active かは唯一の可変
ファイル `active-manifest.json` が指す（git の HEAD 相当）。

`active-manifest.json`（唯一の可変ファイル。ロールバックはこの差し替え 1 回で行う）:

```json
{ "active_manifest_artifact": "manifests/42.json" }
```

アーカイブされる manifest（`manifests/42.json`。公開後不変）:

```json
{
  "manifest_version": 42,
  "memory_bank": { "snapshot_id": "mb-2026-07-01", "prototype_count": 1284000, "artifact": "banks/mb-2026-07-01/" },
  "priority": { "artifact": "priorities/priority-2026-07-01.json" },
  "domains": [
    { "domain_id": "sha256:3f9a…", "slug": "drie__sin__plasmaetch__wafer", "artifact": "domains/sha256:3f9a…/1023.json" },
    { "domain_id": "sha256:7c1e…", "slug": "drie__any__any__wafer",        "artifact": "domains/sha256:7c1e…/1.json" }
  ]
}
```

- `manifest_version` は単調増加・非再利用。ロールバックは目的の異なる 2 操作を区別する:
  - **タプル全体のロールバック**：**新 manifest を作らず** `active-manifest.json` を過去版へ向け直すだけ
    （`manifests/` は追記専用の不変集合）。bank・priority・全ドメインが当時のタプルへ一括で戻る。
  - **部分ロールバック（ドメイン単位）**：現在の他軸を維持したまま特定ドメインだけを旧 `domain_version` へ戻す。
    過去 manifest には当時の他軸が丸ごと入っており流用できないため、旧ドメイン版と現在の他軸を組み合わせた
    **新しい manifest を発行**（`manifest_version` は最大＋1）してポインタを向け直す。
  いずれの場合もロールバック後の新ビルドは最大版＋1 で publish する。
- `memory_bank.snapshot_id` を差し替えるとメモリバンク側が原子的に切替わる（全ドメインに波及。§4）。publish 検証で
  全ドメインについて、active な bank から `parent_bank_snapshot_id` を遡って各ドメイン版の
  `built_against_bank_snapshot_id` に到達できること（bank 互換の祖先判定。§4）を assert する。
- `priority.artifact` はマニフェストと同時に切り替わる。参照先は公開後に書き換えない（§9.1）。
- 過去状態の完全再現は `active-manifest.json` を当該 `manifest_version` へ向けるだけで済み、`resolved_at` の
  再現識別子は `manifest_version` が担う。
- `banks/<snapshot_id>/` はディスク上の版付き不変アーティファクト（FAISS インデックス＋メタデータ層＋版メタ
  `parent_bank_snapshot_id`。§2・§2.1）。
- `ontology_registry.json` は build 時のみ使用し、稼働・ロールバック時には引かない（ドメイン版は目標版へ正規化
  済みで自己完結。§8.3）。よって manifest はレジストリ版をピンしない（前提：版キー内容は publish 後不変）。

## 8. JSON サンプル

### 8.1 ドメイン版アーティファクト（`domains/<domain_id>/<domain_version>.json`）

ドメインの不変メタ・正規化情報・補正要素を 1 ファイルに持つ、稼働系がそのままロードできる
**目標版に正規化済み・自己完結**のアーティファクト。ビルドごとに単一ライタが全生成し、publish 後は不変。

- トップレベル（不変メタ＋正規化情報）:
  - `domain_id`（凍結。§4.1）、`domain_version`（ドメイン内単調増加。§4）
  - `domain_source_ontology_version`（domain CURIE タプルの解釈元＝作成時版。§5.1）
  - `target_ontology_version`（稼働系が使う正規化先。要素 `match.scope` もこの版へ正規化済み。§5.1）
  - `domain_representations_by_ontology_version`（同一 domain の新旧表現を版キーで格納。作成時版・採用要素の
    authored 版・目標版を含む。3 版以上でも同じマップに追加）
  - `built_against_bank_snapshot_id`（ビルド時に `match.prototype_ids` が解決できたメモリバンク版。bank 互換の
    祖先判定の到達目標。§4）
- `elements[]`（有効要素集合そのもの。削除済み要素は含まない。§9）:
  - `element_id`（全ドメイン一意・非再利用。§6.3）、`ontology_version`（要素の authored 版タグ。§6.3）
  - `action` / `method` / `params` / `match`（`match.scope` は目標版へ正規化済み）
  - `recorded_at` / `attributed_to` / `source_ref`

```json
{
  "domain_id": "sha256:3f9a…",
  "domain_version": 1023,
  "domain_source_ontology_version": "1.2.0",
  "target_ontology_version": "1.3.0",
  "built_against_bank_snapshot_id": "mb-2026-07-01",
  "domain_representations_by_ontology_version": {
    "1.2.0": {
      "process": "semicont:DeepReactiveIonEtchProcess",
      "material": "semicont:SiliconNitride",
      "equipment": "semicont:PlasmaEtchSystem",
      "unit_of_work": "semicont:Wafer"
    },
    "1.3.0": {
      "process": "semicont:DeepReactiveIonEtchProcess",
      "material": "semicont:SiliconNitride",
      "equipment": "semicont:PlasmaEtchTool",
      "unit_of_work": "semicont:Wafer"
    }
  },
  "elements": [
    {
      "element_id": 87,
      "ontology_version": "1.2.0",
      "action": "OverridePositive",
      "method": "LabelOverride",
      "params": {},
      "match": { "prototype_ids": ["proto-2041"], "similarity_threshold": 0.90, "scope": { "defect_class": "proj:MicroCrack" } },
      "recorded_at": "2026-06-20T10:00:00Z",
      "attributed_to": "op_tanaka",
      "source_ref": "annotation:ann-5700"
    }
  ]
}
```

- `domain_representations_by_ontology_version[target_ontology_version]`（目標版の表現）だけを specificity 照合・
  ドメイン合成に使う。
- 稼働・ロールバック時に `ontology_registry.json` を引かない（正規化済みで自己完結）。次の目標版へ上げる際は、
  格納済みの正規化値にレジストリの remap を前方適用して再生成する。
- 要素の authored 版は `ontology_version` タグで判別する（同一 IRI の意味変更は値では区別できないため。§5.1）。
  正規化前の元 CURIE は独立監査ログ（`source_ref` 先）が保持する（§5.1）。

### 8.2 要素の作成・編集・削除（可変・最小構成）

各ビルドで単一ライタがドメインファイルを全生成する。ファイルはビルド時点の必要最小構成で、要素ごとの履歴は
持たない（過去状態は版アーティファクトのアーカイブで再現する。§7.1）。

- **作成**：新しい `element_id` を専用カウンタで採番し `elements[]` に追加。
- **編集**：同じ `element_id` の要素を差し替える（前の内容は残さない。詳細来歴は監査ログ）。
- **削除**：`elements[]` から当該要素を取り除く（§3.1）。削除された要素は有効集合から消え、重なる広域ルールに
  フォールバックする。`element_id` は再利用しない（§6.3）。

### 8.3 メモリバンク版メタ（系譜。`banks/<snapshot_id>/`）

各メモリバンク版は自身の識別子と親を持つ。merge を許可しないため親は高々 1 つ（root は `null`）。

```json
{
  "snapshot_id": "mb-2026-07-01",
  "parent_bank_snapshot_id": "mb-2026-06-15",
  "prototype_count": 1284000
}
```

- ドメイン版の `built_against_bank_snapshot_id`（§8.1）に、active な bank から `parent_bank_snapshot_id` を
  root まで遡って到達できるかで互換を判定する（§4）。到達＝ゲート通過、個別プロトタイプの除外は §9 規則2 の
  remap／skip で処理する。`prototype_id` は安定・非再利用なので、別枝でも誤解決せず skip に留まる（§2.1）。
