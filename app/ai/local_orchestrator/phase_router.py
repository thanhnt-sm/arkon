"""
Phase Router — state machine managing which LM Studio model is loaded.

Exactly one slot (vision OR main_llm) may be loaded at a time. When a phase
requires a different slot, the router unloads the current model before loading
the next one. Embedding is always handled in-process via EmbeddingService and
never touches LMSClient.

Singleton pattern: call ``get_router(session)`` to obtain the process-wide
instance. ``reset_router()`` tears down the singleton for tests or config
reload.

State machine transitions::

    IDLE → LOADING_VISION → VISION_ACTIVE → UNLOADING_VISION → IDLE
                                                             ↘ LOADING_MAIN_LLM
    IDLE → LOADING_MAIN_LLM → MAIN_LLM_ACTIVE → UNLOADING_MAIN_LLM → IDLE
                                                                    ↘ LOADING_VISION
"""

from __future__ import annotations

import asyncio
from enum import Enum
from typing import Optional, TYPE_CHECKING

from loguru import logger

from app.ai.local_orchestrator.embedding_service import EmbeddingService
from app.ai.local_orchestrator.lms_client import (
    LMSClientProtocol,
    LoadOptions,
    SamplingParams,
)
from app.ai.local_orchestrator.lms_client_guarded import LMSClientGuarded
from app.ai.local_orchestrator.ram_guard import RAMGuard
from app.ai.local_orchestrator.sampling_profiles import get_profile

from app.ai.local_orchestrator.config import load_config

if TYPE_CHECKING:
    from app.ai.local_orchestrator.config import LocalAIConfig
    from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# State enum
# ---------------------------------------------------------------------------


class RouterState(str, Enum):
    IDLE = "idle"
    LOADING_VISION = "loading_vision"
    VISION_ACTIVE = "vision_active"
    UNLOADING_VISION = "unloading_vision"
    LOADING_MAIN_LLM = "loading_main_llm"
    MAIN_LLM_ACTIVE = "main_llm_active"
    UNLOADING_MAIN_LLM = "unloading_main_llm"


# ---------------------------------------------------------------------------
# Phase → slot mapping
# ---------------------------------------------------------------------------

PHASE_TO_SLOT: dict[str, str] = {
    "vision_caption": "vision",
    "map_extract": "main_llm",
    "reduce_plan": "main_llm",
    "refine_write": "main_llm",
    "verify_check": "main_llm",
    "digest_summary": "main_llm",
}

_VALID_PHASES = frozenset(PHASE_TO_SLOT.keys())

# Maps slot → (loading_state, active_state, unloading_state)
_SLOT_STATES: dict[str, tuple[RouterState, RouterState, RouterState]] = {
    "vision": (
        RouterState.LOADING_VISION,
        RouterState.VISION_ACTIVE,
        RouterState.UNLOADING_VISION,
    ),
    "main_llm": (
        RouterState.LOADING_MAIN_LLM,
        RouterState.MAIN_LLM_ACTIVE,
        RouterState.UNLOADING_MAIN_LLM,
    ),
}


# ---------------------------------------------------------------------------
# LoadOptions builders
# ---------------------------------------------------------------------------


def _build_load_options(slot: str, config: "LocalAIConfig") -> LoadOptions:
    """Build LoadOptions from config for a given slot and mode.

    MAX mode: full options including gpu_ratio, flash_attention, etc.
    OTHER mode: minimal options — only model_id is used here; LoadOptions
    carries context_length only (LM Studio applies its own defaults for GPU).
    """
    if slot == "vision":
        slot_cfg = config.vision
    else:
        slot_cfg = config.main_llm  # type: ignore[assignment]

    if config.mode == "max":
        opts: dict = {
            "context_length": slot_cfg.context_length,
            "gpu_ratio": slot_cfg.gpu_ratio,
        }
        if slot == "main_llm":
            opts["flash_attention"] = slot_cfg.flash_attention  # type: ignore[union-attr]
            opts["kv_cache_gpu_offload"] = slot_cfg.kv_cache_offload  # type: ignore[union-attr]
            opts["eval_batch_size"] = slot_cfg.eval_batch_size
        else:
            opts["eval_batch_size"] = slot_cfg.eval_batch_size
        return LoadOptions(**opts)
    else:
        # OTHER mode: minimal — just context_length; let LM Studio pick GPU params
        return LoadOptions(context_length=slot_cfg.context_length)


