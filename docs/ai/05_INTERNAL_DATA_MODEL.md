# AI内部 Data Model

これはShared Contractではなく `backend/ai/` 内部だけで使う推奨型。

## Semantic Plan

```python
class SemanticPlan(BaseModel):
    memory_summary: str
    candidates: list[VisualElementCandidate]


class VisualElementCandidate(BaseModel):
    candidate_id: str
    label: str
    source_photo_index: int
    importance: float
    selection_reason: str
    kind: Literal["subject", "scene_anchor"]
    components: list[SegmentationComponent]


class SegmentationComponent(BaseModel):
    component_id: str
    label: str
    box_2d: Box2D
    required: bool = True


class Box2D(BaseModel):
    y_min: int
    x_min: int
    y_max: int
    x_max: int
```

Geminiのbbox座標系が0..1000ならImage Ops層で実pixelへ変換する。
内部で座標系を暗黙混在させない。

## Segmentation Result

```python
@dataclass(frozen=True)
class SegmentationResult:
    mask: np.ndarray
    score: float | None
    prompt_box_px: tuple[int, int, int, int]
```

mask shape / coordinate basisは明示する。

## Accepted Layer

```python
@dataclass
class AcceptedLayer:
    candidate_id: str
    label: str
    source_photo_index: int
    source_layer_id: str
    asset: AssetBlob
    importance: float
    kind: str
```

## Composition Plan

```python
class CompositionPlan(BaseModel):
    layers: list[LayerPlacement]


class LayerPlacement(BaseModel):
    candidate_id: str
    x: float
    y: float
    scale: float
    order: int
```

Geminiの`order`をArtwork `layerIndex`へそのまま信用して入れない。
Pythonで:
- candidate_id uniqueness
- accepted candidate存在確認
- order重複解消
- 0..N-1正規化

してからArtworkへ変換。

## physical_layer_v2の内部情報

- `scene_anchor` は背景として機能する1つの広い範囲候補。Segmentationせず、単一bboxの矩形Cropを
  不透明RGBA PNGとして使う。最終表示幅はCanvas幅の0.60以上とする。
- `subject` は最終統合Maskが単一連結である候補だけを採用する。複数componentなら別候補を試し、
  画像上の橋渡しはしない。
- `kind`、component数、`background_missing`、Canvas下端からの距離、再構図・下方補正は
  `GenerationMetrics` とPoC debugだけの内部情報である。Artwork Data / Asset Manifest / API Responseへ
  出力しない。
- Canvas下端からの距離が0.30を超えた構図は、全Layerを対象に1回だけ再構図する。なお超えるLayerだけを
  決定論的に下方補正する。支柱・土台・スロット・STLはこのModelの責務ではない。

## Shared Typeとの境界

最終的に既存:

```python
GenerationResult(
    artwork=dict,
    assets=Sequence[AssetBlob],
)
```

へ必ず落とす。
内部Pydantic ModelをFrontend/API Contractとして公開しない。
