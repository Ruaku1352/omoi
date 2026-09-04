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
    # coherent_group内で主componentとどう関係するかを示す内部情報。
    # Artwork Dataや公開APIには出さない。
    relation_to_primary: Literal["primary", "contained", "supported_by", "attached"] = "primary"


class VisualElementCandidate(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=64)
    source_photo_index: int = Field(ge=0)
    importance: float = Field(ge=0, le=1)
    selection_reason: str = Field(min_length=1, max_length=512)
    # Internal semantic-planning metadata. It is intentionally not exported through
    # Artwork Data or the shared API contract.
    kind: Literal["subject", "scene_anchor"] = "subject"
    # subjectだけが持つ内部意味役割。scene_anchorの種類はkindだけで表す。
    semantic_role: Literal["general", "architecture_primary", "architecture_detail"] | None = None
    # subjectだけが持つ抽出方針。scene_anchorはSegmentationしないため持たない。
    extraction_intent: Literal["single_form", "coherent_group"] | None = None
    components: list[SegmentationComponent] = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _canonicalize_subject_metadata(cls, value: object) -> object:
        """旧Saved Planを保ちつつ、kindをscene_anchorの唯一の種別情報にする。"""
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        if normalized.get("kind", "subject") == "scene_anchor":
            # 旧Planではscene_anchorをsemantic_role=general / extraction_intent=scene_anchorで
            # 二重に記録していた。意味を失わない中立値だけを読み込み時に正規化する。
            if normalized.get("semantic_role") == "general":
                normalized.pop("semantic_role")
            if normalized.get("extraction_intent") == "scene_anchor":
                normalized.pop("extraction_intent")
            return normalized
        normalized.setdefault("semantic_role", "general")
        normalized.setdefault("extraction_intent", "single_form")
        return normalized

    @model_validator(mode="after")
    def _validate_subject_metadata(self) -> VisualElementCandidate:
        if self.kind == "scene_anchor":
            if self.semantic_role is not None or self.extraction_intent is not None:
                raise ValueError("scene_anchor must not have subject metadata")
            if len(self.components) != 1:
                raise ValueError("scene_anchor requires one component")
            return self
        if self.semantic_role is None or self.extraction_intent is None:
            raise ValueError("subject requires semantic_role and extraction_intent")
        if self.extraction_intent != "coherent_group":
            return self
        if len(self.components) < 2:
            raise ValueError("coherent_group requires at least two components")
        primaries = [item for item in self.components if item.relation_to_primary == "primary"]
        if len(primaries) != 1:
            raise ValueError("coherent_group requires exactly one primary component")
        if not primaries[0].required:
            raise ValueError("coherent_group primary component must be required")
        return self


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
