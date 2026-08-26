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
