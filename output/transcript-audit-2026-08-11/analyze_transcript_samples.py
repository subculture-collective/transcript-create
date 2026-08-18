from __future__ import annotations

import csv
import json
import math
import re
import subprocess
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


OUTPUT_DIR = Path(__file__).resolve().parent
SAMPLE_COUNT = 40
POSITIONS = (0.05, 0.27, 0.50, 0.73, 0.95)

SAMPLE_SQL = r"""
WITH eligible AS (
    SELECT
        v.id,
        v.youtube_id,
        v.title,
        v.uploaded_at,
        v.duration_seconds,
        ntile(40) OVER (ORDER BY v.uploaded_at, v.id) AS time_bucket
    FROM videos v
    WHERE v.state = 'completed'
      AND v.uploaded_at IS NOT NULL
      AND v.duration_seconds >= 600
      AND EXISTS (SELECT 1 FROM segments s WHERE s.video_id = v.id)
      AND EXISTS (SELECT 1 FROM youtube_transcripts yt WHERE yt.video_id = v.id)
), sampled AS (
    SELECT *, row_number() OVER (PARTITION BY time_bucket ORDER BY md5(id::text)) AS bucket_row
    FROM eligible
), positions(position_label, position_ratio) AS (
    VALUES ('early', 0.05::numeric), ('first_quarter', 0.27::numeric),
           ('middle', 0.50::numeric), ('third_quarter', 0.73::numeric), ('late', 0.95::numeric)
), targets AS (
    SELECT
        s.*,
        p.position_label,
        p.position_ratio,
        round(s.duration_seconds * 1000 * p.position_ratio)::integer AS target_ms
    FROM sampled s CROSS JOIN positions p
    WHERE s.bucket_row = 1
)
SELECT json_build_object(
    'video_id', t.id,
    'youtube_id', t.youtube_id,
    'title', t.title,
    'uploaded_at', t.uploaded_at,
    'duration_seconds', t.duration_seconds,
    'position_label', t.position_label,
    'position_ratio', t.position_ratio,
    'target_ms', t.target_ms,
    'window_start_ms', greatest(0, t.target_ms - 30000),
    'window_end_ms', least(t.duration_seconds * 1000, t.target_ms + 30000),
    'native_start_ms', native.native_start_ms,
    'native_end_ms', native.native_end_ms,
    'native_text', coalesce(native.native_text, ''),
    'native_segment_count', coalesce(native.native_segment_count, 0),
    'native_hallucination_count', coalesce(native.native_hallucination_count, 0),
    'native_avg_logprob', native.native_avg_logprob,
    'youtube_start_ms', captions.youtube_start_ms,
    'youtube_end_ms', captions.youtube_end_ms,
    'youtube_text', coalesce(captions.youtube_text, ''),
    'youtube_segment_count', coalesce(captions.youtube_segment_count, 0)
)::text
FROM targets t
LEFT JOIN LATERAL (
    SELECT
        min(s.start_ms) AS native_start_ms,
        max(s.end_ms) AS native_end_ms,
        left(string_agg(s.text, ' ' ORDER BY s.start_ms), 4000) AS native_text,
        count(*) AS native_segment_count,
        count(*) FILTER (WHERE s.likely_hallucination = true) AS native_hallucination_count,
        avg(s.avg_logprob) AS native_avg_logprob
    FROM segments s
    WHERE s.video_id = t.id
      AND s.end_ms >= greatest(0, t.target_ms - 30000)
      AND s.start_ms <= least(t.duration_seconds * 1000, t.target_ms + 30000)
) native ON true
LEFT JOIN LATERAL (
    SELECT
        min(ys.start_ms) AS youtube_start_ms,
        max(ys.end_ms) AS youtube_end_ms,
        left(string_agg(ys.text, ' ' ORDER BY ys.start_ms), 4000) AS youtube_text,
        count(*) AS youtube_segment_count
    FROM youtube_transcripts yt
    JOIN youtube_segments ys ON ys.youtube_transcript_id = yt.id
    WHERE yt.video_id = t.id
      AND ys.end_ms >= greatest(0, t.target_ms - 30000)
      AND ys.start_ms <= least(t.duration_seconds * 1000, t.target_ms + 30000)
) captions ON true
ORDER BY t.uploaded_at, t.youtube_id, t.position_ratio;
"""

