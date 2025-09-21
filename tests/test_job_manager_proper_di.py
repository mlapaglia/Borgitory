"""
Tests for JobManager proper DI patterns using dual function approach.
"""

from unittest.mock import Mock

from borgitory.dependencies import get_job_manager_singleton, get_job_manager_dependency


class TestJobManagerProperDI:
    """Test JobManager proper dependency injection patterns"""

    def test_singleton_function_returns_same_instance(self) -> None:
        """Test that get_job_manager_singleton returns the same instance on multiple calls"""
        instance1 = get_job_manager_singleton()
        instance2 = get_job_manager_singleton()

        # Should be the exact same instance (singleton behavior)
        assert instance1 is instance2
        assert id(instance1) == id(instance2)

    def test_dependency_function_returns_singleton(self) -> None:
        """Test that get_job_manager_dependency returns the same singleton instance"""
        singleton_instance = get_job_manager_singleton()
        dependency_instance = get_job_manager_dependency()

        # Both should return the exact same instance
        assert singleton_instance is dependency_instance
        assert id(singleton_instance) == id(dependency_instance)

    def test_multiple_dependency_calls_return_same_instance(self) -> None:
        """Test that multiple calls to get_job_manager_dependency return the same instance"""
        instance1 = get_job_manager_dependency()
        instance2 = get_job_manager_dependency()
        instance3 = get_job_manager_singleton()

        # All should be the exact same instance
        assert instance1 is instance2
        assert instance2 is instance3
        assert id(instance1) == id(instance2) == id(instance3)

    def test_job_manager_has_required_attributes(self) -> None:
        """Test that the JobManager instance has the required attributes for job state"""
        job_manager = get_job_manager_singleton()

        # Should have the jobs dictionary for maintaining state
        assert hasattr(job_manager, "jobs")
        assert isinstance(job_manager.jobs, dict)

        # Should have other required attributes
        assert hasattr(job_manager, "config")
        assert hasattr(job_manager, "dependencies")

    def test_job_state_consistency_across_calls(self) -> None:
        """Test that job state is maintained across different function calls"""
        # Get instances through different functions
        manager1 = get_job_manager_singleton()
        manager2 = get_job_manager_dependency()

        # Add a mock job to the first instance
        test_job_id = "test-job-123"
        mock_job = Mock()
        mock_job.id = test_job_id
        mock_job.status = "running"

        manager1.jobs[test_job_id] = mock_job

        # The second instance should see the same job (shared state)
        assert test_job_id in manager2.jobs
        assert manager2.jobs[test_job_id] is mock_job
        assert manager2.jobs[test_job_id].status == "running"

    def test_proper_di_pattern_documentation(self) -> None:
        """Test that the functions have proper documentation for DI usage"""
        singleton_doc = get_job_manager_singleton.__doc__
        dependency_doc = get_job_manager_dependency.__doc__

        # Singleton function should document direct usage
        assert "direct instantiation" in singleton_doc
        assert "tests" in singleton_doc
        assert "background tasks" in singleton_doc
        assert "Don't use for: FastAPI endpoints" in singleton_doc

        # Dependency function should document FastAPI DI usage
        assert "FastAPI endpoints" in dependency_doc
        assert "Depends(get_job_manager_dependency)" in dependency_doc
        assert "Don't use for: Direct calls" in dependency_doc
        assert "use get_job_manager_singleton() instead" in dependency_doc


class TestJobManagerDIAntiPatterns:
    """Test that the old anti-patterns are avoided"""

    def test_no_global_variables_in_module(self) -> None:
        """Test that there are no global singleton variables in the dependencies module"""
        import borgitory.dependencies as deps

        # Should not have global instance variables
        assert not hasattr(deps, "_job_manager_instance")
        assert not hasattr(deps, "global_job_manager")
        assert not hasattr(deps, "job_manager_singleton")

    def test_functions_are_pure_di(self) -> None:
        """Test that the DI functions follow pure dependency injection principles"""
        # The singleton function should use @lru_cache for proper caching
        assert hasattr(
            get_job_manager_singleton, "__wrapped__"
        )  # lru_cache creates __wrapped__

        # The dependency function should be a simple wrapper
        dependency_source = get_job_manager_dependency.__code__
        assert dependency_source.co_argcount == 0  # No parameters (pure wrapper)

    def test_consistent_return_types(self) -> None:
        """Test that both functions return the same concrete type"""
        singleton_instance = get_job_manager_singleton()
        dependency_instance = get_job_manager_dependency()

        # Both should return the same concrete type
        assert type(singleton_instance) is type(dependency_instance)
        assert hasattr(singleton_instance, "jobs")  # JobManager-specific attribute
        assert hasattr(dependency_instance, "jobs")  # JobManager-specific attribute
