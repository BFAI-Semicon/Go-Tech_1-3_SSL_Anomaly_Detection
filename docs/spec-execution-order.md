# spec 実行の推奨順序

[roadmap](../.kiro/steering/roadmap.md) の 6 spec を takt-sdd で進める際の推奨順序。
roadmap の依存順（ssl-vit → store → primary → llm → correction → evaluation）を機械的に
守るのではなく、[段階的開発計画](./incremental-development-plan.md) の前倒し方針と
「スキーマの所有者を先に固める」原則で並べ替える。

## 推奨順序

実施が完了した項目にチェックを付ける。

1. [x] **promptable-correction-layer（前半）**（開発計画 Phase 0–3 の範囲に限定）
2. [x] **ssl-vit-feature-extraction**
3. [x] **patch-feature-store**（Lance / LanceDB スパイク判断は bank 版管理＝補正レイヤ Phase 5 送り）
4. [ ] **primary-anomaly-detection**（完了条件に
   [VisA 検証ゲート](./visa-validation-gate.md) を置く）
5. [ ] **llm-feedback-structuring**
6. [ ] **evaluation-framework**（指標・プロトコル定義と、ゲート用の最小指標のみ 4 と並行前倒し可）
7. [ ] **promptable-correction-layer（後半）**（Phase 4–7：バージョン管理・オントロジー、
   Phase 8：実パイプライン統合・評価）

## 並べ替えの理由

### 補正レイヤを先頭に置く（roadmap 依存順との最大の差分）

roadmap 上は promptable-correction-layer が 4 spec に依存する最後発だが、この依存は
**実データ統合時（Phase 8）に初めて必要**になるもの。開発計画の通り、Phase 0–3 は
合成 fixture（ランダム埋め込みの FAISS Flat＋手書きドメイン JSON）だけで進み、
先行 spec の完成を待たない。先頭に置く理由は 3 つ。

- 研究の核であり最難関（競合解決チェーンの総順序性）を最初にデリスクできる。
- Phase 1–3 は永続化を持たず、スキーマ手戻りコストが最安の時期に判定ロジックを固められる。
- **運用スキーマ（補正レコードの action／method／match）の所有者はここ**。Phase 2 で
  スキーマを確定させることが、下流 spec の契約を安定させる。

### llm-feedback-structuring を補正レイヤ・一次検出の後に置く

roadmap では llm が correction より先だが、llm-feedback-structuring の出力（構造化 JSON）は
補正レイヤの判定スキーマそのもの。**スキーマの生産者を消費者より先に作ると、スキーマ確定の
主導権が逆転して手戻りが起きる**。Phase 2 でスキーマが確定した後なら、llm 側は
`instructor` による pydantic モデルへの構造化（[ライブラリ採用提案 §4](./library-adoption-proposal.md)）
を確定済みモデルに対して実装するだけになる。また入力（ROI 候補・スコア）を出す
primary-anomaly-detection の後に置くことで、実データでの E2E 確認も可能になる。

### 実データパイプライン 3 spec は roadmap の依存順のまま

ssl-vit-feature-extraction → patch-feature-store → primary-anomaly-detection は
データ契約（特徴テンソル → ストアレコード → スコア/ROI）の直列依存であり、
入れ替える理由がない。[milestones.md](./milestones.md) の「SSL特徴＋ストア基盤」
「一次検出＋抽出器比較」の順序とも一致する。Lance / LanceDB スパイク（1〜2 日）は
patch-feature-store の初回実装では行わず、bank 版管理（補正レイヤ Phase 5）に入る前へ送る。
初回実装は FAISS Flat＋自作の台帳層で確定させ、置き換えの採否はスパイク時に判断する
（[ライブラリ採用提案 §3](./library-adoption-proposal.md)。補正レイヤ Phase 5 の
自作範囲にも影響する）。

### 一次検出の完了条件に VisA 検証ゲートを置く

3 spec を直列に積んでも、brief の Scope をそのまま実装しただけでは spec 4 完了時点で
パイプラインを通しで動かせない。画像の読み込み・train/test 分割・GT マスク取得は
どの spec も所有しておらず（ssl-vit-feature-extraction の Upstream は「なし」）、
検出性能の数値化は evaluation-framework の所有だからである。

そこで、公開データセット VisA で「メモリバンク構築 → 一次検出 → 最小指標」を通す
[VisA 検証ゲート](./visa-validation-gate.md) を spec 4 の完了条件に置き、
不足する 2 点をゲートの成立に必要な最小範囲だけ前倒しする。実データ（MIIC・実機）を
投入する前に、特徴テンソル → ストアレコード → スコア／ROI のデータ契約が実際に
つながることを確認しておく狙い。VisA を選ぶのは CC BY 4.0（商用可）だからで、
CC BY-NC-SA 4.0 の MVTec AD は使わない（判断根拠と既知の落とし穴はゲートの文書を参照）。

ゲート通過後、独自の半導体検査画像（正常のみ）での
[正常データのみの実機画像検証](./normal-only-validation-plan.md) に進む。こちらは
指標・分割プロトコルの所有者が evaluation-framework なので、順序 6 の実施範囲として扱う。

### evaluation-framework は「定義は早く、実装は最後」

指標・プロトコル定義（PG2・AUPRO・運用 KPI 等）は他 spec と独立に requirements／design
まで進められる（roadmap 87–89 行の注記の通り）。一方、実験実行の実装は評価対象の
パイプラインが揃ってからで、急ぐ理由がない。spec の完了としては最後に置き、
定義フェーズと、VisA 検証ゲートが使う image-level AUROC・AUPRO の実装だけを
primary-anomaly-detection と並行して前倒しする。

## 開発計画フェーズとの対応

| 順序 | spec                                | 対応フェーズ・マイルストーン                  |
| ---- | ----------------------------------- | --------------------------------------------- |
| 1    | promptable-correction-layer（前半） | Phase 0–3（合成データ、前倒し可）             |
| 2    | ssl-vit-feature-extraction          | 「SSL特徴＋ストア基盤」の前提                 |
| 3    | patch-feature-store                 | 「SSL特徴＋ストア基盤」。Lance 判断は Phase 5 |
| 4    | primary-anomaly-detection           | 「一次検出＋抽出器比較」。VisA 検証ゲート     |
| 5    | llm-feedback-structuring            | 「HITL＋補正レイヤ」                          |
| 6    | evaluation-framework                | Phase 8 の回帰ゲート（最小指標は 4 で前倒し） |
| 7    | promptable-correction-layer（後半） | Phase 4–7 → Phase 8 統合                      |

バージョン管理（Phase 4）に入る時点で、バージョン管理・オントロジーを独立 spec に
切り出すかを判断する（それまでは promptable-correction-layer の 1 spec で扱う）。
