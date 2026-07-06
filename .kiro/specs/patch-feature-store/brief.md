# Brief: patch-feature-store

## Problem

正常パッチ分布からの逸脱判定と ROI プロトタイプ照合には、大量のパッチ特徴量
（1 枚あたり数千〜数万パッチ、researches.md §4）を保持し高速に近傍検索できる基盤が必要。
装置別・チャネル別に正常分布が乖離する場合はドメイン単位の分割も要る（researches.md §3.3）。
また、モデル再学習なしでドリフトへ適応するには、検証済み正常特徴の追記だけでストアを
更新できる必要がある（researches.md §11）。

## Current State

- ソースコードは未実装。`faiss-cpu>=1.11` が依存に定義済み（`pyproject.toml` 22-25行目）。
- faiss-gpu の公式 wheel は x86-64 のみで、DGX Spark（aarch64）では faiss-cpu を使用する
  制約がある（`pyproject.toml` 23行目コメント）。
- メモリバンクは DINO 本体の機能ではなく PatchCore 系の仕組みであり、近傍探索とあわせて
  モデルの外側で構築する（researches.md §10）。

## Desired Outcome

- vit_embedding、annotation メタデータ、構造化 JSON、適用メタ情報を後から検索できる
  索引として保持する（researches.md §6 の特徴量ストア）。
- ドメイン（工程・材料・装置タグ）で分割され、適用対象と突き合わせられる
  （researches.md §3.3）。
- 正常パッチ特徴の追記だけで更新でき、勾配更新は不要（researches.md §11）。
  初期構築と定期追加が同じ登録操作で行える。
- coreset 再選択でサイズ上限を維持し、古い・冗長・失効（expiry）したプロトタイプを
  間引ける（researches.md §11）。

## Approach

- FAISS（faiss-cpu）で kNN インデックスを構築する。インデックス方式は Flat／IVF／PQ から
  選択でき、Flat 系は追記が単純、IVF／PQ など量子化系は分布変化時にクラスタ中心の再学習・
  再構築を行う方針とする（researches.md §11）。
- 追加更新時は、新規点として追加するか既存点へ統合するかを最近傍距離で判定する
  （researches.md §11）。
- 登録は検証済みの正常のみとし、HITL 検証・スキーマ検証・監査ログで正常性が担保された
  データだけを受け入れて汚染を防ぐ（researches.md §11）。

## Scope

- **In**: インデックス構築・近傍検索・増分追加・永続化、ドメイン分割、coreset 再選択、
  expiry 間引き、検証済み正常のみを登録するガード、メタデータ（annotation・構造化 JSON・
  適用メタ情報）の索引。
- **Out**: 特徴量の生成、異常スコアの計算、正常性検証ワークフローの実装
  （llm-feedback-structuring の監査ログと連携するが検証自体は所有しない）。

## Boundary Candidates

- インデックス層（FAISS ベクトル検索）とメタデータ層（ドメインタグ・適用条件での絞り込み）
  の分離
- 登録（書き込み・ガード・coreset 管理）と検索（読み取り）の分離

## Out of Boundary

- パッチ特徴の生成（ssl-vit-feature-extraction が所有）
- 異常スコア化（primary-anomaly-detection が所有）
- プロトタイプ登録の判断を生む HITL フロー（llm-feedback-structuring が所有）

## Upstream / Downstream

- **Upstream**: ssl-vit-feature-extraction（登録する特徴ベクトルとメタデータの供給元）。
  なお llm-feedback-structuring からの検証済みプロトタイプ・正常特徴の登録トリガーは
  実行時のデータフローであり、ビルド依存（roadmap の Dependencies）には含めない
  （循環依存を避けるため。roadmap の Shared seams 参照）。
- **Downstream**: primary-anomaly-detection（正常分布との距離計算）、
  promptable-correction-layer（プロトタイプ近傍照合）、evaluation-framework
  （ストア規模スイープの計測対象）。

## Existing Spec Touchpoints

- **Extends**: なし（新規）
- **Adjacent**: ssl-vit-feature-extraction、primary-anomaly-detection、
  promptable-correction-layer

## Constraints

- aarch64（DGX Spark）のため faiss-cpu を使用。GPU 近傍探索が必要になった場合は sm_121
  指定のソースビルドまたは cuVS を検討（`pyproject.toml` 23-24行目コメント）。
- 追加前後で流出率（escape）・過検出率（overkill）を監視できるよう、追加操作を記録する
  （researches.md §11）。