PEOPLE_SQL = "SELECT json_build_object('display_name', display_name, 'aliases', aliases)::text FROM archive_people ORDER BY display_name;"

TOKEN_RE = re.compile(r"[\w']+", re.UNICODE)
NON_LATIN_RE = re.compile(r"[^\x00-\x7f]")
NAME_TOKEN = r"(?:[A-Z][a-z]+(?:[-'][A-Z][a-z]+)?|[A-Z]{2,})"
CAPITALIZED_SEQUENCE_RE = re.compile(rf"\b{NAME_TOKEN}(?:\s+(?:(?:de|van|von|al|bin)\s+)?{NAME_TOKEN}){{1,3}}\b")
NAME_STOPWORDS = {
    "And This",
    "All The",
    "At The",
    "But The",
    "For The",
    "From The",
    "He Was",
    "I Am",
    "I Hope",
    "If You",
    "In The",
    "It Is",
    "No Matter",
    "Of The",
    "On The",
    "Thank You",
    "That Is",
    "The First",
    "The New",
    "The Other",
    "The United",
    "There Is",
    "They Are",
    "This Is",
    "We Are",
    "We Have",
    "What Is",
    "When You",
    "You Are",
}
CONTRACTION_PREFIXES = ("I'm ", "It's ", "We're ", "We've ", "That's ", "There's ", "They're ", "You'll ")
LEADING_CANDIDATE_WORDS = {"After", "Against", "And", "Apparently", "Assessing", "But", "Does", "During", "One", "The", "TV", "We"}
TRAILING_CANDIDATE_WORDS = {"All", "Also", "He", "She", "This", "Today"}
HALLUCINATION_PHRASES = (
    "thank you for watching",
    "thanks for watching",
    "subscribe to the channel",
    "subtitles by",
    "inaudible",
    "you you you",
)
NAME_LEAD_ASSESSMENTS = {
    "Abdul El Sayed": "normalization only; verify preferred hyphenation",
    "Austin": "alias, not necessarily an error; spoken first name may be correct",
    "Emma Vigland": "likely spelling error",
    "Bradley Martin": "likely spelling error",
    "Carl Marx": "likely spelling error",
    "New Yorker": "likely false fuzzy match",
    "Aiden Ross": "likely spelling error",
    "Alex Prey": "possible spelling error; context check required",
    "New Yorkers": "likely false fuzzy match",
    "Bernard Sanders": "likely correct legal name in this context",
    "World War": "likely false fuzzy match",
}


