import uuid
from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy import text

from app.settings import settings


@pytest.fixture
def passage_video(db_session, monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_PASSAGES_ENABLED", True)
    monkeypatch.setattr(settings, "FRONTEND_ORIGIN", "https://archive.example")
    job_id, video_id = uuid.uuid4(), uuid.uuid4()
    db_session.execute(
        text("INSERT INTO jobs(id,kind,input_url) VALUES (:id,'single','https://example.invalid')"), {"id": job_id}
    )
    db_session.execute(
        text(
            "INSERT INTO videos(id,job_id,youtube_id,title,duration_seconds) VALUES (:id,:job,'M7lc1UVf-VE',:title,60)"
        ),
        {"id": video_id, "job": job_id, "title": '<script>alert("title")</script>'},
    )
    db_session.execute(
        text("INSERT INTO segments(video_id,start_ms,end_ms,text) VALUES (:id,1000,5000,:text)"),
        {"id": video_id, "text": '<img src=x onerror="alert(1)"> A passage in context.'},
    )
    return video_id


def test_public_passage_has_server_metadata_safe_content_and_context_link(client, passage_video):
    response = client.get(
        f"/share/videos/{passage_video}?start_ms=1125&end_ms=4000", headers={"Host": "untrusted.example"}
    )
    assert response.status_code == 200
    assert "<script>alert" not in response.text
    assert "<img src=x" not in response.text
    assert "&lt;script&gt;" in response.text
    assert 'property="og:description"' in response.text
    assert "00:00:01.125–00:00:04" in response.text
    assert "https://archive.example/api/share/videos/" in response.text
    assert "untrusted.example" not in response.text
    assert f"/v/{passage_video}?t=1&amp;t_ms=1125&amp;end_ms=4000" in response.text
    assert "no-store" in response.headers["cache-control"]
    assert "frame-src https://www.youtube.com" in response.headers["content-security-policy"]


def test_card_is_real_png_and_deleted_source_is_not_cached(client, db_session, passage_video):
    path = f"/share/videos/{passage_video}/card.png?start_ms=1000&end_ms=4000"
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert Image.open(BytesIO(response.content)).size == (1200, 630)
    db_session.execute(text("DELETE FROM videos WHERE id=:id"), {"id": passage_video})
    assert client.get(path).status_code == 404


@pytest.mark.parametrize(
    "query",
    [
        "start_ms=5000&end_ms=1000",
        "start_ms=-1&end_ms=3000",
        "start_ms=1.5&end_ms=3000",
        "start_ms=1000&end_ms=61000",
        "end_ms=5000",
        "start_ms=0&end_ms=Infinity",
    ],
)
def test_passage_rejects_invalid_ranges(client, passage_video, query):
    assert client.get(f"/share/videos/{passage_video}?{query}").status_code == 422


def test_public_passages_can_be_disabled_for_nonpublic_deployments(client, passage_video, monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_PASSAGES_ENABLED", False)
    assert client.get(f"/share/videos/{passage_video}?start_ms=1000&end_ms=4000").status_code == 404
    assert client.get(f"/share/videos/{passage_video}/card.png?start_ms=1000&end_ms=4000").status_code == 404


def test_missing_transcript_and_unknown_video_do_not_generate_previews(client, passage_video):
    assert client.get(f"/share/videos/{passage_video}?start_ms=20000&end_ms=21000").status_code == 404
    assert client.get(f"/share/videos/{uuid.uuid4()}?start_ms=1000&end_ms=2000").status_code == 404


def test_passage_and_card_use_client_palette(client, passage_video, monkeypatch):
    from app.branding import BrandProfile

    monkeypatch.setattr(settings, "SITE_NAME", "Northstar <Archive>")
    monkeypatch.setattr(
        settings,
        "SITE_BRANDING",
        BrandProfile(theme={"dark": {"canvas": "#112233", "ink": "#eeeeee", "accent": "#ffaa00"}}),
    )
    path = f"/share/videos/{passage_video}"
    page = client.get(path + "?start_ms=1000&end_ms=4000")
    assert "Northstar &lt;Archive&gt;" in page.text
    assert "background:#112233" in page.text
    assert "color:#ffaa00" in page.text
    card = client.get(path + "/card.png?start_ms=1000&end_ms=4000")
    image = Image.open(BytesIO(card.content))
    assert image.getpixel((1199, 629)) == (17, 34, 51)
    assert image.getpixel((0, 0)) == (255, 170, 0)
