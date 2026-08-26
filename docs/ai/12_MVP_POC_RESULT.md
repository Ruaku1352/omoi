# 初回MVP Real AI PoC結果

## 条件

- 実行日: 2026-08-26
- 入力: 同じ代表写真5枚 + 同じmemoryText
- Model: `gemini-3.7-flash`（PoC時の環境設定。最終FIXではない）
- Segmentation: EfficientSAM-Ti ONNX Runtime CPU
- Real E2E完走: 3回（変更前baseline 1回、MVP整合後1回、Semantic改善後final 1回）
- 成功runごとのGemini call: Semantic Planning 1回 + Composition 1回
- Semantic改善後の初回確認は実行時の環境変数名誤記により、Semantic Planning後・
  Segmentation前に1回停止した。MockへFallbackせず失敗Artifactを保存し、設定名だけを正して再開した
- 今回のGemini call合計: 7回（完走3回 x 2 + 上記停止runのSemantic Planning 1回）

## Baseline / Final

| 指標 | Baseline | Final | 変化 |
|---|---:|---:|---:|
| 入力写真 | 5 | 5 | 同一 |
| 出力Layer | 5 | 4 | MVP要件へ整合 |
| Canvas aspectRatio | 0.75（先頭写真依存） | 1.4015748031496063 | 2L Landscapeへ修正 |
| Semantic Planning | 32,679 ms | 29,248 ms | -10.5% |
| Segmentation合計 | 13,558 ms | 10,091 ms | -25.6% |
| Layer Build合計 | 5,947 ms | 5,344 ms | -10.1% |
| Composition | 8,157 ms | 9,973 ms | +22.3% |
| Total | 55,366 ms | 51,714 ms | -6.6% |

性能値は各1回の実測で、Provider変動と5層→4層の処理量減少を含む。一般的な性能向上率とは
断定しない。品質を壊す並列化や追加Modelは行っていない。

## Final Acceptance

- 写真5枚 + memoryTextが記録されている
- 4層、`layerIndex = 0..3`
- `canvas.aspectRatio = 178 / 127`
- Assetの縦横比を含む矩形計算で全Layerの画面外率0（浮動小数誤差を除く）
- API互換版 / Bundle相対URL版の両方がContract validationを通過
- source 5件 + layer 4件の全9 AssetがManifestから解決可能
- 4 LayerはいずれもRGBA PNGで実際の透明pixelを持つ
- composition / source / bbox / mask / layer previewを生成
- Bundle READMEにBackend Response、各ファイル対応、Frontend利用順、2版の違いを記載

## 目視品質と残課題

- 前runで背景混入が大きかった半透明の噴水に対し、二値Maskと相性の悪い透明・反射主体を
  同等に意味のある不透明主体より優先しないSemantic指示を追加した
- Finalでは噴水が選ばれず、漆皿、石塔、木組み模型、庭園母屋の4要素を判別できる
- 漆皿と木組み模型は輪郭が明瞭。石塔には背景が少量、庭園母屋には屋根の飛び地が残る
- 4層作品とFrontend統合を確認するMVP Bundleとしては利用可能だが、物理出力の最終品質としては
  飛び地除去・境界品質の改善余地がある
- 単一Artifactだけを根拠に新しいreject閾値を固定しない。複数代表ケースで
  「bboxが正しいのに境界品質が不足」の再現率を集め、継続する場合にSAM 2.1を比較する。
  P0主経路の自動Fallbackにはしない

## Frontend handoff

Git管理外の `poc-output/final-mvp/frontend-debug-bundle-20260826-122150/` に、
実生成Bundleを保存した。個人データを含むためGitや外部公開先へ自動送信しない。
