import pytest
from pydantic import BaseModel, Field

from borgitory.services.cloud_providers.registry import (
    ProviderRegistry,
    ProviderMetadata,
    register_provider,
    get_config_class,
    get_storage_class,
    get_metadata,
    get_supported_providers,
    get_provider_info,
    get_all_provider_info,
    is_provider_registered,
    clear_registry,
    get_registry,
)
from borgitory.services.rclone_service import RcloneService


# Mock classes for testing
class MockConfigClass(BaseModel):
    test_field: str = Field(..., description="Test field")


class MockStorageClass:
    def __init__(self, config: MockConfigClass, rclone_service: RcloneService) -> None:
        self.config = config
        self.rclone_service = rclone_service


class TestProviderMetadata:
    """Test ProviderMetadata dataclass"""

    def test_create_metadata_with_defaults(self) -> None:
        """Test creating metadata with default values"""
        metadata = ProviderMetadata(
            name="test", label="Test Provider", description="Test description"
        )

        assert metadata.name == "test"
        assert metadata.label == "Test Provider"
        assert metadata.description == "Test description"
        assert metadata.supports_encryption is True
        assert metadata.supports_versioning is False
        assert metadata.requires_credentials is True
        assert metadata.additional_info == {}

    def test_create_metadata_with_custom_values(self) -> None:
        """Test creating metadata with custom values"""
        metadata = ProviderMetadata(
            name="test",
            label="Test Provider",
            description="Test description",
            supports_encryption=False,
            supports_versioning=True,
            requires_credentials=False,
            additional_info={"custom": "value"},
        )

        assert metadata.supports_encryption is False
        assert metadata.supports_versioning is True
        assert metadata.requires_credentials is False
        assert metadata.additional_info == {"custom": "value"}


class TestProviderRegistry:
    """Test ProviderRegistry class"""

    @pytest.fixture
    def registry(self) -> ProviderRegistry:
        """Create a fresh registry for each test"""
        return ProviderRegistry()

    @pytest.fixture
    def sample_metadata(self) -> ProviderMetadata:
        """Sample metadata for testing"""
        return ProviderMetadata(
            name="test", label="Test Provider", description="Test storage provider"
        )

    def test_register_provider(
        self, registry: ProviderRegistry, sample_metadata: ProviderMetadata
    ) -> None:
        """Test registering a provider"""
        registry.register_provider(
            name="test",
            config_class=MockConfigClass,
            storage_class=MockStorageClass,
            metadata=sample_metadata,
        )

        assert registry.get_config_class("test") == MockConfigClass
        assert registry.get_storage_class("test") == MockStorageClass
        assert registry.get_metadata("test") == sample_metadata
        assert "test" in registry.get_supported_providers()

    def test_register_duplicate_provider(
        self, registry: ProviderRegistry, sample_metadata: ProviderMetadata
    ) -> None:
        """Test registering a provider with the same name twice"""
        # First registration
        registry.register_provider(
            name="test",
            config_class=MockConfigClass,
            storage_class=MockStorageClass,
            metadata=sample_metadata,
        )

        # Second registration (should overwrite)
        class AnotherConfigClass(BaseModel):
            pass

        registry.register_provider(
            name="test",
            config_class=AnotherConfigClass,
            storage_class=MockStorageClass,
            metadata=sample_metadata,
        )

        assert registry.get_config_class("test") == AnotherConfigClass

    def test_get_nonexistent_provider(self, registry: ProviderRegistry) -> None:
        """Test getting a provider that doesn't exist"""
        assert registry.get_config_class("nonexistent") is None
        assert registry.get_storage_class("nonexistent") is None
        assert registry.get_metadata("nonexistent") is None

    def test_get_provider_info(
        self, registry: ProviderRegistry, sample_metadata: ProviderMetadata
    ) -> None:
        """Test getting provider info"""
        registry.register_provider(
            name="test",
            config_class=MockConfigClass,
            storage_class=MockStorageClass,
            metadata=sample_metadata,
        )

        info = registry.get_provider_info("test")
        assert info is not None
        assert info.name == "test"
        assert info.label == "Test Provider"
        assert info.description == "Test storage provider"
        assert info.config_class == "MockConfigClass"
        assert info.storage_class == "MockStorageClass"
        assert info.supports_encryption is True
        assert info.supports_versioning is False
        assert info.requires_credentials is True

    def test_get_all_provider_info(self, registry: ProviderRegistry) -> None:
        """Test getting info for all providers"""
        metadata1 = ProviderMetadata(
            name="test1", label="Test 1", description="First test"
        )
        metadata2 = ProviderMetadata(
            name="test2", label="Test 2", description="Second test"
        )

        registry.register_provider(
            "test1", MockConfigClass, MockStorageClass, metadata1
        )
        registry.register_provider(
            "test2", MockConfigClass, MockStorageClass, metadata2
        )

        all_info = registry.get_all_provider_info()
        assert len(all_info) == 2
        assert "test1" in all_info
        assert "test2" in all_info
        assert all_info["test1"].label == "Test 1"
        assert all_info["test2"].label == "Test 2"

    def test_is_provider_registered(
        self, registry: ProviderRegistry, sample_metadata: ProviderMetadata
    ) -> None:
        """Test checking if provider is registered"""
        assert not registry.is_provider_registered("test")

        registry.register_provider(
            "test", MockConfigClass, MockStorageClass, sample_metadata
        )

        assert registry.is_provider_registered("test")

    def test_unregister_provider(
        self, registry: ProviderRegistry, sample_metadata: ProviderMetadata
    ) -> None:
        """Test unregistering a provider"""
        registry.register_provider(
            "test", MockConfigClass, MockStorageClass, sample_metadata
        )
        assert registry.is_provider_registered("test")

        result = registry.unregister_provider("test")
        assert result is True
        assert not registry.is_provider_registered("test")

        # Try to unregister again
        result = registry.unregister_provider("test")
        assert result is False


