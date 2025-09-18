"""
Tests for the enhanced generic rclone integration pattern.

This module tests the registry-based rclone integration including:
- RcloneMethodMapping dataclass
- Provider registration with rclone mappings
- Generic dispatchers using registry
- Auto-discovery of mappings from storage classes
- Validation of rclone integration
"""

import pytest
from unittest.mock import MagicMock

from borgitory.services.cloud_providers.registry import (
    RcloneMethodMapping,
    ProviderMetadata,
    register_provider,
    validate_rclone_integration,
    get_metadata,
    clear_registry,
)
from borgitory.services.rclone_service import RcloneService
from borgitory.models.database import Repository


class TestRcloneMethodMapping:
    """Test RcloneMethodMapping dataclass"""

    def test_create_mapping_with_all_fields(self) -> None:
        """Test creating mapping with all fields"""
        mapping = RcloneMethodMapping(
            sync_method="sync_repo_to_test",
            test_method="test_connection",
            parameter_mapping={"config_field": "rclone_param"},
            required_params=["param1", "param2"],
            optional_params={"opt1": "default1"},
        )

        assert mapping.sync_method == "sync_repo_to_test"
        assert mapping.test_method == "test_connection"
        assert mapping.parameter_mapping == {"config_field": "rclone_param"}
        assert mapping.required_params == ["param1", "param2"]
        assert mapping.optional_params == {"opt1": "default1"}

    def test_create_mapping_with_minimal_fields(self) -> None:
        """Test creating mapping with minimal required fields"""
        mapping = RcloneMethodMapping(
            sync_method="sync_method",
            test_method="test_method",
            parameter_mapping={},
            required_params=[],
        )

        assert mapping.optional_params == {}  # Should default to empty dict

    def test_mapping_optional_params_default(self) -> None:
        """Test that optional_params defaults to empty dict"""
        mapping = RcloneMethodMapping(
            sync_method="sync",
            test_method="test",
            parameter_mapping={},
            required_params=[],
        )

        assert isinstance(mapping.optional_params, dict)
        assert len(mapping.optional_params) == 0


class TestProviderMetadataWithRclone:
    """Test ProviderMetadata with rclone mapping"""

    def test_metadata_with_rclone_mapping(self) -> None:
        """Test creating metadata with rclone mapping"""
        mapping = RcloneMethodMapping(
            sync_method="sync_test",
            test_method="test_test",
            parameter_mapping={"field": "param"},
            required_params=["param"],
        )

        metadata = ProviderMetadata(
            name="test",
            label="Test Provider",
            description="Test provider",
            rclone_mapping=mapping,
        )

        assert metadata.rclone_mapping is not None
        assert metadata.rclone_mapping.sync_method == "sync_test"

    def test_metadata_without_rclone_mapping(self) -> None:
        """Test creating metadata without rclone mapping"""
        metadata = ProviderMetadata(
            name="test", label="Test Provider", description="Test provider"
        )

        assert metadata.rclone_mapping is None


class TestRegistryRcloneIntegration:
    """Test registry integration with rclone mappings"""

    def setup_method(self) -> None:
        """Clear registry before each test"""
        clear_registry()

    def test_register_provider_with_explicit_rclone_mapping(self) -> None:
        """Test registering provider with explicit rclone mapping"""
        mapping = RcloneMethodMapping(
            sync_method="sync_test",
            test_method="test_test",
            parameter_mapping={"config_field": "rclone_param"},
            required_params=["rclone_param"],
        )

        @register_provider(
            name="test_provider", label="Test Provider", rclone_mapping=mapping
        )
        class TestProvider:
            config_class = MagicMock()
            storage_class = MagicMock()

        metadata = get_metadata("test_provider")
        assert metadata is not None
        assert metadata.rclone_mapping is not None
        assert metadata.rclone_mapping.sync_method == "sync_test"

    def test_register_provider_with_auto_discovery(self) -> None:
        """Test registering provider with auto-discovery from storage class"""

        # Create a mock storage class with get_rclone_mapping method
        mock_storage_class = MagicMock()
        mock_mapping = RcloneMethodMapping(
            sync_method="auto_sync",
            test_method="auto_test",
            parameter_mapping={"auto_field": "auto_param"},
            required_params=["auto_param"],
        )
        mock_storage_class.get_rclone_mapping.return_value = mock_mapping

        @register_provider(name="auto_provider", label="Auto Provider")
        class AutoProvider:
            config_class = MagicMock()
            storage_class = mock_storage_class

        metadata = get_metadata("auto_provider")
        assert metadata is not None
        assert metadata.rclone_mapping is not None
        assert metadata.rclone_mapping.sync_method == "auto_sync"
        mock_storage_class.get_rclone_mapping.assert_called_once()

    def test_register_provider_auto_discovery_failure(self) -> None:
        """Test auto-discovery gracefully handles failures"""

        # Create a mock storage class that raises exception
        mock_storage_class = MagicMock()
        mock_storage_class.get_rclone_mapping.side_effect = Exception(
            "Discovery failed"
        )

        @register_provider(name="failing_provider", label="Failing Provider")
        class FailingProvider:
            config_class = MagicMock()
            storage_class = mock_storage_class

        metadata = get_metadata("failing_provider")
        assert metadata is not None
        assert metadata.rclone_mapping is None  # Should be None due to exception


