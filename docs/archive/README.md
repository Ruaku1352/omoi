# 資料アーカイブ

このディレクトリは、現行Checkoutの正式仕様と混同すべきでない過去の検討資料・作業指示を保管する場所です。削除ではなく移動として保存し、READMEと`docs/`直下の仕様書は「今このブランチにある実装」を説明する資料だけに保ちます。

## 収録資料

| 区分 | 資料 | 扱い |
| --- | --- | --- |
| 履歴AI資料 | [20_AI_PROCESSING_SEQUENCE.md](legacy-ai-research/20_AI_PROCESSING_SEQUENCE.md) | Gemini / EfficientSAMによるReal AI Pipelineを前提とした処理・評価メモ。現行の`backend/ai/gemini.py`はProvider呼び出しを実装していないため、現行仕様ではない。 |
| 履歴AI資料 | [artwork-output-quality-gap-research-prompt.md](legacy-ai-research/artwork-output-quality-gap-research-prompt.md) | Real AI出力を調べるための作業指示。実装仕様・受け入れ基準ではない。 |

## 他ブランチで確認した資料

2026-09-07に、リモート追跡ブランチ `origin/main` のコミット `09bbf141c7b886314ab7c8634ad2052dfbd163e6` を確認しました。このコミットは現在のCheckoutとは異なる実装を含むため、資料本文を現行仕様へコピーしていません。必要な事実だけを、各正式仕様書で「他ブランチのPoC記録」として区別して反映しています。

| 参照元のパス | 内容 | 現行資料での扱い |
| --- | --- | --- |
| `docs/ai/00_INDEX.md` / `03_SEQUENCE.md` / `12_MVP_POC_RESULT.md` | GeminiとEfficientSAMを用いたReal AI Pipeline、MVP PoCの記録 | AI仕様書に、別ブランチでのPoC実績として記載。現行実装済みとはしない。 |
| `docs/physical-output-poc.md` | Artwork Dataを物理出力へ渡すPoCと物理試作の記録 | 物理出力仕様書に、試作履歴として記載。現行Runtime・STL生成実装とはしない。 |
| `docs/status-0903.md` | 2026-09-03時点のブランチ進捗メモ | 時点とブランチに依存するため、正式仕様へは反映しない。 |

参照元を確認・復元する必要がある場合は、対象のGit revisionを明示して読み出します。たとえば次のように確認できます。

```powershell
git show 09bbf141c7b886314ab7c8634ad2052dfbd163e6:docs/physical-output-poc.md
```

この運用により、履歴資料を失わずに、現行README・仕様書が別ブランチの機能を「今ある実装」と誤認させないようにします。
