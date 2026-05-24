"""Local AI Orchestrator — public API surface."""

from app.ai.local_orchestrator.config import (
    LocalAIConfig,
    is_max_mode,
    load_config,
    save_config,
)
from app.ai.local_orchestrator.lms_client import (
    BusyError,
    LMSClient,
    LoadOptions,
    SamplingParams,
)
from app.ai.local_orchestrator.presets import MAX_PRESET, MODE_MAX, MODE_OFF, MODE_OTHER

# Phase 04 — prompt templates, sampling profiles, embedding service
from app.ai.local_orchestrator.embedding_service import EmbeddingService
from app.ai.local_orchestrator.prompt_templates.universal_system_vi import build as build_universal_system_vi
from app.ai.local_orchestrator.sampling_profiles import (
    SAMPLING_MAX,
    SAMPLING_OTHER,
    SamplingProfile,
    get_profile,
)

# Phase 03 — PhaseRouter state machine + provider adapters
from app.ai.local_orchestrator.phase_router import (
    PhaseRouter,
    RouterState,
    PHASE_TO_SLOT,
    get_router,
    reset_router,
)
from app.ai.local_orchestrator.provider_adapter import (
    LocalOrchestratorEmbedding,
    LocalOrchestratorLLM,
    LocalOrchestratorVision,
)

# Phase 06 — RAM guard + guarded client
from app.ai.local_orchestrator.ram_guard import RAMGuard, RAMInsufficientError
from app.ai.local_orchestrator.lms_client_guarded import LMSClientGuarded

__all__ = [
    "load_config",
    "save_config",
    "LocalAIConfig",
    "MAX_PRESET",
    "MODE_OFF",
    "MODE_MAX",
    "MODE_OTHER",
    "is_max_mode",
    # Phase 02 — LMS client
    "LMSClient",
    "LoadOptions",
    "SamplingParams",
    "BusyError",
    # Phase 04 — prompt templates + sampling + embedding
    "EmbeddingService",
    "build_universal_system_vi",
    "SamplingProfile",
    "SAMPLING_MAX",
    "SAMPLING_OTHER",
    "get_profile",
    # Phase 03 — router + adapters
    "PhaseRouter",
    "RouterState",
    "PHASE_TO_SLOT",
    "get_router",
    "reset_router",
    "LocalOrchestratorLLM",
    "LocalOrchestratorVision",
    "LocalOrchestratorEmbedding",
    # Phase 06 — RAM guard + guarded client
    "RAMGuard",
    "RAMInsufficientError",
    "LMSClientGuarded",
]