class TestRcloneValidation:
    """Test rclone integration validation"""

    def setup_method(self) -> None:
        """Clear registry before each test"""
        clear_registry()

    def test_validate_valid_provider(self) -> None:
        """Test validating a properly configured provider"""
        mapping = RcloneMethodMapping(
            sync_method="sync_repository_to_s3",  # This method exists in RcloneService
            test_method="test_s3_connection",  # This method exists in RcloneService
            parameter_mapping={"field": "param"},
            required_params=["param"],
        )

        @register_provider(name="valid_provider", rclone_mapping=mapping)
        class ValidProvider:
            config_class = MagicMock()
            storage_class = MagicMock()

        rclone_service = RcloneService()
        errors = validate_rclone_integration("valid_provider", rclone_service)
        assert len(errors) == 0

    def test_validate_provider_missing_mapping(self) -> None:
        """Test validating provider without rclone mapping"""
        # Create proper mock classes
        mock_config_class = type("MockConfig", (), {})
        mock_storage_class = type("MockStorage", (), {})

        @register_provider(name="no_mapping_provider")
        class NoMappingProvider:
            config_class = mock_config_class
            storage_class = mock_storage_class

        rclone_service = RcloneService()
        errors = validate_rclone_integration("no_mapping_provider", rclone_service)
        assert len(errors) > 0
        assert any("no rclone mapping configured" in error for error in errors)

    def test_validate_provider_missing_sync_method(self) -> None:
        """Test validating provider with missing sync method"""
        mapping = RcloneMethodMapping(
            sync_method="nonexistent_sync_method",
            test_method="test_s3_connection",
            parameter_mapping={"field": "param"},
            required_params=["param"],
        )

        @register_provider(name="missing_sync_provider", rclone_mapping=mapping)
        class MissingSyncProvider:
            config_class = MagicMock()
            storage_class = MagicMock()

        rclone_service = RcloneService()
        errors = validate_rclone_integration("missing_sync_provider", rclone_service)
        assert len(errors) > 0
        assert any("sync method" in error and "not found" in error for error in errors)

    def test_validate_provider_missing_test_method(self) -> None:
        """Test validating provider with missing test method"""
        mapping = RcloneMethodMapping(
            sync_method="sync_repository_to_s3",
            test_method="nonexistent_test_method",
            parameter_mapping={"field": "param"},
            required_params=["param"],
        )

        @register_provider(name="missing_test_provider", rclone_mapping=mapping)
        class MissingTestProvider:
            config_class = MagicMock()
            storage_class = MagicMock()

        rclone_service = RcloneService()
        errors = validate_rclone_integration("missing_test_provider", rclone_service)
        assert len(errors) > 0
        assert any("test method" in error and "not found" in error for error in errors)

    def test_validate_nonexistent_provider(self) -> None:
        """Test validating a provider that doesn't exist"""
        rclone_service = RcloneService()
        errors = validate_rclone_integration("nonexistent_provider", rclone_service)
        assert len(errors) > 0
        assert any("not registered" in error for error in errors)

    def test_validate_requires_rclone_service(self) -> None:
        """Test that validation requires rclone service"""
        errors = validate_rclone_integration("any_provider", None)
        assert len(errors) > 0
        assert any("Rclone service is required" in error for error in errors)


class TestGenericRcloneDispatchers:
    """Test the generic rclone dispatcher methods"""

    @pytest.fixture(autouse=True)
    def ensure_providers_registered(self) -> None:
        """Ensure real providers are registered for dispatcher tests"""
        # Import to trigger registration

    def test_generic_dispatchers_exist(self) -> None:
        """Test that generic dispatcher methods exist on RcloneService"""
        rclone_service = RcloneService()

        # Check that the new generic methods exist
        assert hasattr(rclone_service, "sync_repository_to_provider")
        assert hasattr(rclone_service, "test_provider_connection")

        # Check that they are callable
        assert callable(rclone_service.sync_repository_to_provider)
        assert callable(rclone_service.test_provider_connection)

    @pytest.mark.asyncio
    async def test_sync_repository_to_provider_missing_provider(self) -> None:
        """Test sync with nonexistent provider"""
        rclone_service = RcloneService()
        repository = MagicMock(spec=Repository)

        with pytest.raises(ValueError, match="no rclone mapping configured"):
            async for _ in rclone_service.sync_repository_to_provider(
                "nonexistent_provider", repository
            ):
                pass

    @pytest.mark.asyncio
    async def test_test_provider_connection_missing_method(self) -> None:
        """Test connection test with missing rclone method"""
        # Register a provider with a non-existent test method
        mapping = RcloneMethodMapping(
            sync_method="sync_repository_to_s3",
            test_method="nonexistent_test_method",
            parameter_mapping={"config_field": "rclone_param"},
            required_params=["rclone_param"],
        )

        mock_config_class = type("MockConfig", (), {})
        mock_storage_class = type("MockStorage", (), {})

        @register_provider(name="missing_method_provider", rclone_mapping=mapping)
        class MissingMethodProvider:
            config_class = mock_config_class
            storage_class = mock_storage_class

        rclone_service = RcloneService()

        with pytest.raises(ValueError, match="not found"):
            await rclone_service.test_provider_connection(
                "missing_method_provider", config_field="test_value"
            )


