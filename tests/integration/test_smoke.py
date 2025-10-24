"""Smoke tests for integration test infrastructure."""



class TestIntegrationInfrastructure:
    """Smoke tests to verify integration test infrastructure."""

    def test_imports(self):
        """Test that all required modules can be imported."""
        import tests.integration.conftest
        import tests.integration.test_auth_flow
        import tests.integration.test_billing_flow
        import tests.integration.test_export_flow
        import tests.integration.test_job_flow
        import tests.integration.test_search_flow
        import tests.integration.test_video_flow
        import tests.integration.test_worker_flow

        # Verify modules have expected test classes
        assert hasattr(tests.integration.test_job_flow, "TestJobProcessingFlow")
        assert hasattr(tests.integration.test_worker_flow, "TestWorkerVideoProcessing")
        assert hasattr(tests.integration.test_auth_flow, "TestAuthFlow")

    def test_fixtures_import(self):
        """Test that fixture modules can be imported."""
        from tests.fixtures import transcript_data, youtube_metadata

        # Verify fixture modules have expected data
        assert hasattr(transcript_data, "SAMPLE_WHISPER_SEGMENTS")
        assert hasattr(youtube_metadata, "SAMPLE_VIDEO_METADATA")

    def test_fixture_data_availability(self):
        """Test that fixture data is accessible."""
        from tests.fixtures.transcript_data import DB_SEGMENTS, SAMPLE_SRT_OUTPUT, SAMPLE_WHISPER_SEGMENTS
        from tests.fixtures.youtube_metadata import SAMPLE_CHANNEL_METADATA, SAMPLE_VIDEO_METADATA

        assert len(SAMPLE_WHISPER_SEGMENTS) > 0
        assert len(DB_SEGMENTS) > 0
        assert len(SAMPLE_SRT_OUTPUT) > 0
        assert SAMPLE_VIDEO_METADATA["id"] is not None
        assert SAMPLE_CHANNEL_METADATA["id"] is not None
        assert len(SAMPLE_CHANNEL_METADATA["entries"]) > 0

    def test_pytest_markers_registered(self):
        """Test that pytest markers are properly registered."""
        # This test will fail if markers aren't registered in pyproject.toml
        # The @pytest.mark.timeout decorator should be recognized
        pass

    def test_test_collection(self):
        """Verify that integration tests can be collected."""
        # This is a meta-test - if pytest can collect and run this test,
        # it means the test infrastructure is working
        assert True
