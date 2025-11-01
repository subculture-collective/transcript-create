"""Quality presets for Whisper transcription.

Defines pre-configured quality settings for different use cases:
- fast: Quick transcription with acceptable accuracy
- balanced: Good balance between speed and accuracy (default)
- accurate: Maximum accuracy, slower processing
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class QualitySettings:
    """Quality settings for Whisper transcription."""

    model: str  # Model size: tiny, base, small, medium, large, large-v2, large-v3
    beam_size: int  # Beam size for beam search (1-10)
    temperature: float  # Temperature for sampling (0.0-1.0, 0.0 = greedy)
    best_of: Optional[int] = None  # Number of candidates when temperature > 0
    patience: Optional[float] = None  # Patience for beam search
    vad_filter: bool = False  # Voice Activity Detection filter
    word_timestamps: bool = True  # Extract word-level timestamps


# Predefined quality presets
QUALITY_PRESETS = {
    "fast": QualitySettings(
        model="base",
        beam_size=1,
        temperature=0.0,
        vad_filter=True,
        word_timestamps=False,
    ),
    "balanced": QualitySettings(
        model="large-v3",
        beam_size=5,
        temperature=0.0,
        vad_filter=False,
        word_timestamps=True,
    ),
    "accurate": QualitySettings(
        model="large-v3",
        beam_size=10,
        temperature=0.0,
        patience=2.0,
        vad_filter=False,
        word_timestamps=True,
    ),
}


def get_quality_settings(preset: str = "balanced") -> QualitySettings:
    """Get quality settings for a preset.

    Args:
        preset: Preset name ('fast', 'balanced', 'accurate')

    Returns:
        QualitySettings instance

    Raises:
        ValueError: If preset is not recognized
    """
    if preset not in QUALITY_PRESETS:
        raise ValueError(f"Unknown quality preset: {preset}. Valid presets: {list(QUALITY_PRESETS.keys())}")
    return QUALITY_PRESETS[preset]


def merge_quality_settings(preset: str, overrides: dict) -> QualitySettings:
    """Get quality settings with custom overrides.

    Args:
        preset: Base preset name
        overrides: Dictionary of settings to override

    Returns:
        QualitySettings with overrides applied
    """
    settings = get_quality_settings(preset)
    # Apply overrides
    for key, value in overrides.items():
        if hasattr(settings, key):
            setattr(settings, key, value)
    return settings
