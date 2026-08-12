# Requirements Document

## Project Description (Input)

半導体の超高解像度検査画像（光学／SEM）から欠陥を検出する開発者向けに、工程・材料・撮像条件をまたいで安定した汎用視覚表現が必要である。現状はソースコードが未実装で、パイプライン起点となる「画像→パッチ特徴量」の抽出機能が存在しない。データセット入力アダプタ（anomalib の型を自前タイル入力型へ変換）、超高解像度画像のタイル化／パッチ化、固定 ViT（DINOv3 を既定とし、比較用バックボーンは設定切替）によるパッチ特徴抽出、位置・ドメインメタデータと由来キーの付与、抽出器同一性メタの出力を実現する。異常スコア計算・特徴量永続化・HITL／LLM・評価指標は範囲外とする。

本ドキュメントは draft であり、requirements は未生成・未承認である。正式な要件は `/kiro-spec-requirements ssl-vit-feature-extraction` で生成する。

## Requirements
<!-- Will be generated in /kiro-spec-requirements phase -->
