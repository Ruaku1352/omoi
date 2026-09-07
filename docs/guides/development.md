# Development Conventions

ローカル開発と並行作業で共有する約束をまとめます。実装時の正本は[AGENTS.md](../../AGENTS.md)であり、この文書はREADMEから移した開始時の案内です。

## 情報源の優先順位

| 知りたいこと | 参照先 |
| --- | --- |
| 全体像・共通前提 | Drive「ドパガキ向け_5分でわかる設計理解」 |
| 作るもの | Drive「要件定義」 |
| 技術的な決定と状態ラベル | Drive「技術設計」 |
| 実際のデータ形・API | [contracts/](../../contracts/) |
| Agentの実装ルール | [AGENTS.md](../../AGENTS.md) と `skills/*/SKILL.md` |

担当本人が自分の処理を「Input → 処理 → Output」で説明できれば、担当内で完結する実装は開始できます。共通技術設計、Artwork Data、API・Protocol、MVP Scope、他担当の実装前提、費用に影響する変更は公開チャンネルで共有してから進めます。

Mermaidの構成図・sequenceDiagramは固定の提出物ではありません。必要な箇所だけ作成し、作成した図はRenderして目視確認します。詳細は`skills/project-context/SKILL.md`を参照してください。

## 共通Mockでの並行開発

`contracts/mock/`と`contracts/assets/`は、Real AIの完成を待たずに各領域を開発するための共通Fixtureです。

| Fixture | 利用箇所 |
| --- | --- |
| `mock/artwork.json` | Artwork Dataを読む側すべて（3D / 2D / 物理出力） |
| `mock/asset-manifest.json` | `assetId`から実行時URLを解決する処理 |
| `mock/generate-success-response.json` | FrontendとBackendの生成成功境界 |

- 代表Fixtureは写真5枚・4層だが、`layers[]`と`sourcePhotos[]`は可変長である。
- 差し替えUIを単独検証できるよう、`replacementCandidates`を持つLayerを含む。
- Layer Assetは透過領域を実際に持つRGBA PNGである。
- Mock Manifestの`url`はPlaceholderであり、実URLはRuntimeごとに解決する。
- Real生成結果も同じSchemaを満たすことを接続条件とする。
- Real AIの失敗をMock Artworkで隠すFallbackは作らない。

```bash
python scripts/validate_contracts.py
python scripts/validate_contracts.py path/to/real-artwork.json
python scripts/validate_contracts.py path/to/generate-response.json
```

## Contractを変更したいとき

`contracts/`、API、Repository Top Level、共通Stack、P0スコープ、費用に影響する変更は、担当内だけで確定しません。公開チャンネルで共有してから進めます。

変更が合意された場合は、同じ変更単位でSchema・Mock・[AGENTS.md](../../AGENTS.md)・関連Skillsを更新します。破壊的変更では`schemaVersion`を上げます。

## ドキュメントの置き方

- README: プロダクト概要、最初の導線、開発開始に必要な最小情報
- `docs/README.md`: 技術資料の入口と領域別仕様書の一覧
- `docs/specifications/system.md`: Deploy Unitと責務境界の概要
- `docs/guides/development.md` / `docs/guides/deployment.md`: 開発・デプロイ資料
- `docs/archive/ai-research/ai/`: AI処理の設計、評価、調査資料
- 各Deploy UnitのREADME: そのUnit固有のセットアップと実装範囲

PoCの入出力や発表素材は`poc-images/`、`poc-output/`、`assets/`に保管し、実装ドキュメントと混在させません。
