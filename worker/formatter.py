"""
Transcript formatting module with configurable transformations.

Provides deterministic rules-based cleanup, punctuation, segmentation,
and speaker formatting for transcript segments.
"""

import re
import unicodedata
from typing import Any, Dict, List, Optional

from app.logging_config import get_logger
from app.settings import settings

logger = get_logger(__name__)

# Common filler words by aggressiveness level
FILLER_WORDS = {
    1: {"um", "uh", "er", "ah", "hmm", "mhm"},  # Conservative
    2: {"like", "you know", "i mean", "so", "basically", "literally"},  # Moderate
    3: {"kind of", "sort of", "you see", "right", "okay", "well"},  # Aggressive
}

# Sound event tokens to remove
SOUND_EVENT_TOKENS = [
    "[MUSIC]",
    "[APPLAUSE]",
    "[LAUGHTER]",
    "[NOISE]",
    "[INAUDIBLE]",
    "[BLANK_AUDIO]",
    "♪",
    "♫",
]

# Hallucination patterns (common Whisper artifacts)
HALLUCINATION_PATTERNS = [
    r"^(\w+)\s+\1\s+\1\s+\1",  # Repeated word patterns (word repeated 4+ times)
    r"^\s*[\.\,\!\?]+\s*$",  # Only punctuation
    r"^Thank you\.$",  # Common hallucination
    r"^Thanks for watching\.$",
]


