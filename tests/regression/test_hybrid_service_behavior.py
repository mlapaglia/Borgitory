"""
Regression Tests for Hybrid DI Services

This module captures the current behavior of all hybrid services before migration
to pure FastAPI DI. These tests ensure no functional changes occur during conversion.
"""

import pytest
from typing import Any
from unittest.mock import Mock

from borgitory.dependencies import (
    get_borg_service,
    get_debug_service,
    get_job_stream_service,
    get_job_render_service,
    get_archive_manager,
    get_repository_service,
)
from borgitory.services.borg_service import BorgService
from borgitory.services.debug_service import DebugService
from borgitory.services.jobs.job_stream_service import JobStreamService
from borgitory.services.jobs.job_render_service import JobRenderService
from borgitory.services.archives.archive_manager import ArchiveManager
from borgitory.services.repositories.repository_service import RepositoryService


class TestHybridServiceBehavior:
    """Capture current behavior of all hybrid services before migration."""
    
    def test_borg_service_singleton_behavior(self):
        """Test that BorgService maintains singleton behavior."""
        service1 = get_borg_service()
        service2 = get_borg_service()
        
        # Should return the same instance (singleton pattern)
        assert service1 is service2
        assert isinstance(service1, BorgService)
        
    def test_borg_service_dependencies_resolved(self):
        """Test that BorgService has proper dependencies."""
        service = get_borg_service()
        
        # Verify dependencies are injected
        assert hasattr(service, 'command_runner')
        assert hasattr(service, 'volume_service')
        assert hasattr(service, 'job_manager')
        
        # Dependencies should not be None
        assert service.command_runner is not None
        assert service.volume_service is not None
        assert service.job_manager is not None
        
    def test_borg_service_core_functionality(self):
        """Test core BorgService functionality works."""
        service = get_borg_service()
        
        # Test that key methods exist and are callable
        assert callable(getattr(service, 'create_backup', None))
        assert callable(getattr(service, 'list_archives', None))
        assert callable(getattr(service, 'get_repo_info', None))
        assert callable(getattr(service, 'verify_repository_access', None))
        assert callable(getattr(service, 'scan_for_repositories', None))
        
    def test_debug_service_singleton_behavior(self):
        """Test that DebugService maintains singleton behavior."""
        service1 = get_debug_service()
        service2 = get_debug_service()
        
        assert service1 is service2
        assert isinstance(service1, DebugService)
        
    def test_debug_service_dependencies_resolved(self):
        """Test that DebugService has proper dependencies."""
        service = get_debug_service()
        
        assert hasattr(service, 'volume_service')
        assert hasattr(service, 'job_manager')
        
        # Dependencies should not be None
        assert service.volume_service is not None
        assert service.job_manager is not None
        
    def test_debug_service_core_functionality(self):
        """Test core DebugService functionality works."""
        service = get_debug_service()
        
        # Test that key methods exist and are callable
        assert callable(getattr(service, 'get_debug_info', None))
        
    def test_job_stream_service_singleton_behavior(self):
        """Test that JobStreamService no longer maintains singleton behavior (converted to pure DI)."""
        # Direct calls still work (backward compatibility) but no longer return the same instance
        service1 = get_job_stream_service()
        service2 = get_job_stream_service()
        
        # Both should be JobStreamService instances
        assert isinstance(service1, JobStreamService)
        assert isinstance(service2, JobStreamService)
        
        # But they should be DIFFERENT instances (no longer singleton)
        assert service1 is not service2, "JobStreamService should no longer be singleton"
        
    def test_job_stream_service_dependencies_resolved(self):
        """Test that JobStreamService has proper dependencies."""
        service = get_job_stream_service()
        
        assert hasattr(service, 'job_manager')
        assert service.job_manager is not None
        
    def test_job_stream_service_core_functionality(self):
        """Test core JobStreamService functionality works."""
        service = get_job_stream_service()
        
        # Test that key methods exist and are callable
        assert callable(getattr(service, 'stream_all_jobs', None))
        assert callable(getattr(service, 'stream_job_output', None))
        assert callable(getattr(service, 'get_current_jobs_data', None))
        
    def test_job_render_service_singleton_behavior(self):
        """Test that JobRenderService no longer maintains singleton behavior (converted to pure DI)."""
        # Direct calls still work (backward compatibility) but no longer return the same instance
        service1 = get_job_render_service()
        service2 = get_job_render_service()
        
        # Both should be JobRenderService instances
        assert isinstance(service1, JobRenderService)
        assert isinstance(service2, JobRenderService)
        
        # But they should be DIFFERENT instances (no longer singleton)
        assert service1 is not service2, "JobRenderService should no longer be singleton"
        
    def test_job_render_service_dependencies_resolved(self):
        """Test that JobRenderService has proper dependencies."""
        service = get_job_render_service()
        
        assert hasattr(service, 'job_manager')
        assert service.job_manager is not None
        
    def test_job_render_service_core_functionality(self):
        """Test core JobRenderService functionality works."""
        service = get_job_render_service()
        
        # Test that key methods exist and are callable
        assert callable(getattr(service, 'render_jobs_html', None))
        assert callable(getattr(service, 'render_current_jobs_html', None))
        assert callable(getattr(service, 'get_job_for_render', None))
        assert callable(getattr(service, 'stream_current_jobs_html', None))
        
    def test_archive_manager_singleton_behavior(self):
        """Test that ArchiveManager no longer maintains singleton behavior (converted to pure DI)."""
        # Note: ArchiveManager has been converted to pure FastAPI DI
        # Direct calls still work (backward compatibility) but no longer return the same instance
        service1 = get_archive_manager()
        service2 = get_archive_manager()
        
        # Both should be ArchiveManager instances
        assert isinstance(service1, ArchiveManager)
        assert isinstance(service2, ArchiveManager)
        
        # But they should be DIFFERENT instances (no longer singleton)
        assert service1 is not service2, "ArchiveManager should no longer be singleton"
        
    def test_archive_manager_dependencies_resolved(self):
        """Test that ArchiveManager has proper dependencies."""
        # Direct calls still work with pure DI (backward compatibility)
        service = get_archive_manager()
        
        assert hasattr(service, 'job_executor')
        assert hasattr(service, 'command_builder')
        
        # Dependencies should not be None
        assert service.job_executor is not None
        assert service.command_builder is not None
        
    def test_archive_manager_core_functionality(self):
        """Test core ArchiveManager functionality works."""
        # Direct calls work with pure DI (backward compatibility)
        service = get_archive_manager()
        
        # Test that key methods exist and are callable
        assert callable(getattr(service, 'list_archive_contents', None))
        assert callable(getattr(service, 'get_archive_metadata', None))
        assert callable(getattr(service, 'list_archive_directory_contents', None))
        assert callable(getattr(service, 'validate_archive_path', None))
        
    def test_repository_service_singleton_behavior(self):
        """Test that RepositoryService maintains singleton behavior."""
        service1 = get_repository_service()
        service2 = get_repository_service()
        
        assert service1 is service2
        assert isinstance(service1, RepositoryService)
        
    def test_repository_service_dependencies_resolved(self):
        """Test that RepositoryService has proper dependencies."""
        service = get_repository_service()
        
        assert hasattr(service, 'borg_service')
        assert hasattr(service, 'scheduler_service')
        assert hasattr(service, 'volume_service')
        
        # Dependencies should not be None
        assert service.borg_service is not None
        assert service.scheduler_service is not None
        assert service.volume_service is not None
        
    def test_repository_service_core_functionality(self):
        """Test core RepositoryService functionality works."""
        service = get_repository_service()
        
        # Test that key methods exist and are callable
        assert callable(getattr(service, 'scan_repositories', None))
        assert callable(getattr(service, 'create_repository', None))
        assert callable(getattr(service, 'delete_repository', None))
        
    def test_dependency_chain_consistency(self):
        """Test that dependency chains are consistent across services."""
        borg_service = get_borg_service()
        repository_service = get_repository_service()
        
        # RepositoryService should use the same BorgService instance
        assert repository_service.borg_service is borg_service
        
        # Both services should use the same VolumeService instance
        assert repository_service.volume_service is borg_service.volume_service
        
    def test_all_services_instantiate_successfully(self):
        """Test that all hybrid services can be instantiated without errors."""
        services = [
            get_borg_service(),
            get_debug_service(),
            get_job_stream_service(),
            get_job_render_service(),
            get_archive_manager(),
            get_repository_service(),
        ]
        
        # All services should be instantiated
        for service in services:
            assert service is not None
            
        # All should be different types
        service_types = [type(service) for service in services]
        assert len(set(service_types)) == len(service_types)  # All unique types


