# Acceptance Criteria

## 一般API / Contract Input
- [ ] JPEG / PNG / WebP
- [ ] photos[]可変長
- [ ] memoryText無しでも動作

## 初回MVP代表Input
- [ ] 初回MVP代表ケースは写真5枚 + memoryTextあり

## Semantic Planning
- [ ] 複数写真を同一Contextで理解
- [ ] Visual Element候補を複数出す
- [ ] sourcePhotoを特定
- [ ] bboxをStructured Outputで取得
- [ ] 自由文parse無し

## Segmentation
- [ ] EfficientSAM-Ti ONNXでbox prompt
- [ ] ONNX sessionをrequestごとに再loadしない
- [ ] Model missing時clear error
- [ ] RuntimeにPyTorch必須でない
- [ ] 1候補失敗時に次候補へ進める

## Layer Asset
- [ ] RGBA PNG
- [ ] alpha channelあり
- [ ] 実際に透明pixelあり
- [ ] 元写真由来
- [ ] runtime URL無し

## Composition
- [ ] x/y 0..1
- [ ] scale > 0
- [ ] layerIndex 0..N-1 unique contiguous
- [ ] array positionをdepth意味にしない
- [ ] 初回MVPは4層、2L判Landscape (`178 / 127`)
- [ ] tall / wide / square Layerの矩形全体がCanvas内

## Contract
- [ ] Artwork Schema通過
- [ ] Asset refs完全
- [ ] sourcePhotos/layers固定長なし
- [ ] Binary Base64無し

## Error / Safety
- [ ] Real failure -> Mock fallback無し
- [ ] API Key leak無し
- [ ] Provider raw responseをFrontendへ返さない
- [ ] Internal File pathをFrontendへ返さない
- [ ] retry bounded

## Cloud Run
- [ ] CPU onlyで動作
- [ ] 1 vCPU / 2 GiBから検証
- [ ] OOM原因を測定可能
- [ ] cold/warm latency記録
- [ ] Model runtime download無し

## Testing
- [ ] Unit TestはAPI Key不要
- [ ] Unit TestはONNX weight不要
- [ ] Fake Gemini/Fake Segmenterあり
- [ ] Real PoCは別script/test marker
- [ ] `MOCK_AI=true` regression無し

## Frontend handoff
- [ ] Real生成の成功Response / Artwork / Manifest / 全Assetが1フォルダに揃う
- [ ] memoryText / metrics / READMEが揃う
- [ ] composition / bbox / mask / layer previewが揃う
- [ ] READMEにBackend Responseと各ファイルの対応、ローカル版との差がある

## Product Quality
- [ ] 作品として使えるLayerが複数生成
- [ ] 主役候補が極端に外れない
- [ ] Segmentation都合だけで無意味なObjectを選ばない
- [ ] 一部候補失敗でも代替候補で作品が成立

## physical-ready構図（AI側の限定判定）

- [ ] 背景として機能する範囲候補を最大1件だけ優先し、使えない場合は `background_missing` をprivate debugへ記録する
- [ ] 通常Layerは最終Maskが単一連結でなければ候補を不採用にし、画像上の橋渡しを行わない
- [ ] Canvas下端からの距離が0.30を超えた場合、全Layerの再構図を1回行い、なお超えるLayerだけを下方補正する
- [ ] Artwork Data・Asset Manifest・共通Contractに、候補種別・診断・支え・mm値を追加しない
- [ ] 支柱・土台・スロット・STL・実寸・組立はPhysical Output担当へ委ねる
