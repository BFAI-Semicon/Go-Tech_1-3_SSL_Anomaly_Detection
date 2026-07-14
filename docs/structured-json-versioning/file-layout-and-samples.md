# ファイルレイアウト・マニフェスト・JSON サンプル（§7・§8）

> 親: [設計メモ索引](./README.md)。章番号は全体で連続（`§x.y` 参照は同ディレクトリの対応ファイル。§2–§4→[versioning-model.md](./versioning-model.md)、§5→[ontology.md](./ontology.md)、§6/§9→[correction-layer.md](./correction-layer.md)）。

## 7. ファイルレイアウトとマニフェスト

```text
versions/
├── manifest.json                       # バージョンタプルを束ねる（memory_bank + 各ドメイン revision。§7.1）
├── ontology_registry.json              # オントロジー定義（版キー：components / prefixes / remap）共通（§5.2）
├── priority.json                       # 任意：全体1ファイルの優先順位明示上書き（派生・再生成可能。§9.1）
├── banks/                              # メモリバンク側の版付き不変アーティファクト（グローバル1軸。§2.1）
│   └── mb-2026-07-01/                  # FAISS インデックス＋メタデータ層（snapshot_id で参照）
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

オントロジーは per-record の `ontology_version`（値の権威）＋ グローバル `ontology_registry.json`
（定義＝prefixes / remap / components の権威。§5.2）で解決し、`meta.json` は domain identity
（`domain_id` / `domain`）のみを持つ。したがってマニフェストも各ドメインの `meta.json` も
`ontology` を持たない（per-domain のオントロジー権威は存在しない）。

マニフェストは**バージョンタプルの両側**を束ねる：グローバルな `memory_bank` スナップショット（§2）と、
各ドメインの `active_revision`（§4）。`memory_bank` はメモリバンク側（タプルの片側）の権威で、全ドメインが
共有する単一プールなので 1 つだけ持つ。

```json
{
  "manifest_version": 42,
  "memory_bank": { "snapshot_id": "mb-2026-07-01", "prototype_count": 1284000, "artifact": "banks/mb-2026-07-01/" },
  "domains": [
    { "domain_id": "sha256:3f9a…", "slug": "drie__sin__plasmaetch__wafer", "active_revision": 1023, "log": "domains/drie__sin__plasmaetch__wafer/log.jsonl" },
    { "domain_id": "sha256:7c1e…", "slug": "drie__any__any__wafer",        "active_revision": 1,    "log": "domains/drie__any__any__wafer/log.jsonl" }
  ]
}
```

- `memory_bank.snapshot_id` を差し替えるとメモリバンク側が原子的に切替わる（全ドメインに波及。§4）。
- 過去状態の完全再現は `(memory_bank.snapshot_id, 各ドメインの active_revision)` のタプル全体で決まる。
- `banks/<snapshot_id>/` はディスク上の版付き不変アーティファクト（FAISS インデックス＋メタデータ層。§2.1）。

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
{"ontology_version":"1.2.0","revision":1001,"element_id":"e-8f3a1c","action":"OverrideNegative","method":"ScoreReweight","params":{"weight":0.3},"match":{"prototype_ids":["proto-1187","proto-1190"],"similarity_threshold":0.82,"scope":{"defect_class":"proj:PolymerResidue","measurement":"semicont:CriticalDimension"}},"valid_to":"2026-12-01T00:00:00Z","recorded_at":"2026-06-01T09:12:00Z","attributed_to":"op_tanaka","source_ref":"annotation:ann-5521"}
{"ontology_version":"1.2.0","revision":1005,"element_id":"e-8f3a1c","action":"OverrideNegative","method":"ScoreReweight","params":{"weight":0.15},"match":{"prototype_ids":["proto-1187","proto-1190","proto-1203"],"similarity_threshold":0.85,"scope":{"defect_class":"proj:PolymerResidue","measurement":"semicont:CriticalDimension"}},"valid_to":"2026-12-01T00:00:00Z","recorded_at":"2026-06-15T14:03:00Z","attributed_to":"op_tanaka","source_ref":"annotation:ann-5602"}
{"ontology_version":"1.2.0","revision":1020,"element_id":"e-8f3a1c","action":"Retire","method":null,"params":{},"match":null,"valid_to":null,"recorded_at":"2026-07-01T08:00:00Z","attributed_to":"op_tanaka","source_ref":"annotation:ann-5988"}
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
      "action": "OverridePositive",
      "method": "LabelOverride",
      "params": {},
      "match": { "prototype_ids": ["proto-2041"], "similarity_threshold": 0.90, "scope": { "defect_class": "proj:MicroCrack" } },
      "valid_to": null
    }
  ]
}
```

- `e-8f3a1c` は最新（`revision 1020`）が `Retire` のため有効集合から除外される（＝真の削除と同じ挙動）。
- `resolved_at_revision` により、どのバージョンで解決したかを再現できる。