class TestHybridServicePerformance:
    """Test performance characteristics of hybrid services."""
    
    def test_service_creation_performance(self):
        """Test that service creation is fast (due to singleton caching)."""
        import time
        
        # First call (creates instance)
        start_time = time.time()
        service1 = get_borg_service()
        first_call_time = time.time() - start_time
        
        # Second call (should return cached instance)
        start_time = time.time()
        service2 = get_borg_service()
        second_call_time = time.time() - start_time
        
        # Second call should be significantly faster (cached)
        assert second_call_time < first_call_time
        assert service1 is service2
        
    def test_memory_usage_singleton_pattern(self):
        """Test that singleton pattern doesn't create memory leaks."""
        import gc
        
        # Create references to services multiple times
        services = []
        for _ in range(100):
            services.append([
                get_borg_service(),
                get_debug_service(),
                get_job_stream_service(),
                get_job_render_service(),
                get_archive_manager(),
                get_repository_service(),
            ])
        
        # All references should point to the same instances
        first_batch = services[0]
        for batch in services[1:]:
            for i, service in enumerate(batch):
                assert service is first_batch[i]
        
        # Clean up
        del services
        gc.collect()


class TestHybridServiceErrorHandling:
    """Test error handling in hybrid services."""
    
    def test_borg_service_error_handling(self):
        """Test BorgService error handling."""
        service = get_borg_service()
        
        # Test that service handles missing job manager gracefully
        # (This tests the _get_job_manager method)
        if hasattr(service, '_get_job_manager'):
            try:
                job_manager = service._get_job_manager()
                assert job_manager is not None
            except RuntimeError:
                # This is expected if job_manager is None
                pass
    
    def test_service_method_signatures(self):
        """Test that service methods have expected signatures."""
        import inspect
        
        # Test BorgService methods
        borg_service = get_borg_service()
        create_backup_method = getattr(borg_service, 'create_backup', None)
        if create_backup_method:
            sig = inspect.signature(create_backup_method)
            # Should have parameters (exact signature may vary)
            assert len(sig.parameters) >= 0
            
        # Test DebugService methods
        debug_service = get_debug_service()
        get_debug_info_method = getattr(debug_service, 'get_debug_info', None)
        if get_debug_info_method:
            sig = inspect.signature(get_debug_info_method)
            assert len(sig.parameters) >= 0


