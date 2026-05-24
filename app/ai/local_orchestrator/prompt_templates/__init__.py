"""
Prompt templates package — re-export all phase builders for convenient access.

Usage:
    from app.ai.local_orchestrator.prompt_templates import universal_system_vi
    from app.ai.local_orchestrator.prompt_templates import map_extract, refine_write

Or import the build functions directly:
    from app.ai.local_orchestrator.prompt_templates.map_extract import build as build_map
"""

from app.ai.local_orchestrator.prompt_templates import (
    digest_summary,
    map_extract,
    reduce_plan,
    refine_write,
    universal_system_vi,
    verify_check,
    vision_caption,
)

__all__ = [
    "universal_system_vi",
    "map_extract",
    "reduce_plan",
    "refine_write",
    "verify_check",
    "digest_summary",
    "vision_caption",
]
