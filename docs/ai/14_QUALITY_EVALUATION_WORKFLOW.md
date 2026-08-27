# Artwork Quality Evaluation Workflow

## 目的

少数の代表画像へPipelineを最適化せず、あり得る撮影条件でLayer品質を観測・比較する。
生成成功、mask score、Artwork Contract通過だけを作品品質の合格とみなさない。

## Private dataset

評価datasetはGit管理外のJSONとして用意する。raw写真・memoryText・生成bundle・画像レビューは
`poc-images/` と `poc-output/` のprivate領域だけに置き、commitしない。

```json
{
  "cases": [
    {
      "id": "occluded-building",
      "photos": ["photo-01.jpg", "photo-02.jpg", "photo-03.jpg", "photo-04.jpg", "photo-05.jpg"],
      "memoryText": "旅行で見た建築と庭園の思い出。",
      "scenarioTags": ["occluded-building", "complex-background"]
    }
  ]
}
```

各caseは写真5枚、非空memoryText、状況を表すtagを持つ。最低限、単純物体、細い構造、
遮蔽建築、庭園景観、人物＋持ち物、反射・水・半透明、夜景、小物を含める。

## 実行

```powershell
uv run --project backend python scripts/run_quality_evaluation.py `
  --dataset poc-images/quality-evaluation.json `
  --max-e2e-runs 24
```

既定では各caseを `baseline` と `physical_layer_v1` で比較する。予定数が上限を超える場合は
実行せず失敗する。Real Geminiは最大24 E2E run（Semantic + Compositionの最大48呼出し）に
制限する。

## 評価と候補置換

- `debug/masks/index.json` と `metrics.json` に、component数・最大成分比・上位成分比・
  tail比・bbox coverage・border touchを保存する。
- Codexはsource → bbox → mask → RGBA → compositionを追跡し、A/B/Cとfailure stageを
  privateな `quality-review.json` へ記録する。
- 診断値は既定で観測のみ。少数画像から閾値を学習・自動変更しない。
- 十分に多様なcaseで妥当性を確認した環境変数だけ、`QUALITY_GATE_MODE=enforce` で有効化できる。
  不適格candidateは次候補へ進み、4 Layerに届かなければ明示的に失敗する。Mock fallbackはない。

## 非対象

- Contract変更、Frontend変更、SAM 2.1自動fallback、largest componentだけを残す後処理。
- 製造上のmm閾値の決定。これはPhysical Output PoCの結果を待つ。
