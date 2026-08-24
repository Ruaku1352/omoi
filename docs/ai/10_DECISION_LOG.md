# AI Decision Log

AI内部の設計判断を残す。
Shared Contract変更は別途チーム正本へ反映する。

## D-AI-001: 完成画像生成→再Segmentationを採用しない
Status: FIX

理由:
- 元写真provenance保持
- 生成画像による改変回避
- Layer差し替え/編集を成立させる

## D-AI-002: Depth EstimationをP0から外す
Status: FIX for P0

理由:
- 複数source photo間でDepth値を比較できない
- 2.5D Layer内部のDepthを最終表現で保持しない
- layerIndexはArtwork Composition
- Model/Memory/Latency増加に対する価値が小さい

Revisit条件:
同一写真内の前後関係がVLMだけでは継続的に破綻する場合。

## D-AI-003: Segment Everythingを主経路にしない
Status: FIX for P0

```text
Gemini bbox → Prompted Segmentation
```

理由:
- 画像中全Objectは不要
- Mask Pool Matchingの複雑性回避
- 計算量抑制

## D-AI-004: 初回Segmentation PoCはEfficientSAM-Ti ONNX
Status: 暫定 / PoC後FIX

理由:
- Geminiが意味理解済み
- Box Promptで責務が足りる
- CPU Runtimeを軽くできる
- ONNX Runtimeを使える
- Cloud Run P0と相性が良い

## D-AI-005: SAM 2.1 / YOLOEはFallback比較
Status: 暫定

SAM 2.1:
- 境界品質不足時

YOLOE:
- bboxだけでは対象識別不足時

Matting:
- 対象は正しいが髪/soft edge不足時

## D-AI-006: Candidateは最終Layerより多めに生成
Status: 暫定 / PoC後FIX

代表:
- Candidate 6〜8
- Adopted Layer 3〜5

固定Contractにはしない。

## D-AI-007: GeminiはSemantic PlanningとCompositionを分ける
Status: 暫定

Call 1:
- 候補選定
- bbox

Call 2:
- 実際に採用できたLayerの構図

理由:
Segmentation failureによって最終採用要素が変わるため。
Latency問題時は1 Call化を再検討。
