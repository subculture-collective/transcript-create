from __future__ import annotations

from collections import Counter, defaultdict
import re

from app.archive.intelligence_repository import alias_matches_text

from .normalization import is_junk_phrase, normalize_label, normalized_alias
from .types import LabelCandidate


def _ngrams(text: str, max_words: int = 3, max_tokens: int = 400) -> list[str]:
    words = [word for word in normalized_alias(text).split() if word][:max_tokens]
    phrases: list[str] = []
    seen: set[str] = set()

    for size in range(1, max_words + 1):
        for idx in range(0, max(0, len(words) - size + 1)):
            phrase = " ".join(words[idx : idx + size])
            if phrase in seen or is_junk_phrase(phrase):
                continue
            seen.add(phrase)
            phrases.append(phrase)

    return phrases


def extract_keyphrase_candidates(
    windows: list[dict],
    min_distinct_videos: int = 3,
    min_occurrences: int = 5,
) -> list[LabelCandidate]:
    counts: Counter[str] = Counter()
    videos_by_phrase: dict[str, set[str]] = defaultdict(set)
    evidence_by_phrase: dict[str, list[dict]] = defaultdict(list)

    for window in windows:
        video_id = str(window.get("video_id") or "")
        window_id = str(window.get("id") or "")
        start_ms = int(window.get("start_ms") or 0)
        end_ms = int(window.get("end_ms") or 0)
        snippet = str(window.get("text") or "")[:300]

        for phrase in _ngrams(str(window.get("text") or ""), max_words=3):
            counts[phrase] += 1
            videos_by_phrase[phrase].add(video_id)
            if len(evidence_by_phrase[phrase]) < 5:
                evidence_by_phrase[phrase].append(
                    {
                        "window_id": window_id,
                        "video_id": video_id,
                        "start_ms": start_ms,
                        "end_ms": end_ms,
                        "snippet": snippet,
                        "extractor": "keyphrase",
                    }
                )

    candidates: list[LabelCandidate] = []
    for phrase, count in counts.items():
        distinct_videos = len(videos_by_phrase[phrase])
        if count < min_occurrences or distinct_videos < min_distinct_videos:
            continue

        confidence = min(0.88, 0.30 + (0.10 * distinct_videos) + (0.04 * count))
        candidates.append(
            LabelCandidate(
                label=normalize_label(phrase),
                kind="topic",
                aliases=(phrase,),
                confidence_score=confidence,
                component_scores={"occurrences": float(count), "distinct_videos": float(distinct_videos)},
                evidence=tuple(evidence_by_phrase[phrase]),
            )
        )

    return sorted(
        candidates,
        key=lambda candidate: (-candidate.confidence_score, -candidate.component_scores.get("distinct_videos", 0.0), -candidate.component_scores.get("occurrences", 0.0), candidate.label),
    )


def extract_alias_candidates(windows: list[dict], aliases: list[dict]) -> list[LabelCandidate]:
    evidence_by_label: dict[str, list[dict]] = defaultdict(list)
    alias_terms_by_label: dict[str, set[str]] = defaultdict(set)
    label_rows: dict[str, dict] = {}

    for alias_row in aliases:
        label_id = str(alias_row.get("label_id") or "")
        if not label_id:
            continue

        status = alias_row.get("status")
        if status is not None and str(status).lower() != "active":
            continue
        if bool(alias_row.get("is_ambiguous")):
            continue

        alias_value = normalized_alias(str(alias_row.get("alias") or ""))
        if not alias_value or is_junk_phrase(alias_value):
            continue

        label_rows[label_id] = alias_row
        alias_terms_by_label[label_id].add(alias_value)

    for window in windows:
        text = str(window.get("text") or "")
        lowered_text = text.lower()
        window_id = str(window.get("id") or "")
        video_id = str(window.get("video_id") or "")
        start_ms = int(window.get("start_ms") or 0)
        end_ms = int(window.get("end_ms") or 0)
        snippet = text[:300]

        for label_id in sorted(alias_terms_by_label):
            matches = sorted(term for term in alias_terms_by_label[label_id] if alias_matches_text(term, lowered_text))
            if not matches:
                continue
            if len(evidence_by_label[label_id]) >= 10:
                continue
            evidence_by_label[label_id].append(
                {
                    "window_id": window_id,
                    "video_id": video_id,
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "snippet": snippet,
                    "extractor": "alias",
                    "matched_alias": matches[0],
                }
            )

    candidates: list[LabelCandidate] = []
    for label_id, evidence in evidence_by_label.items():
        row = label_rows[label_id]
        alias_terms = tuple(sorted(alias_terms_by_label[label_id]))
        evidence_count = len(evidence)
        distinct_videos = len({item["video_id"] for item in evidence})
        confidence = min(0.98, 0.72 + (0.05 * min(evidence_count, 5)) + (0.03 * min(len(alias_terms), 5)) + (0.02 * min(distinct_videos, 5)))

        candidates.append(
            LabelCandidate(
                label=normalize_label(str(row.get("label") or label_id)),
                kind=str(row.get("kind") or "topic"),
                aliases=alias_terms,
                confidence_score=confidence,
                component_scores={
                    "evidence_count": float(evidence_count),
                    "alias_count": float(len(alias_terms)),
                    "distinct_videos": float(distinct_videos),
                },
                evidence=tuple(evidence),
            )
        )

    return sorted(
        candidates,
        key=lambda candidate: (-candidate.confidence_score, -candidate.component_scores.get("evidence_count", 0.0), candidate.label),
    )


