# Brief: ssl-vit-feature-extraction

## Problem

半導体の超高解像度検査画像（光学／SEM）から欠陥を検出するには、工程・材料・撮像条件を
またいで安定した汎用視覚表現が必要だが、教師あり学習は汎化が難しくラベル付けコストも高い
（researches.md §1）。パイプラインの起点となる「画像→パッチ特徴量」の抽出機能が存在しない。

## Current State

- ソースコードは未実装。依存関係のみ `pyproject.toml` に定義済み
  （timm>=1.0.20: `vit_*_patch16_dinov3` 対応、anomalib は本家 main ブランチ暫定使用）。
- anomalib v2.5.0（PyPI 公開版）の PatchCore は DINO 系バックボーンを正式サポートしておらず
  （既定は CNN の `wide_resnet50_2`）、timm 経由 drop-in 対応は本家 GitHub main ブランチに
  統合済み（researches.md §10）。
- Meta 版 DINOv2 は抽出特徴へ layer norm を適用するか否かで精度が変わるため、
  比較実験では前処理条件を揃える必要がある（researches.md §10）。

## Desired Outcome

- 超高解像度画像をタイル化・パッチ化し、固定 ViT でパッチ特徴テンソルを生成できる
  （researches.md §3.2-1）。1 枚あたり数千〜数万パッチのスケールを扱える（researches.md §4）。
- パッチ特徴に位置情報とドメインタグ（工程・材料・装置）のメタデータが付随する
  （researches.md §3.3 のドメイン分割の前提）。
- バックボーンは DINOv3 を主軸に DINO／DINOv2／MAE／汎用 ViT を差し替え可能
  （researches.md §3.1、§5 の特徴抽出器比較の前提）。
- 特徴抽出器比較（researches.md §5、§9）のため、ImageNet 教師あり CNN
  （例: `wide_resnet50_2`）も同一パイプライン上の比較用バックボーンとして差し替えられる。
- MAE 使用時はピクセル再構成誤差の算出に必要な再構成経路も提供する（researches.md §3.3）。

## Approach

- 学習済み重みを torch.hub／timm からロードして重み固定で用いる。ローカルで SSL 学習は
  行わない（researches.md §10）。初回ダウンロード後はローカルキャッシュ
  （既定 `~/.cache/torch/hub`）を使用し、完全オフライン運用は `source='local'` 指定または
  `state_dict` の自前保存で対応する（researches.md §10）。
- DINOv3 は timm>=1.0.20 の `vit_*_patch16_dinov3` を使用（`pyproject.toml` 19-20行目）。
- layer norm の有無など前処理条件を設定として明示し、CNN との比較実験で条件を揃えられる
  ようにする（researches.md §10）。

## Scope

- **In**: タイル化／パッチ化、固定 ViT による特徴抽出、位置・ドメインメタデータの付与、
  バックボーン切り替え（比較用 ImageNet 教師あり CNN、例: `wide_resnet50_2` を含む）、
  前処理条件（layer norm 等）の統一管理、MAE 再構成経路。
- **Out**: 異常スコア計算、特徴量の永続化・索引、HITL・LLM 関連機能。

## Boundary Candidates

- タイル化・パッチ化（画像幾何処理）とバックボーン推論（モデルロード・特徴抽出）の分離
- バックボーンごとの前処理差（layer norm 等）を吸収するアダプタ層

## Out of Boundary

- 異常スコア化・ヒートマップ生成（primary-anomaly-detection が所有）
- 特徴量ストアの構築・検索（patch-feature-store が所有）
- ViT の重み更新・ファインチューニング（プロジェクト全体で禁止、researches.md §3.1）

## Upstream / Downstream

- **Upstream**: なし（パイプラインの起点）。外部依存は torch.hub／timm の学習済み重み配布。
- **Downstream**: patch-feature-store（特徴の登録）、primary-anomaly-detection（スコア化の
  入力）、promptable-correction-layer（roi_embedding の生成）、evaluation-framework
  （特徴抽出器比較）。

## Existing Spec Touchpoints

- **Extends**: なし（新規）
- **Adjacent**: patch-feature-store、primary-anomaly-detection

## Constraints

- 重み更新は行わない（researches.md §3.1）。
- Python 3.12 固定・DGX Spark（aarch64／CUDA 13）対応（`pyproject.toml` 6-8行目）。
- anomalib はリリース版（2.6.0 想定）の公開まで本家 main ブランチを使用（DINOv3 対応は
  main に統合済み。`pyproject.toml` 70-75行目）。
- DINOv2 等のモデルライセンスは法務確認が必要（`docs/plan.md` リスクと対策）。