def _model_id_for_slot(slot: str, config: "LocalAIConfig") -> str:
    """Return the primary model_id for the given slot."""
    if slot == "vision":
        return config.vision.model_id
    return config.main_llm.model_id


# ---------------------------------------------------------------------------
# PhaseRouter
# ---------------------------------------------------------------------------


class PhaseRouter:
    """
    Async state machine for LM Studio model lifecycle.

    Guarantees:
      - Only one slot (vision XOR main_llm) loaded at a time.
      - State transitions serialized by ``_lock``.
      - Embedding never touches LMSClient.

    Args:
        lms_client: Any object satisfying LMSClientProtocol.
        embedding_service: In-process sentence-transformers service.
        config: Validated LocalAIConfig snapshot from DB.
    """

    def __init__(
        self,
        lms_client: LMSClientProtocol,
        embedding_service: EmbeddingService,
        config: "LocalAIConfig",
    ) -> None:
        self._lms = lms_client
        self._embedding = embedding_service
        self._config = config
        self._state: RouterState = RouterState.IDLE
        self._current_slot: Optional[str] = None
        self._current_instance_id: Optional[str] = None
        self._lock: asyncio.Lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def state(self) -> RouterState:
        """Current router state (snapshot — may be stale under concurrency)."""
        return self._state

    # ------------------------------------------------------------------
    # Core state machine
    # ------------------------------------------------------------------

    async def ensure_loaded(self, phase: str, source_id: str = "") -> str:
        """Ensure the model for ``phase`` is loaded; return its instance_id.

        If the required slot is already active with the same model, this is a
        no-op and returns the cached instance_id immediately. Otherwise, the
        current slot is unloaded first, then the required slot is loaded.

        Args:
            phase: Phase key (e.g. ``"vision_caption"``, ``"map_extract"``).
            source_id: Opaque job identifier forwarded to LMSClientGuarded for
                OOM counter scoping. Empty string disables per-source tracking.

        Raises:
            ValueError: Unknown phase name.
            AssertionError: Internal invariant violation (both slots loaded).
        """
        if phase not in _VALID_PHASES:
            raise ValueError(
                f"Unknown phase {phase!r}. Valid phases: {sorted(_VALID_PHASES)}"
            )

        required_slot = PHASE_TO_SLOT[phase]

        async with self._lock:
            # Invariant: vision and main_llm cannot both be active.
            active_slots = sum(
                1
                for s in (RouterState.VISION_ACTIVE, RouterState.MAIN_LLM_ACTIVE)
                if self._state == s
            )
            assert active_slots <= 1, (
                f"Invariant violation: both slots appear active (state={self._state})"
            )

            # Already loaded for the correct slot — idempotent no-op.
            if self._current_slot == required_slot and self._current_instance_id:
                logger.debug(
                    "ensure_loaded: slot={} already active (instance_id={})",
                    required_slot,
                    self._current_instance_id,
                )
                return self._current_instance_id

            # Unload current if something is loaded.
            if self._current_slot and self._current_instance_id:
                await self._unload_current()

            # Load required slot.
            instance_id = await self._load_slot(required_slot, source_id=source_id)
            return instance_id

    def reset_source(self, source_id: str) -> None:
        """Clear OOM counters and fallback state for a completed source.

        Delegates to LMSClientGuarded.reset_source when the underlying client
        supports it. Safe to call on plain LMSClient (no-op via hasattr guard).

        Args:
            source_id: The job/source whose state should be cleared.
        """
        if hasattr(self._lms, "reset_source"):
            self._lms.reset_source(source_id)  # type: ignore[union-attr]

    async def run_phase(self, phase: str, *, source_id: str = "", **kwargs) -> str:
        """Run a phase end-to-end: ensure model loaded, build messages, predict.

        Args:
            phase: One of the 6 phase keys.
            **kwargs: Phase-specific payload — see per-phase docs below.

        Phase-specific kwargs:
            vision_caption:
                image_bytes (bytes): Raw image bytes.
                mime_type (str, optional): MIME type, default "image/jpeg".
                prompt (str, optional): Context hint passed to vision template.
            map_extract / reduce_plan / refine_write / verify_check / digest_summary:
                messages (list[dict], optional): Pre-built message list. If not
                    provided, a single user message is built from remaining kwargs.
                Any other kwargs are joined as a user message string if no
                ``messages`` kwarg is given.

        Returns:
            LLM response string.
        """
        instance_id = await self.ensure_loaded(phase, source_id=source_id)
        sampling = self._get_sampling(phase)

        if phase == "vision_caption":
            return await self._run_vision(instance_id, sampling, **kwargs)
        return await self._run_text(phase, instance_id, sampling, **kwargs)

    async def embed(
        self, texts: list[str], task: str = "document"
    ) -> list[list[float]]:
        """Embed texts in-process. Never touches LMSClient.

        Args:
            texts: Texts to embed.
            task: "document" for indexing, "search_query" for queries.

        Returns:
            List of float vectors.
        """
        if task == "search_query":
            if len(texts) == 1:
                vec = await self._embedding.embed_query(texts[0])
                return [vec]
            # Multiple queries — encode one by one preserving prompt prefix
            results = []
            for t in texts:
                results.append(await self._embedding.embed_query(t))
            return results
        return await self._embedding.embed_document(texts)

    async def shutdown(self) -> None:
        """Unload current model and return to IDLE. Safe to call from IDLE."""
        async with self._lock:
            if self._current_slot and self._current_instance_id:
                await self._unload_current()
            self._state = RouterState.IDLE
            logger.info("PhaseRouter: shutdown complete, state=IDLE")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _unload_current(self) -> None:
        """Unload currently loaded instance. Caller must hold ``_lock``."""
        assert self._current_slot is not None
        assert self._current_instance_id is not None

        unload_state = _SLOT_STATES[self._current_slot][2]  # unloading state
        self._state = unload_state
        logger.info(
            "PhaseRouter: unloading slot={} instance_id={} state={}",
            self._current_slot,
            self._current_instance_id,
            self._state,
        )

        try:
            await self._lms.unload(self._current_instance_id)
        except Exception as exc:
            logger.warning(
                "PhaseRouter: unload failed (slot={} instance_id={}): {}",
                self._current_slot,
                self._current_instance_id,
                exc,
            )
        finally:
            prev_slot = self._current_slot
            self._current_slot = None
            self._current_instance_id = None
            self._state = RouterState.IDLE
            logger.info(
                "PhaseRouter: unload complete slot={} state=IDLE", prev_slot
            )

    async def _load_slot(self, slot: str, source_id: str = "") -> str:
        """Load the model for ``slot``. Caller must hold ``_lock``.

        Passes source_id + RAM metadata to LMSClientGuarded when available.
        Falls back to plain signature for LMSClientProtocol-only objects.
        """
        model_id = _model_id_for_slot(slot, self._config)
        load_options = _build_load_options(slot, self._config)
        loading_state, active_state, _ = _SLOT_STATES[slot]

        self._state = loading_state
        logger.info(
            "PhaseRouter: loading slot={} model_id={} state={}",
            slot,
            model_id,
            self._state,
        )

        # Pass RAM metadata when client supports it (LMSClientGuarded).
        # Plain LMSClientProtocol callers (e.g. mocks) only get the base args.
        if isinstance(self._lms, LMSClientGuarded):
            slot_cfg = self._config.vision if slot == "vision" else self._config.main_llm
            instance_id = await self._lms.load(
                model_id,
                load_options,
                source_id=source_id,
                phase=slot,
                estimated_ram_gb=slot_cfg.estimated_ram_gb,
                fallback_model_id=slot_cfg.fallback_model_id,
            )
        else:
            instance_id = await self._lms.load(model_id, load_options)

        self._current_slot = slot
        self._current_instance_id = instance_id
        self._state = active_state
        logger.info(
            "PhaseRouter: load complete slot={} instance_id={} state={}",
            slot,
            instance_id,
            self._state,
        )
        return instance_id

    def _get_sampling(self, phase: str) -> SamplingParams:
        """Build SamplingParams from config + sampling_profiles for this phase/mode."""
        mode = self._config.mode if self._config.mode != "off" else "other"
        profile = get_profile(phase, mode)
        return SamplingParams(
            temperature=profile.temperature,
            top_p=profile.top_p,
            top_k=profile.top_k,
            min_p=profile.min_p,
            repeat_penalty=profile.repeat_penalty,
            response_format_json=(phase == "map_extract"),
        )

    async def _run_vision(
        self, instance_id: str, sampling: SamplingParams, **kwargs
    ) -> str:
        """Build vision messages and predict."""
        from app.ai.local_orchestrator.prompt_templates import vision_caption

        image_bytes: bytes = kwargs.get("image_bytes", b"")
        mime_type: str = kwargs.get("mime_type", "image/jpeg")
        context_hint: str = kwargs.get("prompt", "") or ""

        system_prompt = vision_caption.build(context_hint=context_hint)

        import base64
        b64_data = base64.b64encode(image_bytes).decode("ascii")
        # Build OpenAI-compatible multimodal message
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{b64_data}"},
                    },
                    {"type": "text", "text": "Mô tả hình ảnh này."},
                ],
            },
        ]
        return await self._lms.predict(instance_id, messages, sampling)

    async def _run_text(
        self,
        phase: str,
        instance_id: str,
        sampling: SamplingParams,
        **kwargs,
    ) -> str:
        """Build text messages for a main_llm phase and predict."""
        # Caller may supply pre-built messages list directly
        messages: Optional[list[dict]] = kwargs.get("messages")
        if messages is None:
            # Build a minimal user message from remaining kwargs
            payload_str = " ".join(
                str(v) for k, v in kwargs.items() if k != "sampling"
            )
            messages = [{"role": "user", "content": payload_str}]

        logger.debug(
            "PhaseRouter: run_text phase={} instance_id={} messages={}",
            phase,
            instance_id,
            len(messages),
        )
        return await self._lms.predict(instance_id, messages, sampling)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_router_singleton: Optional[PhaseRouter] = None