class TestIsolatedRcloneDispatchers:
    """Test rclone dispatchers in isolation with registry clearing"""

    def setup_method(self) -> None:
        """Clear registry before each test"""
        clear_registry()

    @pytest.mark.asyncio
    async def test_sync_repository_to_provider_missing_parameters(self) -> None:
        """Test sync with missing required parameters"""
        # Register a test provider with strict requirements
        mapping = RcloneMethodMapping(
            sync_method="sync_repository_to_s3",  # Use real method
            test_method="test_s3_connection",
            parameter_mapping={"config_field": "access_key_id"},
            required_params=["repository", "access_key_id", "missing_param"],
        )

        mock_config_class = type("MockConfig", (), {})
        mock_storage_class = type("MockStorage", (), {})

        @register_provider(name="missing_param_provider", rclone_mapping=mapping)
        class MissingParamProvider:
            config_class = mock_config_class
            storage_class = mock_storage_class

        rclone_service = RcloneService()
        repository = MagicMock(spec=Repository)
        provider_config = {"config_field": "test_value"}  # missing_param not provided

        with pytest.raises(ValueError, match="Missing required parameters"):
            async for _ in rclone_service.sync_repository_to_provider(
                "missing_param_provider", repository, **provider_config
            ):
                pass


class TestRealProviderIntegration:
    """Test integration with real providers (S3, SFTP, SMB)"""

    @pytest.fixture(autouse=True)
    def ensure_providers_registered(self) -> None:
        """Ensure real providers are registered for these tests"""
        # Import to trigger registration

    def test_real_providers_have_rclone_mappings_via_storage_classes(self) -> None:
        """Test that real providers have rclone mappings via their storage classes"""
        # Test that storage classes can provide mappings directly
        from borgitory.services.cloud_providers.storage.s3_storage import S3Storage
        from borgitory.services.cloud_providers.storage.sftp_storage import SFTPStorage
        from borgitory.services.cloud_providers.storage.smb_storage import SMBStorage

        storage_classes = [
            (S3Storage, "s3"),
            (SFTPStorage, "sftp"),
            (SMBStorage, "smb"),
        ]

        for storage_class, provider_name in storage_classes:
            # Test that the storage class has the method
            assert hasattr(storage_class, "get_rclone_mapping"), (
                f"{storage_class.__name__} missing get_rclone_mapping method"
            )

            # Test that the method returns a valid mapping
            mapping = storage_class.get_rclone_mapping()
            assert isinstance(mapping, RcloneMethodMapping)
            assert mapping.sync_method, f"{provider_name} missing sync method"
            assert mapping.test_method, f"{provider_name} missing test method"
            assert isinstance(mapping.parameter_mapping, dict), (
                f"{provider_name} parameter mapping not a dict"
            )
            assert isinstance(mapping.required_params, list), (
                f"{provider_name} required params not a list"
            )
            assert len(mapping.parameter_mapping) > 0, (
                f"{provider_name} has empty parameter mapping"
            )
            assert len(mapping.required_params) > 0, (
                f"{provider_name} has no required params"
            )

    def test_real_providers_validation(self) -> None:
        """Test that all real providers pass validation"""
        from borgitory.services.rclone_service import RcloneService
        from borgitory.services.cloud_providers.registry import get_supported_providers

        rclone_service = RcloneService()
        providers = get_supported_providers()
        expected_providers = ["s3", "sftp", "smb"]

        for provider in expected_providers:
            if provider in providers:
                errors = validate_rclone_integration(provider, rclone_service)
                assert len(errors) == 0, (
                    f"Provider {provider} has validation errors: {errors}"
                )

    def test_storage_classes_have_get_rclone_mapping(self) -> None:
        """Test that all storage classes have get_rclone_mapping method"""
        from borgitory.services.cloud_providers.storage.s3_storage import S3Storage
        from borgitory.services.cloud_providers.storage.sftp_storage import SFTPStorage
        from borgitory.services.cloud_providers.storage.smb_storage import SMBStorage

        storage_classes = [S3Storage, SFTPStorage, SMBStorage]

        for storage_class in storage_classes:
            assert hasattr(storage_class, "get_rclone_mapping"), (
                f"{storage_class.__name__} missing get_rclone_mapping method"
            )

            # Test that the method returns a valid mapping
            mapping = storage_class.get_rclone_mapping()
            assert isinstance(mapping, RcloneMethodMapping)
            assert mapping.sync_method
            assert mapping.test_method
            assert isinstance(mapping.parameter_mapping, dict)
            assert isinstance(mapping.required_params, list)
