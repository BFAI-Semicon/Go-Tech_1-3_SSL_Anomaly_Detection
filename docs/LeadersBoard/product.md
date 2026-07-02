# Product Overview

ML実験プラットフォーム「LeadersBoard」は、外部からの投稿（コード/データ）を受け付け、サーバー側でGPU学習・評価を実行し、MLflowで実験結果を可視化・比較するリーダーボード機能を提供します。anomalibを用いた異常検知モデルの評価を想定した最小構成から開始し、将来的にはEvalAI統合や大規模スケールへの拡張を見据えています。

## Core Capabilities

- **提出受付**: 認証済みユーザーからのコード/データのマルチパートアップロード受付
- **非同期ジョブ実行**: Redisキュー + GPUワーカーによる学習・評価の非同期実行
- **実験可視化**: MLflow Tracking Serverによるパラメータ・メトリクス・アーティファクトの記録と比較ビュー
- **進捗管理**: ジョブ状態・ログ・結果の取得API（`run_id` とMLflow UIリンクの返却）
- **欠陥箇所の可視化**: 異常検知結果（original / heatmap / mask / overlay）を4列比較UIで表示し、CSV予測ファイルも提供
- **リーダーボード**: MLflow UIの比較ビューを活用したランキング表示
- **Web UI**: Streamlit UIによる提出フォーム、ジョブ監視、ログ表示、可視化パネル（研究者向けフロントエンド）

## Target Use Cases

- **研究者（Streamlit UI）**: Web UIから手法をアップロードし、ジョブの進捗・ログをリアルタイム監視
- **研究者（API）**: 自分の手法をアップロードし、標準データセット（例: MVTec AD）で評価結果を確認
- **研究者**: 異常検知結果の可視化（original/heatmap/mask/overlay 4列比較、CSV予測データ）
- **研究者**: 他の提出と比較してランキング上の位置を把握（MLflow UI経由）
- **管理者**: ジョブの実行状況（進捗、ログ、エラー）を監視（Streamlit UI/API両対応）
- **管理者**: MLflow UIで全実験のメトリクス・アーティファクトを一覧・比較

## Value Proposition

- **透明性と再現性**: MLflowによる実験記録で、パラメータ・メトリクス・アーティファクトを完全追跡
- **公平な評価**: 統一された環境（GPUコンテナ、anomalib）で全提出を評価
- **拡張性**: 依存逆転（Clean-lite設計）により、将来の差し替えコスト最小化（ファイルシステム→S3、Redis→RabbitMQ、SQLite→Postgres等）
- **最小構成から開始**: docker-compose単機構成でPoC可能、将来はKubernetes移行・オートスケール対応
- **品質保証**: テストカバレッジ90.8%達成（目標80%超過）、65件のテストで品質を担保

## Project Status

- **Version**: 0.1.0
- **Phase**: 本番準備完了（コア機能・UI・可視化・ドキュメント完備）
- **Test Count**: 160件（ユニット）+ 18件（統合）= 178件
- **Implementation**: T1-T15完了（コア機能・統合テスト）+ T16.1（UI自動更新）+ T19（ドキュメント）+ 欠陥箇所可視化
- **UI Capabilities**: 提出フォーム、ジョブ一覧（自動更新対応）、ステータス監視、ログ表示、MLflowリンク生成、可視化パネル（4列比較）
- **Documentation**: README.md、API仕様（docs/api.md）、デプロイ手順（docs/deployment.md）完備
- **Specifications**: nginx-basic-auth 実装完了、
  streamlit-realtime-worker-logs 仕様初期化完了、
  migrate-formatter-to-ruff 完了、
  defect-location-visualization 実装完了、
  report-presentation-materials 実装完了
