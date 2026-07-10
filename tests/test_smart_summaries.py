from __future__ import annotations

import json

import pytest

from app.archive.smart_summaries import (
    PROMPT_VERSION,
    SummaryValidationError,
    build_summary_request,
    parse_summary_response,
)

EVIDENCE = [
    {
        "evidence_id": "moment-1",
        "video_id": "video-1",
        "title": "Hasan reacts to election results",
        "topic": "Election",
        "start_ms": 120_000,
        "end_ms": 150_000,
        "snippet": (
            "The discussion turns to the election results, voter turnout, and the campaigns that shaped the outcome."
        ),
    },
    {
        "evidence_id": "moment-2",
        "video_id": "video-2",
        "title": "Union organizing interview",
        "topic": "Labor",
        "start_ms": 60_000,
        "end_ms": 95_000,
        "snippet": (
            "A guest explains the union organizing drive, workplace concerns, "
            "and the workers preparing for an upcoming vote."
        ),
    },
]


def test_summary_request_uses_structured_output_and_disables_thinking():
    request = build_summary_request("May 2026", EVIDENCE, model="qwen3:4b")

    assert request["model"] == "qwen3:4b"
    assert request["stream"] is False
    assert request["think"] is False
    assert request["options"]["temperature"] == 0
    assert request["format"]["required"] == ["claims"]
    assert PROMPT_VERSION in request["messages"][0]["content"]
    assert "moment-1" in request["messages"][1]["content"]


def test_summary_response_keeps_only_cited_claims_and_builds_summary():
    payload = {
        "message": {
            "content": json.dumps(
                {
                    "claims": [
                        {
                            "text": "The period included election analysis focused on results and turnout.",
                            "evidence_ids": ["moment-1"],
                        },
                        {
                            "text": "It also featured a discussion of a union drive and vote.",
                            "evidence_ids": ["moment-2"],
                        },
                    ]
                }
            )
        },
        "prompt_eval_count": 100,
        "eval_count": 40,
    }

    result = parse_summary_response(payload, EVIDENCE, model="qwen3:4b")

    assert result.summary == (
        "The period included election analysis focused on results and turnout. "
        "It also featured a discussion of a union drive and vote."
    )
    assert result.evidence_ids == ("moment-1", "moment-2")
    assert result.prompt_tokens == 100
    assert result.completion_tokens == 40


@pytest.mark.parametrize(
    "claims",
    [
        [],
        [{"text": "An unsupported claim.", "evidence_ids": []}],
        [{"text": "A claim with an invented citation.", "evidence_ids": ["missing"]}],
    ],
)
def test_summary_response_rejects_missing_or_unknown_citations(claims):
    payload = {"message": {"content": json.dumps({"claims": claims})}}

    with pytest.raises(SummaryValidationError):
        parse_summary_response(payload, EVIDENCE, model="qwen3:4b")


@pytest.mark.parametrize(
    "text",
    [
        "The election discussion featured invented analyst Jordan Bellups.",
        "The election discussion reported an unsupported 77% turnout increase.",
    ],
)
def test_summary_response_rejects_unsupported_named_terms_and_numbers(text):
    payload = {"message": {"content": json.dumps({"claims": [{"text": text, "evidence_ids": ["moment-1"]}]})}}

    with pytest.raises(SummaryValidationError):
        parse_summary_response(payload, EVIDENCE, model="qwen3:4b")
