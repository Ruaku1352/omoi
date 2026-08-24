# Acceptance Criteria

## Input
- [ ] JPEG / PNG / WebP
- [ ] photos[]可変長
- [ ] memoryText無しでも動作

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

## Product Quality
- [ ] 作品として使えるLayerが複数生成
- [ ] 主役候補が極端に外れない
- [ ] Segmentation都合だけで無意味なObjectを選ばない
- [ ] 一部候補失敗でも代替候補で作品が成立
