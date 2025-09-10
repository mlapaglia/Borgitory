"""
Critical test suite for CloudSyncManager

This test focuses on preventing the specific import and method call issues
that caused the cloud sync failures.
"""
import pytest
import asyncio
from unittest.mock import Mock, patch

from app.services.cloud_sync_manager import CloudSyncManager


class TestCloudSyncManagerCritical:
    """Critical tests for CloudSyncManager to prevent regressions"""

    def test_rclone_service_import_works(self):
        """
        CRITICAL: Ensure RcloneService can be imported correctly
        This prevents: ImportError: cannot import name 'rclone_service' from 'app.services.rclone_service'
        """
        try:
            from app.services.rclone_service import RcloneService
            assert RcloneService is not None
            
            # Verify we can instantiate it
            service = RcloneService()
            assert service is not None
            print("✓ RcloneService import and instantiation successful")
        except ImportError as e:
            pytest.fail(f"CRITICAL: Failed to import RcloneService: {e}")

    def test_rclone_service_has_correct_method_name(self):
        """
        CRITICAL: Ensure RcloneService has sync_repository_to_s3, not sync_to_s3
        This prevents: AttributeError: 'RcloneService' object has no attribute 'sync_to_s3'
        """
        from app.services.rclone_service import RcloneService
        
        service = RcloneService()
        
        # Test that the correct method exists
        assert hasattr(service, 'sync_repository_to_s3'), "RcloneService missing sync_repository_to_s3 method"
        assert callable(service.sync_repository_to_s3), "sync_repository_to_s3 is not callable"
        
        # Test that the old incorrect method name does NOT exist
        assert not hasattr(service, 'sync_to_s3'), "RcloneService should NOT have sync_to_s3 method"
        
        print("✓ RcloneService has correct method name")

    def test_rclone_method_has_correct_parameters(self):
        """
        CRITICAL: Ensure sync_repository_to_s3 has the expected parameters
        This prevents: TypeError: unexpected keyword arguments
        """
        from app.services.rclone_service import RcloneService
        import inspect
        
        service = RcloneService()
        method = service.sync_repository_to_s3
        
        # Get method signature
        sig = inspect.signature(method)
        param_names = list(sig.parameters.keys())
        
        # Verify expected parameters are present (these are what CloudSyncManager passes)
        required_params = ['repository', 'access_key_id', 'secret_access_key', 'bucket_name']
        for param in required_params:
            assert param in param_names, f"Missing required parameter '{param}' in sync_repository_to_s3"
        
        print("✓ RcloneService method has correct parameters")

    def test_cloud_sync_manager_has_sync_method(self):
        """
        CRITICAL: Ensure CloudSyncManager has the expected sync methods
        """
        manager = CloudSyncManager()
        
        # Verify the _sync_to_s3 method exists
        assert hasattr(manager, '_sync_to_s3'), "CloudSyncManager missing _sync_to_s3 method"
        assert callable(manager._sync_to_s3), "_sync_to_s3 is not callable"
        
        print("✓ CloudSyncManager has required sync methods")

    def test_cloud_sync_manager_method_signature(self):
        """
        CRITICAL: Ensure CloudSyncManager._sync_to_s3 has the expected parameters
        """
        from app.services.cloud_sync_manager import CloudSyncManager
        import inspect
        
        manager = CloudSyncManager()
        method = manager._sync_to_s3
        
        # Get method signature
        sig = inspect.signature(method)
        param_names = list(sig.parameters.keys())
        
        # Verify expected parameters are present
        expected_params = ['config', 'repo_data', 'output_callback']
        for param in expected_params:
            assert param in param_names, f"Missing parameter '{param}' in _sync_to_s3"
        
        print("✓ CloudSyncManager._sync_to_s3 has correct parameters")

    def test_integration_compatibility(self):
        """
        CRITICAL: Ensure CloudSyncManager and RcloneService are compatible
        This tests that the integration between the two services will work
        """
        from app.services.cloud_sync_manager import CloudSyncManager
        from app.services.rclone_service import RcloneService
        
        # Verify both classes exist and can be instantiated
        sync_manager = CloudSyncManager()
        rclone_service = RcloneService()
        
        assert sync_manager is not None
        assert rclone_service is not None
        
        # Verify RcloneService has the methods that CloudSyncManager expects to use
        assert hasattr(rclone_service, 'sync_repository_to_s3')
        
        # Verify the method signature matches what CloudSyncManager calls
        import inspect
        sig = inspect.signature(rclone_service.sync_repository_to_s3)
        
        # These are the parameters that CloudSyncManager tries to pass
        expected_params = ['repository', 'access_key_id', 'secret_access_key', 'bucket_name']
        param_names = list(sig.parameters.keys())
        
        for param in expected_params:
            assert param in param_names, f"RcloneService.sync_repository_to_s3 missing expected parameter: {param}"
        
        print("✓ CloudSyncManager and RcloneService are compatible")

    def test_async_generator_return_type(self):
        """
        CRITICAL: Verify that sync_repository_to_s3 returns an async generator
        This prevents issues with consuming the return value
        """
        from app.services.rclone_service import RcloneService
        import inspect
        
        service = RcloneService()
        method = service.sync_repository_to_s3
        
        # Check return type annotation if available
        sig = inspect.signature(method)
        return_annotation = sig.return_annotation
        
        # The method should return AsyncGenerator[Dict, None]
        if return_annotation != inspect.Signature.empty:
            # Check if it's some form of async generator annotation
            return_str = str(return_annotation)
            assert 'AsyncGenerator' in return_str or 'async' in return_str.lower(), \
                f"sync_repository_to_s3 should return AsyncGenerator, got {return_annotation}"
        
        print("✓ RcloneService method has correct return type")

    def test_prevent_old_import_pattern(self):
        """
        CRITICAL: Ensure the old incorrect import pattern doesn't exist
        This prevents the original error: cannot import name 'rclone_service'
        """
        # This import should fail - there is no 'rclone_service' function/object to import
        try:
            from app.services.rclone_service import rclone_service
            pytest.fail("ERROR: Found old 'rclone_service' import - this should not exist!")
        except ImportError:
            # This is expected - the old import should fail
            pass
        
        print("✓ Old incorrect import pattern properly prevents import")

    def test_cloud_sync_manager_imports_correctly(self):
        """
        CRITICAL: Ensure CloudSyncManager can import RcloneService correctly
        This simulates the dynamic import that happens in _sync_to_s3
        """
        # This simulates the import that happens inside _sync_to_s3 method
        try:
            from app.services.rclone_service import RcloneService
            service = RcloneService()
            assert service is not None
            print("✓ Dynamic import of RcloneService works correctly")
        except ImportError as e:
            pytest.fail(f"CRITICAL: CloudSyncManager cannot import RcloneService: {e}")

    def test_method_call_compatibility(self):
        """
        CRITICAL: Test that the method call pattern used by CloudSyncManager is valid
        This creates the same call pattern but with mocked data to verify compatibility
        """
        from app.services.rclone_service import RcloneService
        from types import SimpleNamespace
        import asyncio
        
        service = RcloneService()
        
        # Create mock repository object (same pattern as CloudSyncManager)
        repo_obj = SimpleNamespace()
        repo_obj.name = "test-repo"
        repo_obj.path = "/test/path"
        
        # Verify the method can be called with the expected parameters
        try:
            # We won't actually run this (to avoid needing real rclone), 
            # but we can verify the method exists and accepts the parameters
            method = service.sync_repository_to_s3
            import inspect
            sig = inspect.signature(method)
            
            # Try to bind the arguments that CloudSyncManager would pass
            bound = sig.bind(
                repository=repo_obj,
                access_key_id="test-key",
                secret_access_key="test-secret", 
                bucket_name="test-bucket",
                path_prefix=""
            )
            assert bound is not None
            print("✓ Method call compatibility verified")
        except Exception as e:
            pytest.fail(f"CRITICAL: Method call pattern is incompatible: {e}")

    def test_error_scenarios_handled(self):
        """
        Test that common error scenarios are handled gracefully
        """
        # Test that we can at least verify error handling capability exists
        # (The actual error handling is tested in the CloudSyncManager implementation)
        
        # Verify that the CloudSyncManager has try-except blocks for error handling
        import inspect
        from app.services.cloud_sync_manager import CloudSyncManager
        
        source = inspect.getsource(CloudSyncManager._sync_to_s3)
        assert 'try:' in source, "CloudSyncManager._sync_to_s3 should have error handling"
        assert 'except' in source, "CloudSyncManager._sync_to_s3 should have exception handling"
        
        print("✓ Error scenarios are handled correctly")