TITLE_PERSON_STOPWORDS = {
    "ALT",
    "CNN",
    "DELETED VOD",
    "Hasan",
    "HasanAbi",
    "Hasan Piker",
    "Instagram Stories Compilation",
    "LIVE",
    "VOD",
    "WIRED Politics Lab",
}
TITLE_PERSON_REJECT_TERMS = {
    "ayatollah",
    "advisor",
    "blockade",
    "cnn",
    "correspondents",
    "crime",
    "currents",
    "day",
    "deleted",
    "dood",
    "fbi",
    "fox",
    "ice",
    "inside politics",
    "jersey",
    "lab",
    "news",
    "no stream",
    "politics",
    "stream today",
    "true crime",
    "vod",
    "warrant",
    "white house",
}


def _title_alias_rows(aliases: list[dict]) -> tuple[dict[str, dict], dict[str, set[str]]]:
    label_rows: dict[str, dict] = {}
    alias_terms_by_label: dict[str, set[str]] = defaultdict(set)
    for alias_row in aliases:
        label_id = str(alias_row.get("label_id") or "")
        if not label_id:
            continue
        status = alias_row.get("status")
        if status is not None and str(status).lower() != "active":
            continue
        if bool(alias_row.get("is_ambiguous")):
            continue
        alias_value = normalized_alias(str(alias_row.get("alias") or ""))
        if not alias_value or is_junk_phrase(alias_value):
            continue
        label_rows[label_id] = alias_row
        alias_terms_by_label[label_id].add(alias_value)
    return label_rows, alias_terms_by_label


def extract_title_alias_candidates(video: dict, aliases: list[dict]) -> list[LabelCandidate]:
    title = str(video.get("title") or "").strip()
    video_id = str(video.get("id") or video.get("video_id") or "")
    if not title or not video_id:
        return []

    lowered_title = title.lower()
    label_rows, alias_terms_by_label = _title_alias_rows(aliases)
    candidates: list[LabelCandidate] = []
    for label_id in sorted(alias_terms_by_label):
        matches = sorted(term for term in alias_terms_by_label[label_id] if alias_matches_text(term, lowered_title))
        if not matches:
            continue
        row = label_rows[label_id]
        candidates.append(
            LabelCandidate(
                label=normalize_label(str(row.get("label") or label_id)),
                kind=str(row.get("kind") or "topic"),
                aliases=tuple(sorted(alias_terms_by_label[label_id])),
                confidence_score=0.97,
                component_scores={"title_match": 1.0, "alias_count": float(len(alias_terms_by_label[label_id]))},
                evidence=(
                    {
                        "video_id": video_id,
                        "start_ms": 0,
                        "end_ms": 0,
                        "snippet": title[:300],
                        "extractor": "title",
                        "matched_alias": matches[0],
                        "title": title,
                    },
                ),
            )
        )
    return sorted(candidates, key=lambda candidate: (-candidate.confidence_score, candidate.label))


def _title_candidate_text(title: str) -> str:
    text = re.sub(r"\[[^\]]*\]", " ", title)
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", " ", text)
    text = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", " ", text)
    text = re.sub(r"\b(?:Jan|Feb|Mar|Apr|April|May|Jun|June|Jul|July|Aug|Sept?|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:HasanAbi|Hasan Piker|Hasan)\b", " ", text)
    return text


def suggest_person_names_from_title(title: str) -> list[str]:
    text = _title_candidate_text(title)
    candidates: list[str] = []
    patterns = [
        r"\b(?:with|ft\.?|featuring|guest|visits?|interviews?|talking (?:with|to))\s+([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){0,3})",
        r"\b([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3})\b",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            name = " ".join(match.group(1).replace("–", " ").replace("-", " ").split())
            if len(name) < 4 or name in TITLE_PERSON_STOPWORDS:
                continue
            if any(name.startswith(stop) or name.endswith(stop) for stop in TITLE_PERSON_STOPWORDS):
                continue
            lowered_name = name.lower()
            if name.isupper() or any(term in lowered_name for term in TITLE_PERSON_REJECT_TERMS):
                continue
            if lowered_name.startswith("in "):
                continue
            if name not in candidates:
                candidates.append(name)
    return candidates


def suggest_person_names_from_titles(rows: list[dict]) -> list[dict]:
    grouped: dict[str, dict] = {}
    for row in rows:
        title = str(row.get("title") or "")
        for name in suggest_person_names_from_title(title):
            item = grouped.setdefault(name, {"name": name, "count": 0, "titles": []})
            item["count"] += 1
            if len(item["titles"]) < 5:
                item["titles"].append({"video_id": str(row.get("id") or row.get("video_id") or ""), "title": title})
    return sorted(grouped.values(), key=lambda item: (-int(item["count"]), str(item["name"])))
