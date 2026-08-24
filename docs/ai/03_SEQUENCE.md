# AI処理 詳細Sequence

```mermaid
sequenceDiagram
    autonumber

    actor U as ユーザー
    participant FE as Frontend
    participant API as FastAPI Backend
    participant PIPE as AI Pipeline
    participant IMG as Pillow / Image Ops
    participant GEM as Gemini
    participant SEG as EfficientSAM-Ti ONNX
    participant Q as Mask Quality Gate
    participant ASM as Artwork Assembler
    participant VAL as Backend Validation
    participant STORE as AssetStore

    U->>FE: 複数写真を選択<br/>必要なら思い出テキスト入力
    FE->>API: POST /api/v1/artworks/generate<br/>photos[] + memoryText

    API->>API: MIME / 枚数 / サイズ検証
    API->>PIPE: generate(InputPhoto[], memoryText)

    PIPE->>IMG: 各写真をdecode
    IMG->>IMG: EXIF Orientation補正
    IMG->>IMG: Gemini解析用thumbnail生成
    IMG-->>PIPE: original + analysis image

    PIPE->>GEM: 写真群 + memoryText<br/>Structured Output指定
    GEM->>GEM: 思い出全体を意味理解
    GEM->>GEM: Visual Element候補を6〜8件生成
    GEM->>GEM: 各候補をcomponentへ分解
    GEM-->>PIPE: candidate[]<br/>priority / sourcePhoto / label / bbox

    loop 上位候補から良質Layerが必要数集まるまで
        loop Visual Element内の各component
            PIPE->>SEG: 元写真 + bbox
            SEG-->>PIPE: mask + score

            PIPE->>Q: bbox + mask + score
            Q->>Q: non-empty確認
            Q->>Q: 面積・bbox整合確認

            alt Mask品質が不足
                Q-->>PIPE: NG
                PIPE->>SEG: bbox調整 / point追加で1回再試行
                SEG-->>PIPE: refined mask
                PIPE->>Q: 再評価
                alt 再びNG
                    Q-->>PIPE: component failure
                else OK
                    Q-->>PIPE: accepted mask
                end
            else 品質が十分
                Q-->>PIPE: accepted mask
            end
        end

        alt 必須componentが揃わない
            PIPE->>PIPE: 候補を破棄し次候補へ
        else componentが揃った
            PIPE->>IMG: component masksをunion
            IMG->>IMG: 元画像へalpha適用
            IMG->>IMG: crop
            IMG->>IMG: RGBA PNG encode
            IMG-->>PIPE: Layer AssetBlob
        end
    end

    alt 最低Layer数に届かない
        PIPE-->>API: AiError
        API-->>FE: AI_FAILED
    else Layer生成成功
        PIPE->>GEM: 採用Layer thumbnail + label<br/>Composition Structured Output
        GEM->>GEM: 作品として配置を提案
        GEM-->>PIPE: x / y / scale / front-to-back

        PIPE->>ASM: 採用Layer + Composition
        ASM->>ASM: ID生成
        ASM->>ASM: x/y/scale制約
        ASM->>ASM: layerIndexを0..N-1へ正規化
        ASM->>ASM: Artwork dict生成
        ASM-->>PIPE: artwork

        PIPE-->>API: GenerationResult<br/>artwork + AssetBlob[]

        API->>VAL: Pydantic / Contract / 参照整合性検証
        alt Validation失敗
            VAL-->>API: ARTWORK_VALIDATION_FAILED
            API-->>FE: Error
        else Validation成功
            API->>STORE: Asset公開
            STORE-->>API: Asset Manifest
            API-->>FE: Artwork + Asset Manifest
            FE-->>U: 3D完成Preview
        end
    end
```

## Gemini Call構成

P0推奨:

```text
Call 1: Semantic Planning
写真群 → 候補選定 + bbox

Call 2: Composition
実際に採用できたLayer → x/y/scale/order
```

Segmentation失敗で採用要素が変わるため、最終構図は実Layer確定後に決める。
