"""
Tests for Job SSE API endpoint - Unit tests only
Note: Full SSE streaming tests are handled in test_job_render_service.py
Integration testing of SSE endpoints requires specialized tools due to streaming nature.
"""
from fastapi.testclient import TestClient

from app.main import app


class TestJobsAPISSEEndpoint:
    """Test SSE endpoint registration and basic functionality"""

    def setup_method(self):
        """Set up test fixtures"""
        self.client = TestClient(app)

    def test_sse_endpoint_registration(self):
        """Test that SSE endpoint is properly registered"""
        # This test just verifies the endpoint exists and can be called
        # without actually consuming the stream
        from app.api.jobs import router
        
        # Check that the route is registered
        routes = [route.path for route in router.routes]
        assert "/current/stream" in routes

    def test_sse_endpoint_function_signature(self):
        """Test that SSE endpoint function has correct signature"""
        from app.api.jobs import stream_current_jobs_html
        import inspect
        
        # Check function signature
        sig = inspect.signature(stream_current_jobs_html)
        assert 'render_svc' in sig.parameters
        
        # Check that it's an async function
        assert inspect.iscoroutinefunction(stream_current_jobs_html)

    def test_sse_endpoint_imports(self):
        """Test that SSE endpoint has all necessary imports"""
        from app.api.jobs import stream_current_jobs_html
        import inspect
        
        # Get the source code to verify it uses StreamingResponse
        source = inspect.getsource(stream_current_jobs_html)
        
        assert "StreamingResponse" in source
        assert "text/event-stream" in source
        assert "Cache-Control" in source
        assert "no-cache" in source