"""
Local AI Orchestrator — Pydantic config schema + KV load/save helpers.

All DB access is gated behind the async helpers. Module-level import triggers
zero DB calls — schemas are plain Pydantic models instantiated from dicts.

KV key layout (all prefixed `local_ai.`):
  local_ai.mode                         "off" | "max" | "other"
  local_ai.lms_host                     LM Studio base URL
  local_ai.lms_auth_token               Bearer token (empty = no auth)
  local_ai.vision.model_id
  local_ai.vision.fallback_model_id
  local_ai.vision.estimated_ram_gb
  local_ai.vision.context_length
  local_ai.vision.eval_batch_size
  local_ai.vision.gpu_ratio
  local_ai.main_llm.model_id
  local_ai.main_llm.fallback_model_id
  local_ai.main_llm.estimated_ram_gb
  local_ai.main_llm.context_length
  local_ai.main_llm.eval_batch_size
  local_ai.main_llm.gpu_ratio
  local_ai.main_llm.flash_attention
  local_ai.main_llm.kv_cache_offload
  local_ai.embedding.model_id
  local_ai.embedding.fallback_model_id
  local_ai.embedding.estimated_ram_gb
  local_ai.ram_headroom_gb
  local_ai.sampling.<phase>.temperature
  local_ai.sampling.<phase>.top_p
  local_ai.sampling.<phase>.top_k        (optional per phase)
  local_ai.sampling.<phase>.min_p        (optional per phase)
  local_ai.sampling.<phase>.repeat_penalty (optional, refine only)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from loguru import logger
from pydantic import BaseModel, field_validator

from app.ai.local_orchestrator.presets import MAX_PRESET, VALID_MODES

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_KV_PREFIX = "local_ai."

# ---------------------------------------------------------------------------
# Sub-schemas
# ---------------------------------------------------------------------------


class VisionConfig(BaseModel):
    model_id: str = MAX_PRESET["vision"]["model_id"]
    fallback_model_id: str = MAX_PRESET["vision"]["fallback_model_id"]
    estimated_ram_gb: float = MAX_PRESET["vision"]["estimated_ram_gb"]
    context_length: int = MAX_PRESET["vision"]["context_length"]
    eval_batch_size: int = MAX_PRESET["vision"]["eval_batch_size"]
    gpu_ratio: float = MAX_PRESET["vision"]["gpu_ratio"]


class MainLLMConfig(BaseModel):
    model_id: str = MAX_PRESET["main_llm"]["model_id"]
    fallback_model_id: str = MAX_PRESET["main_llm"]["fallback_model_id"]
    estimated_ram_gb: float = MAX_PRESET["main_llm"]["estimated_ram_gb"]
    context_length: int = MAX_PRESET["main_llm"]["context_length"]
    eval_batch_size: int = MAX_PRESET["main_llm"]["eval_batch_size"]
    gpu_ratio: float = MAX_PRESET["main_llm"]["gpu_ratio"]
    flash_attention: bool = MAX_PRESET["main_llm"]["flash_attention"]
    kv_cache_offload: bool = MAX_PRESET["main_llm"]["kv_cache_offload"]


class EmbeddingConfig(BaseModel):
    model_id: str = MAX_PRESET["embedding"]["model_id"]
    fallback_model_id: str = MAX_PRESET["embedding"]["fallback_model_id"]
    estimated_ram_gb: float = MAX_PRESET["embedding"]["estimated_ram_gb"]


class SamplingProfile(BaseModel):
    temperature: float
    top_p: float
    top_k: Optional[int] = None
    min_p: Optional[float] = None
    repeat_penalty: Optional[float] = None


class SamplingProfiles(BaseModel):
    refine: SamplingProfile = SamplingProfile(**MAX_PRESET["sampling"]["refine"])
    map: SamplingProfile = SamplingProfile(**MAX_PRESET["sampling"]["map"])
    verify: SamplingProfile = SamplingProfile(**MAX_PRESET["sampling"]["verify"])
    reduce: SamplingProfile = SamplingProfile(**MAX_PRESET["sampling"]["reduce"])
    digest: SamplingProfile = SamplingProfile(**MAX_PRESET["sampling"]["digest"])
    vision: SamplingProfile = SamplingProfile(**MAX_PRESET["sampling"]["vision"])


class LocalAIConfig(BaseModel):
    mode: str = "off"
    lms_host: str = MAX_PRESET["lms_host"]
    lms_auth_token: str = MAX_PRESET["lms_auth_token"]
    ram_headroom_gb: float = MAX_PRESET["ram_headroom_gb"]
    vision: VisionConfig = VisionConfig()
    main_llm: MainLLMConfig = MainLLMConfig()
    embedding: EmbeddingConfig = EmbeddingConfig()
    sampling: SamplingProfiles = SamplingProfiles()

    @field_validator("mode")
    @classmethod
    def _validate_mode(cls, v: str) -> str:
        if v not in VALID_MODES:
            raise ValueError(f"mode must be one of {sorted(VALID_MODES)}, got {v!r}")
        return v

    @classmethod
    def from_max_preset(
        cls,
        preserve_host: str = "",
        preserve_token: str = "",
    ) -> "LocalAIConfig":
        """Return a config seeded from MAX_PRESET with mode='max'.

        preserve_host and preserve_token allow callers (e.g. reset-max endpoint)
        to keep the existing LMS connection settings while resetting all other
        fields to researched MAX defaults.
        """
        config = cls(mode="max")
        if preserve_host:
            config = config.model_copy(update={"lms_host": preserve_host})
        if preserve_token:
            config = config.model_copy(update={"lms_auth_token": preserve_token})
        return config


# ---------------------------------------------------------------------------
# KV flattening helpers
# ---------------------------------------------------------------------------


def _flat_key(suffix: str) -> str:
    return f"{_KV_PREFIX}{suffix}"


def _to_bool(value: str) -> bool:
    return value.lower() in ("true", "1", "yes")


def _config_to_kv(config: LocalAIConfig) -> dict[str, str]:
    """Flatten LocalAIConfig into the `local_ai.*` KV pairs."""
    kv: dict[str, str] = {
        _flat_key("mode"): config.mode,
        _flat_key("lms_host"): config.lms_host,
        _flat_key("lms_auth_token"): config.lms_auth_token,
        _flat_key("ram_headroom_gb"): str(config.ram_headroom_gb),
        # vision
        _flat_key("vision.model_id"): config.vision.model_id,
        _flat_key("vision.fallback_model_id"): config.vision.fallback_model_id,
        _flat_key("vision.estimated_ram_gb"): str(config.vision.estimated_ram_gb),
        _flat_key("vision.context_length"): str(config.vision.context_length),
        _flat_key("vision.eval_batch_size"): str(config.vision.eval_batch_size),
        _flat_key("vision.gpu_ratio"): str(config.vision.gpu_ratio),
        # main_llm
        _flat_key("main_llm.model_id"): config.main_llm.model_id,
        _flat_key("main_llm.fallback_model_id"): config.main_llm.fallback_model_id,
        _flat_key("main_llm.estimated_ram_gb"): str(config.main_llm.estimated_ram_gb),
        _flat_key("main_llm.context_length"): str(config.main_llm.context_length),
        _flat_key("main_llm.eval_batch_size"): str(config.main_llm.eval_batch_size),
        _flat_key("main_llm.gpu_ratio"): str(config.main_llm.gpu_ratio),
        _flat_key("main_llm.flash_attention"): str(config.main_llm.flash_attention).lower(),
        _flat_key("main_llm.kv_cache_offload"): str(config.main_llm.kv_cache_offload).lower(),
        # embedding
        _flat_key("embedding.model_id"): config.embedding.model_id,
        _flat_key("embedding.fallback_model_id"): config.embedding.fallback_model_id,
        _flat_key("embedding.estimated_ram_gb"): str(config.embedding.estimated_ram_gb),
    }
    # sampling profiles
    for phase_name in ("refine", "map", "verify", "reduce", "digest", "vision"):
        profile: SamplingProfile = getattr(config.sampling, phase_name)
        kv[_flat_key(f"sampling.{phase_name}.temperature")] = str(profile.temperature)
        kv[_flat_key(f"sampling.{phase_name}.top_p")] = str(profile.top_p)
        if profile.top_k is not None:
            kv[_flat_key(f"sampling.{phase_name}.top_k")] = str(profile.top_k)
        if profile.min_p is not None:
            kv[_flat_key(f"sampling.{phase_name}.min_p")] = str(profile.min_p)
        if profile.repeat_penalty is not None:
            kv[_flat_key(f"sampling.{phase_name}.repeat_penalty")] = str(profile.repeat_penalty)
    return kv


def _kv_to_config(kv: dict[str, Optional[str]]) -> LocalAIConfig:
    """Assemble LocalAIConfig from a flat KV dict. Missing keys use schema defaults."""

    def _get(suffix: str) -> Optional[str]:
        return kv.get(_flat_key(suffix))

    def _sampling_for(phase: str) -> SamplingProfile:
        defaults = MAX_PRESET["sampling"][phase]
        temp_raw = _get(f"sampling.{phase}.temperature")
        top_p_raw = _get(f"sampling.{phase}.top_p")
        top_k_raw = _get(f"sampling.{phase}.top_k")
        min_p_raw = _get(f"sampling.{phase}.min_p")
        rp_raw = _get(f"sampling.{phase}.repeat_penalty")
        return SamplingProfile(
            temperature=float(temp_raw) if temp_raw else defaults["temperature"],
            top_p=float(top_p_raw) if top_p_raw else defaults["top_p"],
            top_k=int(top_k_raw) if top_k_raw else defaults.get("top_k"),
            min_p=float(min_p_raw) if min_p_raw else defaults.get("min_p"),
            repeat_penalty=float(rp_raw) if rp_raw else defaults.get("repeat_penalty"),
        )

    mode_raw = _get("mode") or "off"
    vision_ctx = _get("vision.context_length")
    vision_batch = _get("vision.eval_batch_size")
    vision_gpu = _get("vision.gpu_ratio")
    vision_ram = _get("vision.estimated_ram_gb")
    main_ctx = _get("main_llm.context_length")
    main_batch = _get("main_llm.eval_batch_size")
    main_gpu = _get("main_llm.gpu_ratio")
    main_fa = _get("main_llm.flash_attention")
    main_kvo = _get("main_llm.kv_cache_offload")
    main_ram = _get("main_llm.estimated_ram_gb")
    embed_ram = _get("embedding.estimated_ram_gb")
    headroom_raw = _get("ram_headroom_gb")

    vision = VisionConfig(
        model_id=_get("vision.model_id") or MAX_PRESET["vision"]["model_id"],
        fallback_model_id=_get("vision.fallback_model_id") or MAX_PRESET["vision"]["fallback_model_id"],
        estimated_ram_gb=float(vision_ram) if vision_ram else MAX_PRESET["vision"]["estimated_ram_gb"],
        context_length=int(vision_ctx) if vision_ctx else MAX_PRESET["vision"]["context_length"],
        eval_batch_size=int(vision_batch) if vision_batch else MAX_PRESET["vision"]["eval_batch_size"],
        gpu_ratio=float(vision_gpu) if vision_gpu else MAX_PRESET["vision"]["gpu_ratio"],
    )
    main_llm = MainLLMConfig(
        model_id=_get("main_llm.model_id") or MAX_PRESET["main_llm"]["model_id"],
        fallback_model_id=_get("main_llm.fallback_model_id") or MAX_PRESET["main_llm"]["fallback_model_id"],
        estimated_ram_gb=float(main_ram) if main_ram else MAX_PRESET["main_llm"]["estimated_ram_gb"],
        context_length=int(main_ctx) if main_ctx else MAX_PRESET["main_llm"]["context_length"],
        eval_batch_size=int(main_batch) if main_batch else MAX_PRESET["main_llm"]["eval_batch_size"],
        gpu_ratio=float(main_gpu) if main_gpu else MAX_PRESET["main_llm"]["gpu_ratio"],
        flash_attention=_to_bool(main_fa) if main_fa else MAX_PRESET["main_llm"]["flash_attention"],
        kv_cache_offload=_to_bool(main_kvo) if main_kvo else MAX_PRESET["main_llm"]["kv_cache_offload"],
    )
    embedding = EmbeddingConfig(
        model_id=_get("embedding.model_id") or MAX_PRESET["embedding"]["model_id"],
        fallback_model_id=_get("embedding.fallback_model_id") or MAX_PRESET["embedding"]["fallback_model_id"],
        estimated_ram_gb=float(embed_ram) if embed_ram else MAX_PRESET["embedding"]["estimated_ram_gb"],
    )
    sampling = SamplingProfiles(
        refine=_sampling_for("refine"),
        map=_sampling_for("map"),
        verify=_sampling_for("verify"),
        reduce=_sampling_for("reduce"),
        digest=_sampling_for("digest"),
        vision=_sampling_for("vision"),
    )

    return LocalAIConfig(
        mode=mode_raw,
        lms_host=_get("lms_host") or MAX_PRESET["lms_host"],
        lms_auth_token=_get("lms_auth_token") or MAX_PRESET["lms_auth_token"],
        ram_headroom_gb=float(headroom_raw) if headroom_raw else MAX_PRESET["ram_headroom_gb"],
        vision=vision,
        main_llm=main_llm,
        embedding=embedding,
        sampling=sampling,
    )


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------


async def load_config(session: "AsyncSession") -> LocalAIConfig:
    """Read all local_ai.* KV rows and return a validated LocalAIConfig."""
    from app.services.config_service import ConfigService

    svc = ConfigService(session)
    # Fetch every known key in a single logical pass (N individual selects via
    # ConfigService.get — acceptable for ~25 keys, no batch API needed).
    kv_keys = list(_config_to_kv(LocalAIConfig()).keys())
    raw: dict[str, Optional[str]] = {}
    for key in kv_keys:
        raw[key] = await svc.get(key)

    config = _kv_to_config(raw)
    logger.debug("local_ai config loaded: mode={}", config.mode)
    return config


async def save_config(session: "AsyncSession", config: LocalAIConfig) -> None:
    """Upsert all local_ai.* KV rows from the given config."""
    from app.services.config_service import ConfigService

    svc = ConfigService(session)
    kv = _config_to_kv(config)
    for key, value in kv.items():
        await svc.set(key, value)
    logger.debug("local_ai config saved: mode={}, {} keys written", config.mode, len(kv))


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def is_max_mode(config: LocalAIConfig) -> bool:
    """Return True when the orchestrator is in MAX mode (full tuning active)."""
    return config.mode == "max"
