# SemiKong オントロジーの工程網羅性調査

[設計メモ §5](./structured-json-versioning/ontology.md) が採用を計画している SemiKong オントロジーが、
半導体の画像検査対象となる主要工程を網羅しているかの調査結果（2026-07-28 調査、
`aitomatic/semikong` の `stable` ブランチ、446 TTL・約 776 クラス）。

**結論：工程（Process）としては網羅していない。** 装置（equipment）軸ではほぼ揃っているが、
階層が分断されており、設計メモ（§4.2・§5）の前提にいくつか影響がある。

## 工程軸の実態：3 工程ファミリーのみ

工程を表すのは `05-foundry-idm/05-wafer-fabrication-processes/` だが、存在するのは次の 3 つだけ。

| 存在する工程       | 粒度                                                            |
| ------------------ | --------------------------------------------------------------- |
| 成膜（deposition） | ALD／CVD（HDP・LP・PE）／エピタキシ／PVD まで葉ノードあり       |
| エッチング         | ALE／ドライ（DRIE・ICP・RIE）／ウェットまで葉ノードあり         |
| フォトリソグラフィ | 塗布／露光（DUV・EUV・マルチパターニング）／現像／パターン転写  |

この 3 家系は `DeepReactiveIonEtchProcess ⊂ DryEtchProcess ⊂ EtchingProcess ⊂
WaferFabricationProcess` ときれいな subClassOf 連鎖を持ち、§4.2 の上位クラスマッチに使える。
一方で、**酸化・熱処理、イオン注入・拡散、CMP、洗浄・剥離、基板準備、検査・計測工程そのもの、
後工程（ダイシング等）は工程軸に存在しない**。なお親モジュール
`wafer-fabrication-processes/ontology.ttl` 自体が「Minimal Ontology Placeholder」と明記された
雛形のまま。

## 装置軸（07-wfe）では揃うが、階層が分断している

`07-wfe` には oxidation-systems、ion-implantation、etch-systems、CMP、clean-strip、doping、
thermal-processing、annealing、**metrology-inspection（明視野・暗視野・e-beam 欠陥検査、
CD-SEM、overlay）**、inspection-tools（AFM・光学顕微鏡・TEM）が一通りある。しかも一部は
`CMPProcess`、`OxidationProcess`、`IonImplantationProcess`、`WetCleanProcess` など
工程クラスを装置モジュール内に持つ。

ただしこれらの上位クラスは `semicont-shared:ProcessStep` で、工程軸の
`WaferFabricationProcess`（`semicont-core:Process` 配下）とは**別の親にぶら下がっている**。
つまり「エッチング起因の欠陥ルールを CMP にも階層マッチで波及させる」ような工程横断の
上位クラスマッチは、現行の階層では成立しない。

## 設計メモの想定との突き合わせ

[ontology.md](./structured-json-versioning/ontology.md) の想定値を実物と照合した結果：

- `semicont:DeepReactiveIonEtchProcess` — **実在**。ただし `05` 工程軸と `07-wfe` 装置軸の
  **両方に同名クラスがあり**、単一 prefix では曖昧。
- `semicont:PlasmaEtchSystem`・`semicont:SiliconNitride`・`Wafer` — 実在。
- `semicont:CriticalDimension`（`match.scope.measurement` 用）— **クラスとして存在しない**
  （CD-SEM 装置クラスとコメント中の言及のみ）。measurement 語彙も `proj:` 拡張が必要になる。
- 欠陥語彙 — 設計メモの「quality は薄いため自社拡張」は正しく、実態は想定よりさらに薄い
  （`06-yield-optimization/00-defect-analysis` は `DefectAnalysisConcept` 1 クラスのみ）。
- **名前空間** — 設計メモは単一 prefix `https://w3id.org/semicont/ontology#` を想定しているが、
  実物は**モジュールごとに別名前空間**。例:

```text
https://semicont.org/ontology/05-foundry-idm/05-wafer-fabrication-processes/01-etching/01-dry-etch/00-deep-reactive-ion-etch/#
```

  `semicont` 1 個の prefix map では成立せず、§5.2 レジストリの `prefixes` をモジュール別に
  持つか、自社側で短縮 prefix 体系を定義する必要がある。§5.3 の「正確な IRI は ontology.ttl
  から取り込む」は、想定より大きな作業になる。

## 成熟度

446 TTL のうち 58 ファイルが明示的なプレースホルダを含み、全モジュールが
`owl:versionInfo "0.1.0"`、生成日は 2026-03。SemiKong 論文（arXiv:2411.13802）は
「Substrate Preparation〜Metrology and Inspection〜Back-End まで 10 の第一階層で全工程を網羅」
と述べているが、**現行リポジトリの TTL はその構想を反映しきれていない**。急速に整備中の
初期段階のオントロジーであり、設計メモが git ref でピン留めする方針にしているのは正しい判断。

## 実務への含意

1. `domain.process` に CMP・洗浄・注入・熱処理を入れたい場合、現状は `07-wfe` 側の
   Process クラスを借りるか `proj:` で工程クラスを補うことになり、**`proj:` 拡張の範囲が
   「欠陥クラスのみ」の想定から「欠落工程＋measurement 語彙＋階層の橋渡し」に広がる**
   可能性が高い。
2. §4.2 の上位クラスマッチは、エッチング・リソ・成膜の 3 家系内では機能するが、
   工程横断では自社で階層を補う必要がある。
3. 名前空間の乖離は §5.2 レジストリのスキーマ（prefixes の持ち方）に影響するため、
   Phase 7 着手前に [ontology.md](./structured-json-versioning/ontology.md) の想定値を
   実物に合わせて改訂するのがよい。