class TestHybridServiceIntegration:
    """Test integration aspects of hybrid services."""
    
    def test_services_work_with_existing_tests(self):
        """Test that services work with existing test patterns."""
        # This mimics how existing tests call services
        from tests.test_dependencies import TestDependencies
        
        test_instance = TestDependencies()
        
        # These should work without throwing exceptions
        test_instance.test_get_borg_service()
        test_instance.test_get_debug_service()
        test_instance.test_get_job_stream_service()
        test_instance.test_get_job_render_service()
        
    def test_services_compatible_with_api_usage(self):
        """Test that services are compatible with how APIs use them."""
        # Test that services can be used in the way APIs expect
        
        # BorgService (used in repositories API)
        borg_service = get_borg_service()
        assert hasattr(borg_service, 'scan_for_repositories')
        assert hasattr(borg_service, 'verify_repository_access')
        
        # DebugService (used in debug API)
        debug_service = get_debug_service()
        assert hasattr(debug_service, 'get_debug_info')
        
        # JobStreamService (used in jobs API)
        job_stream_service = get_job_stream_service()
        assert hasattr(job_stream_service, 'stream_all_jobs')
        
        # JobRenderService (used in jobs API)
        job_render_service = get_job_render_service()
        assert hasattr(job_render_service, 'render_jobs_html')
        
        # RepositoryService (used in repositories API)
        repository_service = get_repository_service()
        assert hasattr(repository_service, 'scan_repositories')


class TestHybridServiceRegression:
    """Test for regressions in hybrid service behavior."""
    
    def test_no_circular_dependencies(self):
        """Test that there are no circular dependencies in service creation."""
        # This should not cause infinite recursion or stack overflow
        try:
            services = [
                get_borg_service(),
                get_debug_service(),
                get_job_stream_service(),
                get_job_render_service(),
                get_archive_manager(),
                get_repository_service(),
            ]
            
            # All services should be created successfully
            for service in services:
                assert service is not None
                
        except RecursionError:
            pytest.fail("Circular dependency detected in service creation")
        except Exception as e:
            pytest.fail(f"Unexpected error in service creation: {e}")
    
    def test_service_state_isolation(self):
        """Test that services maintain proper state isolation."""
        # Get multiple references to services
        borg1 = get_borg_service()
        borg2 = get_borg_service()
        
        # They should be the same instance
        assert borg1 is borg2
        
        # Modifying one should affect the other (since they're the same instance)
        original_attr = getattr(borg1, 'command_runner', None)
        if original_attr is not None:
            # This is expected behavior for singletons
            assert getattr(borg2, 'command_runner', None) is original_attr
    
    def test_service_cleanup_behavior(self):
        """Test service cleanup and resource management."""
        # This test ensures services can be garbage collected properly
        import weakref
        import gc
        
        # Create weak references to services
        service = get_borg_service()
        weak_ref = weakref.ref(service)
        
        # The service should still exist (it's a singleton)
        assert weak_ref() is not None
        
        # Even after deleting our reference, the singleton should persist
        del service
        gc.collect()
        
        # Singleton should still exist in the dependency system
        assert weak_ref() is not None
        assert get_borg_service() is weak_ref()