_singleton_lock: asyncio.Lock = asyncio.Lock()


def _config_signature(config: "LocalAIConfig") -> tuple:
    """Stable signature for deciding whether the router must be rebuilt."""
    return tuple(sorted(config.model_dump(mode="json").items()))


async def get_router(session: "AsyncSession") -> PhaseRouter:
    """Return the process-wide PhaseRouter singleton.

    Lazy-constructs on first call from DB config. Subsequent calls return the
    cached instance regardless of ``session``.

    Args:
        session: AsyncSession used ONLY on the first construction call.
    """
    global _router_singleton

    config = await load_config(session)

    if (
        _router_singleton is not None
        and _config_signature(_router_singleton._config) == _config_signature(config)
    ):
        return _router_singleton

    async with _singleton_lock:
        # Double-checked locking — another coroutine may have built it.
        if (
            _router_singleton is not None
            and _config_signature(_router_singleton._config) == _config_signature(config)
        ):
            return _router_singleton

        if _router_singleton is not None:
            await _router_singleton.shutdown()
            _router_singleton = None

        lms_client = LMSClientGuarded(
            host=config.lms_host,
            auth_token=config.lms_auth_token,
            default_timeout_s=300.0,
            ram_guard=RAMGuard(headroom_gb=config.ram_headroom_gb),
        )
        embedding_service = EmbeddingService(model_id=config.embedding.model_id)
        _router_singleton = PhaseRouter(
            lms_client=lms_client,
            embedding_service=embedding_service,
            config=config,
        )
        logger.info(
            "PhaseRouter singleton created: mode={} lms_host={}",
            config.mode,
            config.lms_host,
        )

    return _router_singleton


async def reset_router() -> None:
    """Tear down and clear the singleton. Calls shutdown() if loaded.

    For use in tests and config-reload scenarios.
    """
    global _router_singleton

    async with _singleton_lock:
        if _router_singleton is not None:
            try:
                await _router_singleton.shutdown()
            except Exception as exc:
                logger.warning("reset_router: shutdown error ignored: {}", exc)
            finally:
                _router_singleton = None
                logger.info("PhaseRouter singleton reset.")
