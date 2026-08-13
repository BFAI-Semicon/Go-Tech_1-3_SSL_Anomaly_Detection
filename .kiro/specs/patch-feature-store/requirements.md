# Requirements Document

## Project Description (Input)

正常パッチ分布からの逸脱判定と ROI プロトタイプ照合には、大量のパッチ特徴量
（1 枚あたり数千〜数万パッチ）を保持し高速に近傍検索できる基盤が必要である。
装置別・チャネル別に正常分布が乖離する場合はドメイン単位の分割も要る。
また、モデル再学習なしでドリフトへ適応するには、検証済み正常特徴の追記だけでストアを
更新できる必要がある。

現状、ソースコードは未実装である。`faiss-cpu>=1.11` が依存に定義済みだが、
faiss-gpu の公式 wheel は x86-64 のみで、DGX Spark（aarch64）では faiss-cpu を使用する
制約がある。メモリバンクは DINO 本体の機能ではなく PatchCore 系の仕組みであり、
近傍探索とあわせてモデルの外側で構築する。

本仕様では、vit_embedding・annotation メタデータ・構造化 JSON・適用メタ情報を後から
検索できる索引として保持し、ドメイン（工程・材料・装置タグ）で分割し、正常パッチ特徴の
追記だけで更新できるパッチ特徴量ストアを実現する。coreset 再選択と expiry 間引きで
サイズ上限を維持し、評価用には由来キー単位の固定サイズバンクを複数構築できることとする。
特徴量の生成、異常スコアの計算、正常性検証ワークフロー自体はスコープ外とする。

## Requirements
<!-- Will be generated in /kiro-spec-requirements phase -->
<!-- このファイルは draft です。requirements はまだ generated / approved ではありません。 -->
