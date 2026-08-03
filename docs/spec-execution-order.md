# spec 実行の推奨順序

[roadmap](../.kiro/steering/roadmap.md) の 6 spec を takt-sdd で進める際の推奨順序。
roadmap の依存順（ssl-vit → store → primary → llm → correction → evaluation）を機械的に
守るのではなく、[段階的開発計画](./incremental-development-plan.md) の前倒し方針と
「スキーマの所有者を先に固める」原則で並べ替える。

## 推奨順序

実施が完了した項目にチェックを付ける。

1. [x] **promptable-correction-layer（前半）**（開発計画 Phase 0–3 の範囲に限定）
2. [ ] **ssl-vit-feature-extraction**
3. [ ] **patch-feature-store**（着手前に Lance / LanceDB スパイク判断）
4. [ ] **primary-anomaly-detection**
5. [ ] **llm-feedback-structuring**
6. [ ] **evaluation-framework**（指標・プロトコル定義のみ 4 と並行前倒し可）
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
「一次検出＋抽出器比較」の順序とも一致する。patch-feature-store の bank 版管理に入る前に Lance / LanceDB
スパイク（1〜2 日）を実施し、採否を決めてから設計を確定する
（[ライブラリ採用提案 §3](./library-adoption-proposal.md)。補正レイヤ Phase 5 の
自作範囲にも影響する）。

### evaluation-framework は「定義は早く、実装は最後」

指標・プロトコル定義（PG2・AUPRO・運用 KPI 等）は他 spec と独立に requirements／design
まで進められる（roadmap 87–89 行の注記の通り）。一方、実験実行の実装は評価対象の
パイプラインが揃ってからで、急ぐ理由がない。spec の完了としては最後に置き、
定義フェーズだけ primary-anomaly-detection と並行して前倒しする。

## 開発計画フェーズとの対応

| 順序 | spec                                | 対応フェーズ・マイルストーン                  |
| ---- | ----------------------------------- | --------------------------------------------- |
| 1    | promptable-correction-layer（前半） | Phase 0–3（合成データ、前倒し可）             |
| 2    | ssl-vit-feature-extraction          | 「SSL特徴＋ストア基盤」の前提                 |
| 3    | patch-feature-store                 | 「SSL特徴＋ストア基盤」。Lance スパイク判断点 |
| 4    | primary-anomaly-detection           | 「一次検出＋抽出器比較」                      |
| 5    | llm-feedback-structuring            | 「HITL＋補正レイヤ」                          |
| 6    | evaluation-framework                | Phase 8 の回帰ゲート                          |
| 7    | promptable-correction-layer（後半） | Phase 4–7 → Phase 8 統合                      |

バージョン管理（Phase 4）に入る時点で、バージョン管理・オントロジーを独立 spec に
切り出すかを判断する（それまでは promptable-correction-layer の 1 spec で扱う）。
