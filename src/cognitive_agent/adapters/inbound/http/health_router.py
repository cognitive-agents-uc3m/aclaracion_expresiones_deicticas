from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from .... import __version__
from ....infrastructure.dependency_injection.container import Container
from .dependencies import get_container

router = APIRouter(tags=["salud"])

@router.get("/healthz")
def liveness():
    return {"status": "ok", "version": __version__}

@router.get("/readyz")
def readiness(response: Response, container: Container = Depends(get_container)):
    health = container.health()
    if not health["ok"]:
        response.status_code = 503
    return {
        "status": "ok" if health["ok"] else "degraded",
        "version": __version__,
        "environment": container.settings.environment,
        **health,
    }

@router.get("/api/config/audio")
def audio_config(container: Container = Depends(get_container)):

    audio = container.settings.audio
    return {
        "vad_energy_threshold": audio.vad_energy_threshold,
        "vad_preroll_seconds": audio.vad_preroll_seconds,
        "vad_silence_seconds": audio.vad_silence_seconds,
        "vad_min_speech_seconds": audio.vad_min_speech_seconds,
        "vad_max_segment_seconds": audio.vad_max_segment_seconds,
        "vad_calibration_seconds": audio.vad_calibration_seconds,
        "vad_threshold_factor": audio.vad_threshold_factor,
        "stt_provider": container.settings.stt.provider,
        "stt_available": bool(getattr(container.stt, "is_available", False)),
    }

@router.get("/api/config/accessibility")
def accessibility_config(container: Container = Depends(get_container)):

    accessibility = container.settings.accessibility
    return {
        "shortcuts": accessibility.shortcuts,
        "live_region_politeness": accessibility.live_region_politeness,
        "clarification_politeness": accessibility.clarification_politeness,
        "sounds_enabled": accessibility.sounds_enabled,
        "announce_slide_changes": accessibility.announce_slide_changes,
        "auto_play_clarifications": container.settings.clarification.auto_play,
        "auto_insert_clarifications": container.settings.notes.auto_insert_clarifications,
        "slide_tag_idle_seconds": container.settings.notes.slide_tag_idle_seconds,
    }
