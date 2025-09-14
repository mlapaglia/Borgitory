import pytest
from unittest.mock import Mock, patch

from app.services.jobs.job_render_service import JobRenderService


class TestJobRenderService:
    """Test JobRenderService functionality"""

    def test_initialization(self):
        """Test JobRenderService initialization"""
        with patch('app.services.jobs.job_render_service.get_job_manager') as mock_get_manager:
            mock_job_manager = Mock()
            mock_job_manager.jobs = {}
            mock_get_manager.return_value = mock_job_manager

            job_render_service = JobRenderService()
            assert job_render_service is not None
            assert job_render_service.templates is not None
            assert job_render_service.job_manager is not None

    def test_initialization_with_custom_manager(self):
        """Test initialization with custom job manager"""
        custom_manager = Mock()
        service = JobRenderService(job_manager=custom_manager)
        assert service.job_manager == custom_manager

    def test_render_jobs_html_no_jobs(self):
        """Test rendering HTML when no jobs exist"""
        with patch('app.services.jobs.job_render_service.get_job_manager') as mock_get_manager:
            mock_job_manager = Mock()
            mock_job_manager.jobs = {}
            mock_get_manager.return_value = mock_job_manager

            job_render_service = JobRenderService()
            mock_db = Mock()
            mock_db.query.return_value.options.return_value.order_by.return_value.limit.return_value.all.return_value = []

            result = job_render_service.render_jobs_html(mock_db)

            assert "No job history available" in result

    def test_dependency_injection_service(self):
        """Test that dependency injection service works"""
        from app.dependencies import get_job_render_service

        service = get_job_render_service()
        assert service is not None
        assert isinstance(service, JobRenderService)

        # Test singleton behavior
        service2 = get_job_render_service()
        assert service is service2