def psql_json_lines(sql: str) -> list[dict[str, Any]]:
    result = subprocess.run(
        ["docker", "exec", "hasanara-db", "psql", "-X", "-U", "postgres", "-d", "transcripts", "-At", "-c", sql],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def normalize_tokens(text: str) -> list[str]:
    return [token.casefold() for token in TOKEN_RE.findall(text)]


def similarity(left: str, right: str) -> float | None:
    left_tokens = normalize_tokens(left)
    right_tokens = normalize_tokens(right)
    if not left_tokens or not right_tokens:
        return None
    return SequenceMatcher(None, left_tokens, right_tokens, autojunk=False).ratio()


def repetition_share(text: str) -> float:
    tokens = normalize_tokens(text)
    if not tokens:
        return 0.0
    return Counter(tokens).most_common(1)[0][1] / len(tokens)


def non_latin_share(text: str) -> float:
    letters = [character for character in text if character.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for character in letters if NON_LATIN_RE.search(character)) / len(letters)


def excerpt(text: str, limit: int = 520) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact if len(compact) <= limit else compact[: limit - 1].rstrip() + "…"


def contextual_excerpt(text: str, needle: str, limit: int = 300) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    match = re.search(re.escape(needle), compact, re.IGNORECASE)
    if not match:
        return excerpt(compact, limit)
    half = max(40, (limit - len(needle)) // 2)
    start = max(0, match.start() - half)
    end = min(len(compact), match.end() + half)
    prefix = "…" if start else ""
    suffix = "…" if end < len(compact) else ""
    return prefix + compact[start:end].strip() + suffix


def timestamp(milliseconds: int | None) -> str:
    seconds = max(0, int((milliseconds or 0) / 1000))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def canonical_people(rows: list[dict[str, Any]]) -> tuple[dict[str, str], list[str]]:
    alias_to_name: dict[str, str] = {}
    aliases: list[str] = []
    for row in rows:
        display = row["display_name"]
        forms = [display]
        for alias in row.get("aliases") or []:
            alias = str(alias).strip()
            # Archive aliases were originally built for title matching and can
            # include generic first names or editorial phrases such as REACT.
            # Keep only forms specific enough to be useful inside prose.
            if re.search(r"\b(?:react|full|calls|turns|tweets|pod|mega|based)\b", alias, re.IGNORECASE):
                continue
            if " " not in alias and " " in display:
                continue
            forms.append(alias)
        for form in forms:
            normalized = str(form).strip()
            if normalized:
                alias_to_name[normalized.casefold()] = display
                aliases.append(normalized)
    return alias_to_name, sorted(set(aliases), key=len, reverse=True)


def find_names(text: str, alias_to_name: dict[str, str], aliases: list[str]) -> list[tuple[str, str, str]]:
    found: dict[tuple[str, str], tuple[str, str, str]] = {}
    for alias in aliases:
        if re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", text, re.IGNORECASE):
            canonical = alias_to_name[alias.casefold()]
            found[(canonical.casefold(), alias.casefold())] = (canonical, alias, "canonical_or_alias")
    for candidate in CAPITALIZED_SEQUENCE_RE.findall(text):
        candidate = re.sub(r"\s+", " ", candidate).strip(" .,!?;:\"'")
        words = candidate.split()
        while len(words) > 2 and words[0] in LEADING_CANDIDATE_WORDS:
            words.pop(0)
        while len(words) > 2 and words[-1] in TRAILING_CANDIDATE_WORDS:
            words.pop()
        candidate = " ".join(words)
        if candidate in NAME_STOPWORDS or candidate.startswith(CONTRACTION_PREFIXES) or len(candidate) < 5:
            continue
        key = (candidate.casefold(), candidate.casefold())
        if any(candidate.casefold() == alias.casefold() for alias in aliases):
            continue
        found[key] = (candidate, candidate, "unverified_candidate")
    return sorted(found.values())


def load_title_reference_names() -> list[str]:
    source = OUTPUT_DIR.parents[1] / "people-from-titles.json"
    rows = json.loads(source.read_text(encoding="utf-8"))
    return [str(row["name"]).strip() for row in rows if isinstance(row, dict) and row.get("name")]


def best_reference_match(observed: str, references: list[str]) -> tuple[str, float]:
    observed_tokens = normalize_tokens(observed)
    best_name = ""
    best_score = 0.0
    for reference in references:
        reference_tokens = normalize_tokens(reference)
        if len(reference_tokens) != len(observed_tokens):
            continue
        score = SequenceMatcher(None, observed.casefold(), reference.casefold(), autojunk=False).ratio()
        if score > best_score:
            best_name = reference
            best_score = score
    return best_name, best_score


def likely_spelling_variant(canonical: str, observed: str) -> bool:
    if canonical.casefold() == observed.casefold():
        return False
    canonical_tokens = normalize_tokens(canonical)
    observed_tokens = normalize_tokens(observed)
    return len(canonical_tokens) == len(observed_tokens) and SequenceMatcher(
        None, canonical.casefold(), observed.casefold(), autojunk=False
    ).ratio() >= 0.72


def notable_differences(native: str, captions: str, limit: int = 5) -> str:
    native_tokens = TOKEN_RE.findall(native)
    caption_tokens = TOKEN_RE.findall(captions)
    matcher = SequenceMatcher(
        None,
        [token.casefold() for token in native_tokens],
        [token.casefold() for token in caption_tokens],
        autojunk=False,
    )
    differences: list[str] = []
    for operation, left_start, left_end, right_start, right_end in matcher.get_opcodes():
        if operation != "replace":
            continue
        left = " ".join(native_tokens[left_start:left_end])
        right = " ".join(caption_tokens[right_start:right_end])
        if not left or not right or len(left.split()) > 7 or len(right.split()) > 7:
            continue
        if {left.casefold(), right.casefold()} <= {"fuck", "shit", "__"}:
            continue
        differences.append(f"{left} → {right}")
        if len(differences) >= limit:
            break
    return "; ".join(differences)


def issue_flags(row: dict[str, Any], known_alias_hits: list[tuple[str, str, str]]) -> tuple[list[str], int, float | None]:
    native = row["native_text"]
    captions = row["youtube_text"]
    score = 0
    issues: list[str] = []
    agreement = similarity(native, captions)
    native_tokens = normalize_tokens(native)
    caption_tokens = normalize_tokens(captions)

    if non_latin_share(native) >= 0.08:
        issues.append("non-Latin transcription")
        score += 5
    if len(native_tokens) >= 12 and repetition_share(native) >= 0.32:
        issues.append("heavy repetition")
        score += 4
    if any(phrase in native.casefold() for phrase in HALLUCINATION_PHRASES):
        issues.append("known hallucination phrase")
        score += 3
    if row["native_hallucination_count"]:
        issues.append("pipeline hallucination flag")
        score += 3
    if caption_tokens and not native_tokens:
        issues.append("Whisper missed captioned speech")
        score += 5
    elif len(caption_tokens) >= 8 and len(native_tokens) >= 8 and agreement is not None and agreement < 0.20:
        issues.append("strong caption disagreement")
        score += 4
    elif len(caption_tokens) >= 8 and len(native_tokens) >= 8 and agreement is not None and agreement < 0.65:
        issues.append("caption disagreement")
        score += 3
    elif len(caption_tokens) >= 8 and len(native_tokens) >= 8 and agreement is not None and agreement < 0.78:
        issues.append("lower caption agreement")
        score += 1
    if len(native) >= 1600:
        issues.append("implausibly dense 60-second window")
        score += 3
    noncanonical_aliases = [
        (canonical, observed) for canonical, observed, _ in known_alias_hits if likely_spelling_variant(canonical, observed)
    ]
    if noncanonical_aliases:
        issues.append("known name variant")
        score += 2
    return issues, score, agreement


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    samples = psql_json_lines(SAMPLE_SQL)
    people_rows = psql_json_lines(PEOPLE_SQL)
    alias_to_name, aliases = canonical_people(people_rows)
    reference_names = sorted(
        {row["display_name"] for row in people_rows} | set(load_title_reference_names()), key=lambda value: value.casefold()
    )

    reviewed_rows: list[dict[str, Any]] = []
    flagged_rows: list[dict[str, Any]] = []
    name_occurrences: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    issue_counts: Counter[str] = Counter()

    for row in samples:
        native_names = find_names(row["native_text"], alias_to_name, aliases)
        youtube_names = find_names(row["youtube_text"], alias_to_name, aliases)
        issues, score, agreement = issue_flags(row, native_names)
        seek_seconds = int(row["target_ms"] / 1000)
        base = {
            "uploaded_date": str(row["uploaded_at"])[:10],
            "video_title": row["title"],
            "youtube_id": row["youtube_id"],
            "sample_position": row["position_label"],
            "timestamp": timestamp(row["target_ms"]),
            "window": f"{timestamp(row['window_start_ms'])}–{timestamp(row['window_end_ms'])}",
            "youtube_url": f"https://www.youtube.com/watch?v={row['youtube_id']}&t={seek_seconds}s",
            "agreement_score": "" if agreement is None else round(agreement, 3),
            "native_segment_count": row["native_segment_count"],
            "youtube_segment_count": row["youtube_segment_count"],
            "native_text": excerpt(row["native_text"]),
            "youtube_caption_text": excerpt(row["youtube_text"]),
            "possible_names_native": "; ".join(sorted({name for name, _, _ in native_names})),
            "possible_names_youtube": "; ".join(sorted({name for name, _, _ in youtube_names})),
            "possible_word_or_name_differences": notable_differences(row["native_text"], row["youtube_text"]),
            "issues": "; ".join(issues),
            "review_priority": score,
        }
        reviewed_rows.append(base)
        if issues:
            flagged_rows.append(base)
            issue_counts.update(issues)

        for source, names, source_text in (
            ("Whisper", native_names, row["native_text"]),
            ("YouTube captions", youtube_names, row["youtube_text"]),
        ):
            for canonical, observed, candidate_type in names:
                name_occurrences[(canonical, observed, candidate_type)].append(
                    {
                        "source": source,
                        "video_title": row["title"],
                        "youtube_id": row["youtube_id"],
                        "timestamp": timestamp(row["target_ms"]),
                        "youtube_url": base["youtube_url"],
                        "context": contextual_excerpt(source_text, observed, 300),
                    }
                )

    flagged_rows.sort(key=lambda row: (-int(row["review_priority"]), row["uploaded_date"], row["youtube_id"], row["timestamp"]))
    reviewed_rows.sort(key=lambda row: (row["uploaded_date"], row["youtube_id"], row["timestamp"]))

    name_rows: list[dict[str, Any]] = []
    name_mistranscription_rows: list[dict[str, Any]] = []
    for (canonical, observed, candidate_type), occurrences in name_occurrences.items():
        sources = sorted({occurrence["source"] for occurrence in occurrences})
        example = occurrences[0]
        reference_match, reference_similarity = best_reference_match(observed, reference_names)
        exact_reference = reference_match.casefold() == observed.casefold()
        if candidate_type == "canonical_or_alias":
            confidence = "high"
            suggested_name = canonical
        elif exact_reference:
            confidence = "high"
            suggested_name = reference_match
        elif reference_similarity >= 0.82:
            confidence = "medium"
            suggested_name = reference_match
        elif len(occurrences) >= 2 or len(sources) >= 2:
            confidence = "medium"
            suggested_name = ""
        else:
            confidence = "low"
            suggested_name = ""
        name_rows.append(
            {
                "canonical_or_candidate": canonical,
                "observed_form": observed,
                "candidate_type": candidate_type,
                "confidence": confidence,
                "suggested_reference_name": suggested_name,
                "reference_similarity": round(reference_similarity, 3) if reference_match else "",
                "sources": "; ".join(sources),
                "sample_occurrences": len(occurrences),
                "first_video": example["video_title"],
                "first_timestamp": example["timestamp"],
                "first_youtube_url": example["youtube_url"],
                "first_context": example["context"],
            }
        )
        if suggested_name and suggested_name.casefold() != observed.casefold() and reference_similarity >= 0.82:
            name_mistranscription_rows.append(
                {
                    "observed_form": observed,
                    "possible_correction": suggested_name,
                    "similarity": round(reference_similarity, 3),
                    "assessment": NAME_LEAD_ASSESSMENTS.get(observed, "fuzzy spelling lead; manual verification required"),
                    "source": example["source"],
                    "video_title": example["video_title"],
                    "timestamp": example["timestamp"],
                    "youtube_url": example["youtube_url"],
                    "context": example["context"],
                }
            )
    name_rows.sort(key=lambda row: (-int(row["sample_occurrences"]), row["canonical_or_candidate"].casefold()))
    name_mistranscription_rows.sort(key=lambda row: (-float(row["similarity"]), row["observed_form"].casefold()))

    issue_rows = [
        {"issue_type": issue, "flagged_sections": count, "sampled_sections": len(reviewed_rows), "share": round(count / len(reviewed_rows), 4)}
        for issue, count in issue_counts.most_common()
    ]
    summary = {
        "sampled_videos": len({row["youtube_id"] for row in reviewed_rows}),
        "sampled_sections": len(reviewed_rows),
        "flagged_sections": len(flagged_rows),
        "flagged_share": round(len(flagged_rows) / len(reviewed_rows), 4),
        "name_rows": len(name_rows),
        "canonical_name_rows": sum(row["candidate_type"] == "canonical_or_alias" for row in name_rows),
        "unverified_name_rows": sum(row["candidate_type"] == "unverified_candidate" for row in name_rows),
        "possible_name_mistranscriptions": len(name_mistranscription_rows),
        "sample_positions": list(POSITIONS),
        "issue_counts": dict(issue_counts),
        "minimum_uploaded_date": min(row["uploaded_date"] for row in reviewed_rows),
        "maximum_uploaded_date": max(row["uploaded_date"] for row in reviewed_rows),
        "method_note": "Flags are screening signals. YouTube captions are a comparison source, not ground truth.",
    }

    write_csv(OUTPUT_DIR / "sampled_sections.csv", reviewed_rows)
    write_csv(OUTPUT_DIR / "flagged_sections.csv", flagged_rows)
    write_csv(OUTPUT_DIR / "name_candidates.csv", name_rows)
    write_csv(OUTPUT_DIR / "possible_name_mistranscriptions.csv", name_mistranscription_rows)
    write_csv(OUTPUT_DIR / "issue_counts.csv", issue_rows)
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (OUTPUT_DIR / "sampling_query.sql").write_text(SAMPLE_SQL.strip() + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
