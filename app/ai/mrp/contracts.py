"""
MRP contracts — pydantic models shared across mapper/reducer/writer/digest.

`CompilationPlanJson` is the single source of truth for the schema of
`SourceCompilationPlan.plan_json`. Phase 2 reducer writes via
`.model_dump()`; Phase 8 digest + Phase 9 A/B harness read via
`CompilationPlanJson.model_validate(plan.plan_json)`.

`extra = "allow"` tolerates legacy fields (`_claims`, `_entities`,
`_concepts`, `_page_drafts`, `pages`) during rollout — we read the typed
fields and ignore unknown keys.
"""

from typing import Literal

from pydantic import BaseModel

PipelineShape = Literal["stuff", "single_map", "full_mrp", "hierarchical"]


class CompilationPlanJson(BaseModel):
    """Typed view over `plan_json`. Field set is intentionally small."""

    pipeline_shape: PipelineShape = "full_mrp"
    page_slugs: list[str] = []
    summary: str = ""

    class Config:
        extra = "allow"
