from __future__ import annotations

import re

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

    if len(terms) == 1 and terms[0] in {"ok", "okay", "yeah", "like", "yep", "nah", "um", "uh"}:
        return True

    return False