class TestRegisterProviderDecorator:
    """Test the @register_provider decorator"""

    def setup_method(self) -> None:
        """Clear registry before each test"""
        clear_registry()

    def teardown_method(self) -> None:
        """Clear registry after each test"""
        clear_registry()

    def test_register_provider_decorator(self) -> None:
        """Test using the @register_provider decorator"""

        @register_provider(
            name="test", label="Test Provider", description="Test storage provider"
        )
        class TestProvider:
            config_class = MockConfigClass
            storage_class = MockStorageClass

        assert is_provider_registered("test")
        assert get_config_class("test") == MockConfigClass
        assert get_storage_class("test") == MockStorageClass

        metadata = get_metadata("test")
        assert metadata is not None
        assert metadata.name == "test"
        assert metadata.label == "Test Provider"
        assert metadata.description == "Test storage provider"

    def test_register_provider_decorator_with_defaults(self) -> None:
        """Test decorator with default values"""

        @register_provider(name="test")
        class TestProvider:
            config_class = MockConfigClass
            storage_class = MockStorageClass

        metadata = get_metadata("test")
        assert metadata is not None
        assert metadata.label == "TEST"
        assert metadata.description == "TEST storage provider"
        assert metadata.supports_encryption is True
        assert metadata.supports_versioning is False

    def test_register_provider_decorator_with_custom_metadata(self) -> None:
        """Test decorator with custom metadata"""

        @register_provider(
            name="test",
            label="Custom Provider",
            description="Custom description",
            supports_versioning=True,
            custom_field="custom_value",
        )
        class TestProvider:
            config_class = MockConfigClass
            storage_class = MockStorageClass

        metadata = get_metadata("test")
        assert metadata is not None
        assert metadata.supports_versioning is True
        assert metadata.additional_info["custom_field"] == "custom_value"

    def test_register_provider_missing_config_class(self) -> None:
        """Test decorator with missing config_class"""
        with pytest.raises(ValueError, match="must have 'config_class' attribute"):

            @register_provider(name="test")
            class TestProvider:
                storage_class = MockStorageClass

    def test_register_provider_missing_storage_class(self) -> None:
        """Test decorator with missing storage_class"""
        with pytest.raises(ValueError, match="must have 'storage_class' attribute"):

            @register_provider(name="test")
            class TestProvider:
                config_class = MockConfigClass


class TestGlobalRegistryFunctions:
    """Test global registry convenience functions"""

    def setup_method(self) -> None:
        """Clear registry before each test"""
        clear_registry()

    def teardown_method(self) -> None:
        """Clear registry after each test"""
        clear_registry()

    def test_global_functions(self) -> None:
        """Test that global functions work with the global registry"""

        @register_provider(name="test", label="Test")
        class TestProvider:
            config_class = MockConfigClass
            storage_class = MockStorageClass

        # Test all global functions
        assert get_config_class("test") == MockConfigClass
        assert get_storage_class("test") == MockStorageClass
        metadata = get_metadata("test")
        assert metadata is not None
        assert metadata.name == "test"
        assert "test" in get_supported_providers()
        provider_info = get_provider_info("test")
        assert provider_info is not None
        assert provider_info.name == "test"
        assert "test" in get_all_provider_info()
        assert is_provider_registered("test")

    def test_get_registry(self) -> None:
        """Test getting the global registry instance"""
        registry = get_registry()
        assert isinstance(registry, ProviderRegistry)

    def test_clear_registry(self) -> None:
        """Test clearing the global registry"""

        @register_provider(name="test")
        class TestProvider:
            config_class = MockConfigClass
            storage_class = MockStorageClass

        assert is_provider_registered("test")

        clear_registry()

        assert not is_provider_registered("test")
        assert len(get_supported_providers()) == 0
