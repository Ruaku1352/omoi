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

## D-AI-004: P0 SegmentationはEfficientSAM-Ti ONNX Runtime CPU
Status: FIX for P0

理由:
- Geminiが意味理解済み
- Box Promptで責務が足りる
- CPU Runtimeを軽くできる
- ONNX Runtimeを使える
- Cloud Run P0と相性が良い

## D-AI-005: SAM 2.1 / YOLOE / Mattingは比較・Escalation候補
Status: FIX for P0

SAM 2.1:
- 境界品質不足時

YOLOE:
- bboxだけでは対象識別不足時

Matting:
- 対象は正しいが髪/soft edge不足時

いずれもP0主経路の自動Fallbackにはしない。品質不足の原因を確認してから比較する。

## D-AI-006: Candidateは最終Layerより多めに生成
Status: 暫定 / PoC後FIX

代表:
- Candidate 6〜8
- Adopted Layer 3〜5（一般設計・過去PoCの暫定範囲）

固定Contractにはしない。初回MVPのProduction / 代表PoCでは、後続のD-AI-008がこの暫定範囲を
上書きし、Adopted Layerを正確に4層とする。

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

## D-AI-008: 初回MVP生成Profileは5枚 + memoryText → 4層 + 2L Landscape
Status: 初回MVP固定前提

- Production既定は4層を成功条件とし、4層未満をMockや低品質Maskで補完しない
- Canvasは入力写真比率ではなく `178 / 127`
- 代表PoCとFrontend handoff bundleも同じ条件で検証する
- Shared Contractの `sourcePhotos[]` / `layers[]` は可変長のまま維持する
