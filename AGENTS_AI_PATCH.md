# AGENTS.md AI節 更新案

既存 `/AGENTS.md` を丸ごと置き換えない。
AI・画像処理関連の記述を更新するときの差分方針。

## AIモデル【PoC後FIX】

```text
意味理解・象徴要素選定:
  Gemini（初回PoC: gemini-3.7-flash）

Segmentation:
  EfficientSAM-Ti + ONNX Runtime CPU を初回PoCとする

Depth:
  P0では使わない
```

モデル・Backendは環境変数で切り替え可能にする。

## AI処理責務

```text
複数写真 + memoryText
→ Gemini: 思い出理解・Visual Element候補選定
→ Gemini: sourcePhoto + bbox
→ EfficientSAM: prompted segmentation
→ Quality Gate
→ Pillow: RGBA Layer Asset
→ Gemini: 採用LayerのComposition
→ Python: Contractへ正規化
→ GenerationResult
```

## P0禁止

- Depth Modelを先回り追加しない
- SAM 3 / YOLOE / GPU Runtimeを必須化しない
- Segment Everythingを主経路にしない
- Real失敗時にMockへfallbackしない
- runtime時にModel Weightをdownloadしない

## 代替モデルへ進む条件

1. EfficientSAMの境界品質不足 → SAM 2.1 Tiny/Small
2. bboxだけでは対象識別不足 → YOLOE系
3. 髪・半透明境界が作品品質を落とす → Matting/Refiner
4. 上記でも不足 → GPU構成を含む再設計
