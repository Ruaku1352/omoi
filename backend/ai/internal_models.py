"""Real AI pipelineだけで使う内部型。

ここで定義する型はShared Contractではない。最終的には必ず
``GenerationResult`` に組み立てる。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Box2D(BaseModel):
    """Geminiが返す0..1000基準の ``ymin, xmin, ymax, xmax`` bbox。"""

    y_min: int = Field(ge=0, le=1000)
    x_min: int = Field(ge=0, le=1000)
    y_max: int = Field(ge=0, le=1000)
    x_max: int = Field(ge=0, le=1000)

    @model_validator(mode="after")
    def _has_area(self) -> Box2D:
        if self.x_min >= self.x_max or self.y_min >= self.y_max:
            raise ValueError("bbox must have positive area")
        return self


class SegmentationComponent(BaseModel):
    component_id: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=64)
    box_2d: Box2D
    required: bool = True


class VisualElementCandidate(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=64)
    source_photo_index: int = Field(ge=0)
    importance: float = Field(ge=0, le=1)
    selection_reason: str = Field(min_length=1, max_length=512)
    # Internal semantic-planning metadata. It is intentionally not exported through
    # Artwork Data or the shared API contract.
    kind: Literal["subject", "scene_anchor"] = "subject"
    # 建造物比較Profile専用の内部意味役割。公開Artwork Dataには出さない。
    semantic_role: Literal["general", "architecture_primary", "architecture_detail"] = "general"
    components: list[SegmentationComponent] = Field(min_length=1)


class SemanticPlan(BaseModel):
    memory_summary: str = Field(min_length=1, max_length=1024)
    candidates: list[VisualElementCandidate] = Field(min_length=1)


class LayerPlacement(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=128)
    x: float
    y: float
    scale: float
    order: int


class CompositionPlan(BaseModel):
    layers: list[LayerPlacement] = Field(min_length=1)
