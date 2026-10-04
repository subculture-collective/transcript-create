"""Contracts for selective application release artifact selection."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".gitea" / "workflows" / "backend-role-release.yaml"


def test_selective_release_accepts_only_supported_application_roles():
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "- api" in source
    assert "- ingest-cuda" in source
    assert '[[ "$ROLE" == api || "$ROLE" == ingest-cuda ]]' in source
    assert "Dockerfile.api" in source
    assert "Dockerfile.ingest.cuda" in source
    assert "frontend/Dockerfile" not in source
    assert "- frontend" not in source
    assert "hasanara-frontend" not in source
    assert "Dockerfile.cuda" not in source
    assert "Dockerfile.postgres-walg" not in source


def test_selective_release_revalidates_every_unchanged_first_party_digest():
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "base_manifest_json" in source
    assert "reused-images.txt" in source
    assert 'cosign verify --key cosign.pub "$image"' in source
    assert 'cosign verify-attestation --key cosign.pub --type slsaprovenance "$image"' in source
    assert 'cosign verify-attestation --key cosign.pub --type spdxjson "$image"' in source
    assert 'manifest["images"][os.environ["ROLE"]]' in source
    assert '"reused_artifacts_reverified": True' in source


def test_selected_digest_is_scanned_signed_attested_and_uploaded():
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "backend-image:\n    runs-on: switchyard-production" in source
    assert "--severity CRITICAL,HIGH --pkg-types library --exit-code 1" in source
    assert 'docker push "$IMAGE:$TAG"' not in source
    assert "quay.io/skopeo/stable@sha256:47853bb9fb24202af9110531ebd6e43c5f97701254ca290596640290d17942f4" in source
    assert 'destination="docker://${IMAGE}:${TAG}"' in source
    assert 'destination_tls_verify=true' in source
    assert 'if docker container inspect gitea >/dev/null 2>&1; then' in source
    assert 'docker network create --internal "$network"' in source
    assert 'docker network connect --alias registry-origin "$network" gitea' in source
    assert 'destination="docker://registry-origin:3000/${repository}:${TAG}"' in source
    assert '"docker-daemon:${IMAGE}:${TAG}" "$DESTINATION"' in source
    assert '--dest-tls-verify="$DESTINATION_TLS_VERIFY"' in source
    assert '--dest-registry-token "$REGISTRY_BEARER_TOKEN"' in source
    assert '[[ "$canonical_digest" == "$pushed_digest" ]]' in source
    assert "trap cleanup EXIT" in source
    assert '"builder": {"id":' in source
    assert 'cosign sign --yes --key env://COSIGN_PRIVATE_KEY "$IMAGE_REF"' in source
    assert "--type slsaprovenance --predicate selected.provenance.json" in source
    assert "--type spdxjson --predicate selected.spdx.json" in source
    assert "release-images.json" in source


def test_selective_release_drops_a_legacy_frontend_role_from_the_base_manifest():
    source = WORKFLOW.read_text(encoding="utf-8")

    assert 'if role not in {os.environ["ROLE"], "redis", "frontend"}:' in source
    assert 'manifest["images"].pop("frontend", None)' in source
    assert 'manifest["services"].pop("frontend", None)' in source
