"""Emplacements de variantes, compatibles avec les anciens WebP Cloudflare.

IMPORTANT : les images des anciennes versions restent au chemin lots/ inchangé.
"""
from pathlib import Path


def state_for(state: Path, engine: str) -> Path:
    return state if engine == 'cloudflare' else state / 'collections' / engine


def available_states(state, engines):
    return [(engine, state_for(state, engine)) for engine in engines]
