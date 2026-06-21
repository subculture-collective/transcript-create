from __future__ import annotations

import re

# Transcript-derived keyphrases are very noisy: caption fragments often turn
# pronouns, contractions, filler, or function-word runs into title-cased labels
# that look valid syntactically but carry no durable archive meaning.
STOP_TERMS = {
    "abi",
    "alright",
    "chat",
    "dude",
    "guys",
    "hasan",
    "hasanabi",
    "hassan",
    "like",
    "okay",
    "people",
    "stream",
    "streams",
    "vod",
    "vods",
    "yeah",
    "youtube",
    "twitch",
    "the",
    "and",
    "a",
    "an",
    "for",
    "to",
    "of",
    "in",
    "on",
    "with",
    "this",
    "that",
    "me",
    "my",
    "it",
    "it's",
    "its",
    "about",
    "able",
    "you",
    "your",
    "i",
    "m",
    "s",
    "re",
    "ve",
    "ll",
    "he",
    "him",
    "his",
    "she",
    "her",
    "we",
    "us",
    "our",
    "them",
    "their",
    "what",
    "not",
    "all",
    "just",
    "know",
    "are",
    "have",
    "but",
    "don",
    "was",
    "there",
    "they",
    "can",
    "one",
    "out",
    "now",
    "think",
    "here",
    "get",
    "because",
    "going",
    "make",
    "makes",
    "talk",
    "talks",
    "talking",
    "keep",
    "actually",
    "really",
    "even",
    "will",
    "fuck",
    "fucking",
    "motherfucker",
    "motherfuckers",
    "is",
    "am",
    "be",
    "been",
    "being",
    "do",
    "does",
    "did",
    "had",
    "has",
    "were",
    "would",
    "could",
    "should",
    "by",
    "as",
    "at",
    "from",
    "into",
    "than",
    "then",
    "if",
    "or",
    "so",
    "also",
    "very",
    "this is",
    "in the",
    "is in",
    "going this",
    "uh",
    "um",
    "uhh",
    "umm",
    "yea",
    "yep",
    "nope",
    "bro",
    "man",
    "dawg",
    "right",
    "oh",
    "uh huh",
    "i mean",
    "you know",
}

_FILLER_TERMS = {
    "ah",
    "eh",
    "erm",
    "hmm",
    "huh",
    "idk",
    "kinda",
    "little",
    "kind of",
    "sort of",
    "literally",
    "maybe",
    "nah",
    "pfft",
    "whatever",
}

# A second layer for short transcript fragments that are not universal stop
# words on their own, but become junk when they appear in tiny extracted
# phrases such as "M So Sorry", "Ll See You", or "No Matter Where".
_TRANSCRIPT_FRAGMENT_TERMS = {
    "ask",
    "bit",
    "go",
    "got",
    "hide",
    "let",
    "matter",
    "no",
    "say",
    "seat",
    "see",
    "shit",
    "sorry",
    "t",
    "thinking",
    "want",
    "wants",
    "watch",
    "when",
    "where",
    "while",
}


def _looks_like_transcript_fragment(terms: list[str]) -> bool:
    weak_terms = STOP_TERMS | _FILLER_TERMS | _TRANSCRIPT_FRAGMENT_TERMS
    return len(terms) <= 3 and all(term in weak_terms for term in terms)


def normalize_label(value: str) -> str:
    cleaned = " ".join(str(value or "").split())
    if not cleaned:
        return ""
    if cleaned.islower():
        return " ".join(part[:1].upper() + part[1:] if part else part for part in cleaned.split(" "))
    return cleaned


def normalized_alias(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())).strip()


def slugify_label(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    return slug or "label"


def is_junk_phrase(value: str) -> bool:
    normalized = normalized_alias(value)
    if not normalized:
        return True
    if len(normalized) < 3:
        return True
    if normalized.replace(" ", "").isdigit():
        return True

    terms = normalized.split()
    if not terms:
        return True

    if normalized in STOP_TERMS or normalized in _FILLER_TERMS:
        return True

    if re.fullmatch(r"\d+\s+(second|seconds|minute|minutes|hour|hours|day|days|week|weeks|month|months|year|years)", normalized):
        return True

    if all(term in STOP_TERMS or term in _FILLER_TERMS for term in terms):
        return True

    if _looks_like_transcript_fragment(terms):
        return True

    if len(terms) == 1 and terms[0] in {"ok", "okay", "yeah", "like", "yep", "nah", "um", "uh"}:
        return True

    return False
