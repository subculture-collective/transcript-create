"""Custom vocabulary processor for post-transcription corrections.

Applies user-defined terminology replacements to improve transcript accuracy
for domain-specific terms, proper nouns, acronyms, etc.
"""

import re
from typing import Any, Dict, List, Optional

from app.logging_config import get_logger

logger = get_logger(__name__)


class VocabularyProcessor:
    """Processes transcripts with custom vocabulary corrections."""

    def __init__(self, vocabularies: List[Dict[str, Any]]):
        """Initialize with vocabulary definitions.

        Args:
            vocabularies: List of vocabulary dicts with 'terms' field
                         Each term should have: pattern, replacement, case_sensitive
        """
        self.vocabularies = vocabularies
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile regex patterns from vocabulary terms."""
        self.patterns = []
        for vocab in self.vocabularies:
            terms = vocab.get("terms", [])
            for term in terms:
                pattern = term.get("pattern", "")
                replacement = term.get("replacement", "")
                case_sensitive = term.get("case_sensitive", False)

                if not pattern or not replacement:
                    continue

                try:
                    flags = 0 if case_sensitive else re.IGNORECASE
                    # Use word boundaries for whole-word matching
                    compiled = re.compile(r"\b" + re.escape(pattern) + r"\b", flags)
                    self.patterns.append((compiled, replacement))
                except re.error as e:
                    logger.warning(
                        "Invalid regex pattern in vocabulary",
                        extra={"pattern": pattern, "error": str(e)},
                    )

    def process_text(self, text: str) -> str:
        """Apply vocabulary corrections to text.

        Args:
            text: Original text

        Returns:
            Corrected text with vocabulary replacements applied
        """
        if not text:
            return text

        result = text
        for pattern, replacement in self.patterns:
            result = pattern.sub(replacement, result)

        return result

    def process_segments(self, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply vocabulary corrections to transcript segments.

        Args:
            segments: List of segment dicts with 'text' field

        Returns:
            Segments with corrected text
        """
        corrected = []
        for seg in segments:
            corrected_seg = seg.copy()
            if "text" in corrected_seg:
                original = corrected_seg["text"]
                corrected_text = self.process_text(original)
                corrected_seg["text"] = corrected_text
                if original != corrected_text:
                    logger.debug(
                        "Applied vocabulary correction",
                        extra={"original": original, "corrected": corrected_text},
                    )
            corrected.append(corrected_seg)

        return corrected


def load_vocabularies(conn, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Load applicable vocabularies from database.

    Args:
        conn: Database connection
        user_id: User ID to load user-specific vocabularies (optional)

    Returns:
        List of vocabulary dicts
    """
    from sqlalchemy import text

    vocabularies = []

    # Load global vocabularies
    global_vocabs = (
        conn.execute(
            text("SELECT id, name, terms FROM user_vocabularies WHERE is_global = true"),
        )
        .mappings()
        .all()
    )
    vocabularies.extend(global_vocabs)

    # Load user-specific vocabularies if user_id provided
    if user_id:
        user_vocabs = (
            conn.execute(
                text(
                    "SELECT id, name, terms FROM user_vocabularies WHERE user_id = :uid AND is_global = false"
                ),
                {"uid": user_id},
            )
            .mappings()
            .all()
        )
        vocabularies.extend(user_vocabs)

    logger.info("Loaded vocabularies", extra={"count": len(vocabularies)})
    return [dict(v) for v in vocabularies]


def apply_vocabulary_corrections(
    conn, segments: List[Dict[str, Any]], user_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Apply vocabulary corrections to segments.

    Args:
        conn: Database connection
        segments: Transcript segments
        user_id: Optional user ID for user-specific vocabularies

    Returns:
        Corrected segments
    """
    vocabularies = load_vocabularies(conn, user_id)
    if not vocabularies:
        return segments

    processor = VocabularyProcessor(vocabularies)
    return processor.process_segments(segments)
