# ファイルレイアウト・マニフェスト・JSON サンプル（§7・§8）

> 親: [設計メモ索引](./README.md)。章番号は全体で連続（`§x.y` 参照は同ディレクトリの対応ファイル。§2–§4→[versioning-model.md](./versioning-model.md)、§5→[ontology.md](./ontology.md)、§6/§9→[correction-layer.md](./correction-layer.md)）。

## 7. ファイルレイアウトとマニフェスト

```text
versions/
├── manifest.json                       # バージョンタプルを束ねる（memory_bank + priority + 各ドメイン revision。§7.1）
├── ontology_registry.json              # オントロジー定義（版キー：components / prefixes / remap）共通（§5.2）
├── priorities/                         # 優先順位明示上書きの版付き不変アーティファクト（任意。§9.1）
│   └── priority-2026-07-01.json
├── banks/                              # メモリバンク側の版付き不変アーティファクト（グローバル1軸。§2.1）
│   └── mb-2026-07-01/                  # FAISS インデックス＋メタデータ層（snapshot_id で参照）
└── domains/
    ├── drie__sin__plasmaetch__wafer/   # 完全指定ドメイン
    │   ├── meta.json                   # 不変メタ（domain_id / 作成時 ontology_version / domain）
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

CURIE は、各 log 行の `ontology_version`、および `meta.json` の作成時 `ontology_version` とグローバルな
`ontology_registry.json`（定義＝prefixes / remap / components の権威。§5.2）で解決する。`meta.json` の
版は不変な `domain` タプルの解釈元を示すだけで、ドメインの active／候補オントロジー版ではない。
マニフェストに per-domain のオントロジー版は持たせない。

マニフェストは**稼働状態を構成するバージョンタプル全体**を束ねる：グローバルな `memory_bank`
スナップショット（§2）、任意の優先順位明示上書き `priority`（§9.1）、各ドメインの `active_revision`
（§4）。`memory_bank` はメモリバンク側の権威で、全ドメインが共有する単一プールなので 1 つだけ持つ。
`priority` は版付き不変アーティファクトを最大 1 つ参照し、フィールドが無い場合は明示上書きなしとする。

```json
{
  "manifest_version": 42,
  "memory_bank": { "snapshot_id": "mb-2026-07-01", "prototype_count": 1284000, "artifact": "banks/mb-2026-07-01/" },
  "priority": { "artifact": "priorities/priority-2026-07-01.json" },
  "domains": [
    { "domain_id": "sha256:3f9a…", "slug": "drie__sin__plasmaetch__wafer", "active_revision": 1023, "log": "domains/drie__sin__plasmaetch__wafer/log.jsonl" },
    { "domain_id": "sha256:7c1e…", "slug": "drie__any__any__wafer",        "active_revision": 1,    "log": "domains/drie__any__any__wafer/log.jsonl" }
  ]
}
```

- `memory_bank.snapshot_id` を差し替えるとメモリバンク側が原子的に切替わる（全ドメインに波及。§4）。
- `priority.artifact` はマニフェストと同時に切り替わる。参照先は公開後に書き換えない（§9.1）。
- 過去状態の完全再現は `(memory_bank.snapshot_id, priority.artifact または未指定, 各ドメインの
  active_revision)` のタプル全体で決まる。
- `banks/<snapshot_id>/` はディスク上の版付き不変アーティファクト（FAISS インデックス＋メタデータ層。§2.1）。

## 8. JSON サンプル

### 8.1 ドメインの不変メタ（`meta.json`）

`domain_id`、`domain`（CURIE タプル）、そのタプルを記述した作成時の `ontology_version` を持つ。
この版は `domain` の解釈元として `meta.json` とともに凍結し、log に新しいオントロジー版の revision が
追加されても更新しない。active／候補の状態ではないため同期問題は生じない。スナップショット生成時に
この版から目標版へ remap し、`domain_id` は再計算しない（§5.1）。

```json
{
  "domain_id": "sha256:3f9a…",
  "ontology_version": "1.2.0",
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
{"ontology_version":"1.2.0","revision":1001,"element_id":"e-8f3a1c","action":"OverrideNegative","method":"ScoreReweight","params":{"weight":0.3},"match":{"prototype_ids":["proto-1187","proto-1190"],"similarity_threshold":0.82,"scope":{"defect_class":"proj:PolymerResidue","measurement":"semicont:CriticalDimension"}},"recorded_at":"2026-06-01T09:12:00Z","attributed_to":"op_tanaka","source_ref":"annotation:ann-5521"}
{"ontology_version":"1.2.0","revision":1005,"element_id":"e-8f3a1c","action":"OverrideNegative","method":"ScoreReweight","params":{"weight":0.15},"match":{"prototype_ids":["proto-1187","proto-1190","proto-1203"],"similarity_threshold":0.85,"scope":{"defect_class":"proj:PolymerResidue","measurement":"semicont:CriticalDimension"}},"recorded_at":"2026-06-15T14:03:00Z","attributed_to":"op_tanaka","source_ref":"annotation:ann-5602"}
{"ontology_version":"1.2.0","revision":1020,"element_id":"e-8f3a1c","action":"Retire","method":null,"params":{},"match":null,"recorded_at":"2026-07-01T08:00:00Z","attributed_to":"op_tanaka","source_ref":"annotation:ann-5988"}
```

### 8.3 稼働系がロードする有効スナップショット（`revision ≤ 1023` の解決結果）

スナップショットは派生物なので、**目標 `ontology_version` に正規化**して生成する
（レジストリの remap を `meta.json` の `domain` と各 log 行の CURIE に適用。元データは書き換えない）。
新旧表現を比較できるように、meta の作成時版、採用した各要素の元版、目標版における domain 表現を
`domain_representations_by_ontology_version` へ版キーで格納する（版数に上限は設けない）。稼働系の判定には
`domain_representations_by_ontology_version[target_ontology_version]`、すなわち目標版に対応する表現だけを使う。

```json
{
  "target_ontology_version": "1.3.0",
  "domain_id": "sha256:3f9a…",
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
  "resolved_at_revision": 1023,
  "effective_elements": [
    {
      "element_id": "e-2b90f4",
      "from_revision": 1012,
      "action": "OverridePositive",
      "method": "LabelOverride",
      "params": {},
      "match": { "prototype_ids": ["proto-2041"], "similarity_threshold": 0.90, "scope": { "defect_class": "proj:MicroCrack" } }
    }
  ]
}
```

- `e-8f3a1c` は最新（`revision 1020`）が `Retire` のため有効集合から除外される（＝真の削除と同じ挙動）。
- `resolved_at_revision` により、どのバージョンで解決したかを再現できる。
- `domain_representations_by_ontology_version` は、`meta.json` の作成時表現から各版へ remap した
  同一 domain の新旧表現。
  3 版以上が混在する場合も同じマップへ版キーを追加する。
- `target_ontology_version` は稼働系が使う domain 表現と、要素本体の CURIE の正規化先を示す。元の版は
  `from_revision` で不変の `log.jsonl` を参照して確認し、元の `meta.json` と `domain_id` は変更しない。
