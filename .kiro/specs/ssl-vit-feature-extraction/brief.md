# Brief: ssl-vit-feature-extraction

## Problem

半導体の超高解像度検査画像（光学／SEM）から欠陥を検出するには、工程・材料・撮像条件を
またいで安定した汎用視覚表現が必要だが、教師あり学習は汎化が難しくラベル付けコストも高い
（researches.md §1）。パイプラインの起点となる「画像→パッチ特徴量」の抽出機能が存在しない。

## Current State

- ソースコードは未実装。依存関係のみ `pyproject.toml` に定義済み
  （timm>=1.0.20: `vit_*_patch16_dinov3` 対応、`anomalib[cu130]>=2.6,<3`）。
- anomalib>=2.5.1 の `TimmFeatureExtractor`（`output_fmt="NLC"`）で DINOv3 を
  バックボーン名指定により利用可能（researches.md §10）。
- Meta 版 DINOv2 は抽出特徴へ layer norm を適用するか否かで精度が変わるため、
  比較実験では前処理条件を揃える必要がある（researches.md §10）。

## Desired Outcome

- 超高解像度画像をタイル化・パッチ化し、固定 ViT でパッチ特徴テンソルを生成できる
  （researches.md §3.2-1）。1 枚あたり数千〜数万パッチのスケールを扱える（researches.md §4）。
- パッチ特徴に位置情報とドメインタグ（工程・材料・装置）のメタデータが付随する
  （researches.md §3.3 のドメイン分割の前提）。
- 実装対象は DINOv3（anomalib `TimmFeatureExtractor`）。比較用に DINOv2／DINO／
  ImageNet 教師あり CNN（例: `wide_resnet50_2`）をバックボーン名の設定切替で差し替え可能
  （researches.md §3.1、§5）。専用コードは持たない。
- 抽出器の同一性メタ（モデル名・重みリビジョン・前処理条件・埋め込み次元）を出力し、
  下流のストア／補正が同一バックボーン由来であることを検証できる。

## Approach

- 学習済み重みを anomalib `TimmFeatureExtractor`（timm 経由）からロードして重み固定で用いる。
  ローカルで SSL 学習は行わない（researches.md §10）。
- DINOv3 は timm>=1.0.20 の `vit_*_patch16_dinov3` を使用（`pyproject.toml`）。
- layer norm の有無など前処理条件を設定として明示し、CNN との比較実験で条件を揃えられる
  ようにする（researches.md §10）。
- 特徴抽出器は Protocol で抽象化し、将来の差し替えに備える。

## Scope

- **In**: タイル化／パッチ化、固定 ViT（DINOv3）による特徴抽出、位置・ドメインメタデータの付与、
  バックボーン切替（比較用 DINOv2／DINO／ImageNet 教師あり CNN）、前処理条件（layer norm 等）の
  統一管理、抽出器同一性メタの出力。
- **Out**: 異常スコア計算、特徴量の永続化・索引、HITL・LLM 関連機能、
  MAE 再構成経路（将来検討。researches.md §3.3）。

## Boundary Candidates

- タイル化・パッチ化（画像幾何処理）とバックボーン推論（モデルロード・特徴抽出）の分離
- バックボーンごとの前処理差（layer norm 等）を吸収するアダプタ層
- 特徴抽出器 Protocol（実装差し替え口）

## Out of Boundary

- 異常スコア化・ヒートマップ生成（primary-anomaly-detection が所有）
- 特徴量ストアの構築・検索（patch-feature-store が所有）
- ViT の重み更新・ファインチューニング（プロジェクト全体で禁止、researches.md §3.1）
- MAE 再構成経路（将来検討）

## Upstream / Downstream

- **Upstream**: なし（パイプラインの起点）。外部依存は anomalib／timm の学習済み重み配布。
- **Downstream**: patch-feature-store（特徴の登録）、primary-anomaly-detection（スコア化の
  入力）、promptable-correction-layer（roi_embedding の生成）、evaluation-framework
  （特徴抽出器比較）。

## Existing Spec Touchpoints

- **Extends**: なし（新規）
- **Adjacent**: patch-feature-store、primary-anomaly-detection

## Constraints

- 重み更新は行わない（researches.md §3.1）。
- Python 3.12 固定・DGX Spark（aarch64／CUDA 13）対応（`pyproject.toml`）。
- anomalib は PyPI `>=2.6,<3`。利用範囲は特徴抽出のみ（ストア・スコア化は自前）。
- DINOv2 等のモデルライセンスは法務確認が必要（`docs/plan.md` リスクと対策）。
