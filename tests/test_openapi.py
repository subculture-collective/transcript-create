"""Test OpenAPI specification validation."""

import json

import pytest
from fastapi.testclient import TestClient
from openapi_spec_validator import validate
from openapi_spec_validator.exceptions import OpenAPISpecValidatorError


class TestOpenAPISpec:
    """Tests for OpenAPI specification validation."""

    def test_openapi_spec_is_valid(self, client: TestClient):
        """Test that the generated OpenAPI spec is valid."""
        # Get the OpenAPI spec from the app
        response = client.get("/openapi.json")
        assert response.status_code == 200

        spec = response.json()

        # Validate the spec
        try:
            validate(spec)
        except OpenAPISpecValidatorError as e:
            pytest.fail(f"OpenAPI spec validation failed: {e}")

    def test_openapi_spec_has_metadata(self, client: TestClient):
        """Test that the OpenAPI spec includes proper metadata."""
        response = client.get("/openapi.json")
        spec = response.json()

        # Check required metadata
        assert spec["info"]["title"] == "Transcript Create API"
        assert "version" in spec["info"]
        assert spec["info"]["version"] == "0.1.0"
        assert "description" in spec["info"]
        assert "contact" in spec["info"]
        assert "license" in spec["info"]

        # Check contact info
        assert spec["info"]["contact"]["name"] == "onnwee"
        assert "url" in spec["info"]["contact"]

    def test_openapi_spec_has_tags(self, client: TestClient):
        """Test that the OpenAPI spec includes route tags."""
        response = client.get("/openapi.json")
        spec = response.json()

        # Check that tags are defined
        assert "tags" in spec
        tag_names = [tag["name"] for tag in spec["tags"]]

        expected_tags = [
            "Jobs",
            "Videos",
            "Search",
            "Exports",
            "Auth",
            "Billing",
            "Admin",
            "Favorites",
            "Events",
            "Health",
        ]

        for expected_tag in expected_tags:
            assert expected_tag in tag_names, f"Missing tag: {expected_tag}"

    def test_all_routes_have_tags(self, client: TestClient):
        """Test that all routes have tags assigned."""
        response = client.get("/openapi.json")
        spec = response.json()

        # Check that all paths have at least one tag
        for path, methods in spec["paths"].items():
            for method, operation in methods.items():
                if method in ["get", "post", "put", "delete", "patch"]:
                    assert "tags" in operation, f"Route {method.upper()} {path} has no tags"
                    assert len(operation["tags"]) > 0, f"Route {method.upper()} {path} has empty tags"

    def test_all_routes_have_descriptions(self, client: TestClient):
        """Test that all routes have descriptions or summaries."""
        response = client.get("/openapi.json")
        spec = response.json()

        # Check that all paths have summary or description
        for path, methods in spec["paths"].items():
            for method, operation in methods.items():
                if method in ["get", "post", "put", "delete", "patch"]:
                    has_summary = "summary" in operation and operation["summary"]
                    has_description = "description" in operation and operation["description"]
                    assert (
                        has_summary or has_description
                    ), f"Route {method.upper()} {path} has no summary or description"

    def test_schemas_have_descriptions(self, client: TestClient):
        """Test that important schemas have descriptions."""
        response = client.get("/openapi.json")
        spec = response.json()

        # Get schemas from components
        schemas = spec.get("components", {}).get("schemas", {})

        important_schemas = [
            "JobCreate",
            "JobStatus",
            "TranscriptResponse",
            "Segment",
            "VideoInfo",
            "SearchResponse",
            "ErrorResponse",
        ]

        for schema_name in important_schemas:
            assert schema_name in schemas, f"Schema {schema_name} not found"
            # Most schemas should have descriptions or titles
            schema = schemas[schema_name]
            has_description = "description" in schema or "title" in schema
            assert has_description, f"Schema {schema_name} has no description or title"

    def test_error_responses_documented(self, client: TestClient):
        """Test that key endpoints document error responses."""
        response = client.get("/openapi.json")
        spec = response.json()

        # Check a few important endpoints for error responses
        test_cases = [
            ("POST", "/jobs", ["422"]),
            ("GET", "/jobs/{job_id}", ["404"]),
            ("GET", "/videos/{video_id}/transcript", ["404", "503"]),
            ("GET", "/search", ["400", "429"]),
        ]

        for method, path, expected_codes in test_cases:
            operation = spec["paths"][path][method.lower()]
            responses = operation.get("responses", {})

            for code in expected_codes:
                assert code in responses, f"{method} {path} missing {code} error response"

    def test_docs_endpoints_available(self, client: TestClient):
        """Test that documentation endpoints are accessible."""
        # Test Swagger UI
        response = client.get("/docs")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        # Test ReDoc
        response = client.get("/redoc")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        # Test OpenAPI JSON
        response = client.get("/openapi.json")
        assert response.status_code == 200
        assert response.headers.get("content-type") == "application/json"

    def test_openapi_spec_structure(self, client: TestClient):
        """Test the overall structure of the OpenAPI spec."""
        response = client.get("/openapi.json")
        spec = response.json()

        # Check OpenAPI version
        assert "openapi" in spec
        assert spec["openapi"].startswith("3.")

        # Check required top-level keys
        assert "info" in spec
        assert "paths" in spec
        assert "components" in spec

        # Check paths are not empty
        assert len(spec["paths"]) > 0

        # Check we have schemas defined
        assert "schemas" in spec["components"]
        assert len(spec["components"]["schemas"]) > 0

    def test_request_body_schemas(self, client: TestClient):
        """Test that POST endpoints have request body schemas."""
        response = client.get("/openapi.json")
        spec = response.json()

        post_endpoints = [
            "/jobs",
            "/billing/checkout-session",
            "/users/me/favorites",
            "/events",
        ]

        for path in post_endpoints:
            if path in spec["paths"]:
                operation = spec["paths"][path]["post"]
                assert "requestBody" in operation, f"POST {path} has no requestBody definition"
                assert "content" in operation["requestBody"]
                assert "application/json" in operation["requestBody"]["content"]