class TranscriptFormatter:
    """
    Format transcript segments with configurable transformations.

    Supports:
    - Unicode normalization
    - Whitespace cleanup
    - Special token removal
    - Filler word removal
    - Punctuation restoration
    - Capitalization
    - Sentence segmentation
    - Speaker label formatting
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize formatter with configuration.

        Args:
            config: Optional dict to override settings. If None, uses app settings.
        """
        # Load defaults first
        self.config = self._load_default_config()

        # Override with provided config if any
        if config:
            self.config.update(config)

    def _load_default_config(self) -> Dict[str, Any]:
        """Load configuration from app settings."""
        return {
            "enabled": settings.CLEANUP_ENABLED,
            # Normalization
            "normalize_unicode": settings.CLEANUP_NORMALIZE_UNICODE,
            "normalize_whitespace": settings.CLEANUP_NORMALIZE_WHITESPACE,
            "remove_special_tokens": settings.CLEANUP_REMOVE_SPECIAL_TOKENS,
            "preserve_sound_events": settings.CLEANUP_PRESERVE_SOUND_EVENTS,
            # Punctuation
            "punctuation_mode": settings.CLEANUP_PUNCTUATION_MODE,
            "punctuation_model": settings.CLEANUP_PUNCTUATION_MODEL,
            "add_sentence_punctuation": settings.CLEANUP_ADD_SENTENCE_PUNCTUATION,
            "add_internal_punctuation": settings.CLEANUP_ADD_INTERNAL_PUNCTUATION,
            "capitalize_sentences": settings.CLEANUP_CAPITALIZE_SENTENCES,
            "fix_all_caps": settings.CLEANUP_FIX_ALL_CAPS,
            # Fillers
            "remove_fillers": settings.CLEANUP_REMOVE_FILLERS,
            "filler_level": settings.CLEANUP_FILLER_LEVEL,
            # Segmentation
            "segment_by_sentences": settings.CLEANUP_SEGMENT_BY_SENTENCES,
            "merge_short_segments": settings.CLEANUP_MERGE_SHORT_SEGMENTS,
            "min_segment_length_ms": settings.CLEANUP_MIN_SEGMENT_LENGTH_MS,
            "max_gap_for_merge_ms": settings.CLEANUP_MAX_GAP_FOR_MERGE_MS,
            "speaker_format": settings.CLEANUP_SPEAKER_FORMAT,
            # Advanced
            "detect_hallucinations": settings.CLEANUP_DETECT_HALLUCINATIONS,
            "language_specific_rules": settings.CLEANUP_LANGUAGE_SPECIFIC_RULES,
        }

    def format_segments(self, segments: List[Dict[str, Any]], language: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Format a list of transcript segments.

        Args:
            segments: List of segment dicts with 'text', 'start', 'end', optional 'speaker'
            language: Optional language code for language-specific rules

        Returns:
            List of formatted segments
        """
        if not self.config["enabled"]:
            return segments

        logger.debug(f"Formatting {len(segments)} segments", extra={"language": language})

        # Apply text transformations to each segment
        formatted = []
        for seg in segments:
            formatted_seg = seg.copy()
            text = seg.get("text", "")

            # Apply transformations in order
            if self.config["normalize_unicode"]:
                text = self._normalize_unicode(text)

            if self.config["normalize_whitespace"]:
                text = self._normalize_whitespace(text)

            if self.config["remove_special_tokens"]:
                text = self._remove_special_tokens(text)

            if self.config["detect_hallucinations"]:
                if self._is_hallucination(text):
                    logger.debug(f"Detected hallucination, skipping segment: {text[:50]}")
                    continue

            if self.config["remove_fillers"]:
                text = self._remove_fillers(text)

            if self.config["fix_all_caps"]:
                text = self._fix_all_caps(text)

            # Punctuation and capitalization
            if self.config["punctuation_mode"] == "rule-based":
                if self.config["add_sentence_punctuation"]:
                    text = self._add_sentence_punctuation(text)
                if self.config["add_internal_punctuation"]:
                    text = self._add_internal_punctuation(text)

            if self.config["capitalize_sentences"]:
                text = self._capitalize_sentences(text)

            formatted_seg["text"] = text.strip()
            if formatted_seg["text"]:  # Only include non-empty segments
                formatted.append(formatted_seg)

        # Apply segmentation transformations
        if self.config["segment_by_sentences"]:
            formatted = self._segment_by_sentences(formatted)

        if self.config["merge_short_segments"]:
            formatted = self._merge_short_segments(formatted)

        # Apply speaker formatting
        if self.config["speaker_format"] != "inline":
            formatted = self._format_speakers(formatted)

        logger.info(
            f"Formatted segments: {len(segments)} -> {len(formatted)}",
            extra={"original": len(segments), "formatted": len(formatted)},
        )

        return formatted

    def _normalize_unicode(self, text: str) -> str:
        """Apply Unicode NFC normalization."""
        return unicodedata.normalize("NFC", text)

    def _normalize_whitespace(self, text: str) -> str:
        """Normalize whitespace characters."""
        # Replace various whitespace chars with regular space
        text = re.sub(r"[\t\r\n\u00a0\u2000-\u200b\u202f\u205f\u3000]+", " ", text)
        # Collapse multiple spaces
        text = re.sub(r" {2,}", " ", text)
        return text.strip()

    def _remove_special_tokens(self, text: str) -> str:
        """Remove special sound event tokens."""
        if self.config["preserve_sound_events"]:
            return text

        for token in SOUND_EVENT_TOKENS:
            text = text.replace(token, "")

        return text.strip()

    def _is_hallucination(self, text: str) -> bool:
        """Detect if text is likely a Whisper hallucination."""
        text = text.strip()

        # Empty or too short
        if len(text) < 3:
            return True

        # Match known patterns
        for pattern in HALLUCINATION_PATTERNS:
            if re.match(pattern, text, re.IGNORECASE):
                return True

        return False

    def _remove_fillers(self, text: str) -> str:
        """Remove filler words based on configured aggressiveness."""
        level = self.config["filler_level"]
        if level == 0:
            return text

        # Collect all fillers up to the specified level
        fillers_to_remove = set()
        for i in range(1, min(level + 1, 4)):
            fillers_to_remove.update(FILLER_WORDS.get(i, set()))

        # Build pattern for word boundaries
        pattern = r"\b(" + "|".join(re.escape(f) for f in fillers_to_remove) + r")\b"
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

        # Clean up extra spaces
        text = re.sub(r" {2,}", " ", text)
        return text.strip()

    def _fix_all_caps(self, text: str) -> str:
        """Fix inappropriate all-caps text."""
        # Only fix if entire text is caps and longer than 3 chars
        if len(text) > 3 and text.isupper():
            return text.capitalize()
        return text

    def _add_sentence_punctuation(self, text: str) -> str:
        """Add terminal punctuation if missing."""
        text = text.strip()
        if not text:
            return text

        # Check if already has terminal punctuation
        if text[-1] in ".!?":
            return text

        # Add period
        return text + "."

    def _add_internal_punctuation(self, text: str) -> str:
        """Add commas and internal punctuation (simple heuristics)."""
        # Add comma after common conjunctions if missing
        text = re.sub(r"\b(and|but|so|yet)\s+", r"\1, ", text)

        # Add comma after introductory phrases
        text = re.sub(r"^(however|therefore|thus|meanwhile|furthermore)\s+", r"\1, ", text, flags=re.IGNORECASE)

        return text

    def _capitalize_sentences(self, text: str) -> str:
        """Capitalize first letter of sentences."""
        if not text:
            return text

        # Capitalize first character
        if text[0].islower():
            text = text[0].upper() + text[1:]

        # Capitalize after sentence endings
        text = re.sub(r"([.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)

        return text

    def _segment_by_sentences(self, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Split segments on sentence boundaries."""
        result = []

        for seg in segments:
            text = seg["text"]

            # Simple sentence boundary detection
            sentences = re.split(r"([.!?]+\s+)", text)

            if len(sentences) <= 1:
                result.append(seg)
                continue

            # Calculate time per character for proportional splitting
            duration_ms = seg["end"] - seg["start"]
            chars_total = len(text)
            if chars_total == 0:
                result.append(seg)
                continue

            ms_per_char = duration_ms / chars_total
            current_start = seg["start"]

            # Reconstruct sentences and create segments
            i = 0
            while i < len(sentences):
                sentence = sentences[i]
                if i + 1 < len(sentences) and sentences[i + 1].strip() in [".", "!", "?"]:
                    sentence += sentences[i + 1]
                    i += 2
                else:
                    i += 1

                sentence = sentence.strip()
                if not sentence:
                    continue

                # Calculate end time based on character position
                char_count = len(sentence)
                segment_duration = int(char_count * ms_per_char)
                segment_end = min(current_start + segment_duration, seg["end"])

                new_seg = seg.copy()
                new_seg["text"] = sentence
                new_seg["start"] = current_start
                new_seg["end"] = segment_end

                result.append(new_seg)

                current_start = segment_end

        return result

    def _merge_short_segments(self, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Merge segments that are too short or have small gaps."""
        if not segments:
            return segments

        min_length = self.config["min_segment_length_ms"]
        max_gap = self.config["max_gap_for_merge_ms"]

        result = []
        current = segments[0].copy()

        for i in range(1, len(segments)):
            next_seg = segments[i]

            # Check if should merge
            duration = current["end"] - current["start"]
            gap = next_seg["start"] - current["end"]

            # Check speaker compatibility (don't merge different speakers)
            same_speaker = current.get("speaker") == next_seg.get("speaker")

            # Only merge if no speaker or same speaker
            if current.get("speaker") and next_seg.get("speaker") and not same_speaker:
                should_merge = False
            # Merge if short AND close together
            elif duration < min_length and gap < max_gap:
                should_merge = True
            else:
                should_merge = False

            if should_merge:
                # Merge segments
                current["text"] = current["text"] + " " + next_seg["text"]
                current["end"] = next_seg["end"]
            else:
                result.append(current)
                current = next_seg.copy()

        result.append(current)
        return result

    def _format_speakers(self, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format speaker labels according to configured style."""
        format_style = self.config["speaker_format"]

        if format_style == "inline":
            # Already inline, no changes
            return segments

        elif format_style == "dialogue":
            # Format as dialogue with speaker prefix on new lines
            result = []
            for seg in segments:
                speaker = seg.get("speaker") or seg.get("speaker_label", "Unknown")
                seg_copy = seg.copy()
                seg_copy["text"] = f"{speaker}: {seg['text']}"
                result.append(seg_copy)
            return result

        elif format_style == "structured":
            # Deduplicate consecutive speaker labels
            result = []
            prev_speaker = None

            for seg in segments:
                speaker = seg.get("speaker") or seg.get("speaker_label", "")
                seg_copy = seg.copy()

                # Only add speaker prefix if speaker changed
                if speaker and speaker != prev_speaker:
                    seg_copy["text"] = f"{speaker}: {seg['text']}"
                    prev_speaker = speaker

                result.append(seg_copy)

            return result

        return segments


def format_transcript(
    segments: List[Dict[str, Any]], language: Optional[str] = None, config: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Convenience function to format transcript segments.

    Args:
        segments: List of segment dicts
        language: Optional language code
        config: Optional config dict to override settings

    Returns:
        Formatted segments
    """
    formatter = TranscriptFormatter(config=config)
    return formatter.format_segments(segments, language=language)
