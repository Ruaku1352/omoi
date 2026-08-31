# AI・画像処理 設計Index

## 目的

omoiのAI処理を「AIを使うこと」ではなく、
**複数写真から思い出を象徴する要素を自動で抽出し、作品として使えるLayer Assetへ変換すること**
から逆算して実装する。

## 読む順番

1. `01_PRODUCT_GOAL.md`
2. `02_AI_ARCHITECTURE.md`
3. `03_SEQUENCE.md`
4. `04_MODEL_SELECTION.md`
5. `05_INTERNAL_DATA_MODEL.md`
6. `06_IMPLEMENTATION_PLAN.md`
7. `07_POC_TEST_PLAN.md`
8. `08_ACCEPTANCE_CRITERIA.md`
9. `09_CLOUD_RUN_CONSTRAINTS.md`
10. `10_DECISION_LOG.md`
11. `11_EFFICIENTSAM_ARTIFACT.md`
12. `12_MVP_POC_RESULT.md`
13. `13_ARTWORK_OUTPUT_QUALITY_GAP_REPORT.md`
14. `14_QUALITY_EVALUATION_WORKFLOW.md`
15. `99_SOURCES.md`

## 現時点の一文

```text
Geminiが「何を思い出として残すか」を決め、
EfficientSAM-Tiが「どこまでがその対象か」を切り、
Pillow/Pythonが「作品として使えるLayer」にする。
```

## physical-ready構図におけるAIの責務

`physical_layer_v2` は、背景として機能する範囲Layerを優先し、通常Layerを単一連結に保ち、
Canvas下端からの浮遊量を抑えるAI内部Profileである。診断はprivate PoC debugだけへ残し、
Artwork Data・共通Contractへ製造情報は追加しない。支柱・土台・スロット・STL・実寸・組立は
Physical Output担当の責務である。

## 状態

- 意味理解・構成モデル: Gemini Developer API。具体的な `GEMINI_MODEL` は【PoC後FIX】
- Segmentation: 【FIX for P0】EfficientSAM-Ti + ONNX Runtime CPU
- Depth: 【FIX for P0】使わない
- Runtime GPU: 【FIX for P0】必須にしない
- 初回MVP入力: 写真5枚 + memoryText
- 初回MVP出力: 4層（Contract自体は可変長）
- 初回MVP Canvas: 2L判Landscape（`178 / 127`）
- Candidate数: 【PoC後FIX】代表6〜8
