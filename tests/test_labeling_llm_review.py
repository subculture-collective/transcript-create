import json

from app.archive.labeling.llm_review import build_label_review_messages


def test_build_label_review_messages_batches_labels_with_schema():
    messages = build_label_review_messages(
        [{"label_id": "1", "label": "About Israel", "canonical_hint": "Israel"}],
        canonical_context=["Israel", "Gaza"],
    )

    assert messages[0]["role"] == "system"
    payload = json.loads(messages[1]["content"])
    assert payload["labels"][0]["label"] == "About Israel"
    assert payload["canonical_context"] == ["Israel", "Gaza"]
    assert "related_label" in payload["response_schema"]["proposals"][0]["action"]
