# Requirements Document

## Project Description (Input)

半導体製造の検査では、欠陥が極めて稀でラベル付けコストが高いため、教師あり分類による
欠陥判定は成立しない（researches.md §1）。正常パッチ分布からの逸脱（anomaly score）に
基づき、欠陥候補のヒートマップと ROI 候補を教師なしで得る一次検出が必要である
（researches.md §3.1、§3.2-2）。

現状、本機能のソースコードは未実装である。`scipy>=1.13`（Mahalanobis 距離用）と
`scikit-learn>=1.4` は依存に定義済みである（`pyproject.toml`）。anomalib PatchCore を
丸ごと使わず、近傍検索は patch-feature-store、スコア化は本 spec が所有する方針である
（researches.md §10、§11）。本 spec の完了は、公開データセット VisA でパイプラインを
通しで動かす VisA 検証ゲート（`docs/visa-validation-gate.md`）の通過を条件とする。

本機能は、パッチ特徴から正常分布との逸脱を算出し、複数のスコア方式（Mahalanobis 距離、
コアセットによる PatchCore 系 k 近傍距離）を組み合わせて欠陥候補ヒートマップと ROI 候補を
出力する。装置別・チャネル別に正常分布が乖離する場合は、ドメイン（工程・材料・装置タグ）で
分割された特徴量メモリとの突き合わせを任意経路として使える。VisA でメモリバンク構築から
スコア化までを一括実行する CLI を提供し、データセットのルートディレクトリ・カテゴリ・
バックボーンをコマンドライン引数で切り替えられる。HITL によるスコア補正・最終判定、
閾値の運用点確定、MAE 再構成誤差は対象外である。

本ドキュメントは draft である。Requirements は未生成・未承認であり、
`/kiro-spec-requirements primary-anomaly-detection` で生成する。

## Requirements
<!-- Will be generated in /kiro-spec-requirements phase -->
