"""
Tests for RepositoryCheckConfigService - Business logic tests
"""

import pytest
from sqlalchemy.orm import Session
from borgitory.services.repositories.repository_check_config_service import (
    RepositoryCheckConfigService,
)
from borgitory.models.database import RepositoryCheckConfig, Repository


@pytest.fixture
def service(test_db: Session):
    """RepositoryCheckConfigService instance with real database session."""
    return RepositoryCheckConfigService(test_db)


@pytest.fixture
def sample_repository(test_db: Session):
    """Create a sample repository for testing."""
    repository = Repository(
        name="test-repo",
        path="/tmp/test-repo",
        encrypted_passphrase="test-encrypted-passphrase",
    )
    test_db.add(repository)
    test_db.commit()
    test_db.refresh(repository)
    return repository


@pytest.fixture
def sample_config(test_db: Session):
    """Create a sample repository check config for testing."""
    config = RepositoryCheckConfig(
        name="test-config",
        description="Test configuration",
        check_type="full",
        verify_data=False,
        repair_mode=False,
        save_space=False,
        enabled=True,
    )
    test_db.add(config)
    test_db.commit()
    test_db.refresh(config)
    return config


class TestRepositoryCheckConfigService:
    """Test class for RepositoryCheckConfigService business logic."""

    def test_get_all_configs_empty(self, service) -> None:
        """Test getting configs when none exist."""
        result = service.get_all_configs()
        assert result == []

    def test_get_all_configs_with_data(self, service, test_db: Session) -> None:
        """Test getting configs with data."""
        config1 = RepositoryCheckConfig(
            name="config-1", description="First config", check_type="full", enabled=True
        )
        config2 = RepositoryCheckConfig(
            name="config-2",
            description="Second config",
            check_type="repository_only",
            enabled=False,
        )
        test_db.add(config1)
        test_db.add(config2)
        test_db.commit()

        result = service.get_all_configs()
        assert len(result) == 2
        names = [c.name for c in result]
        assert "config-1" in names
        assert "config-2" in names

    def test_get_all_configs_ordered_by_name(self, service, test_db: Session) -> None:
        """Test configs are returned ordered by name."""
        config_z = RepositoryCheckConfig(name="z-config", check_type="full")
        config_a = RepositoryCheckConfig(name="a-config", check_type="full")
        config_m = RepositoryCheckConfig(name="m-config", check_type="full")

        test_db.add(config_z)
        test_db.add(config_a)
        test_db.add(config_m)
        test_db.commit()

        result = service.get_all_configs()
        names = [c.name for c in result]
        assert names == ["a-config", "m-config", "z-config"]

    def test_get_enabled_configs_only(self, service, test_db: Session) -> None:
        """Test getting only enabled configs."""
        enabled_config = RepositoryCheckConfig(
            name="enabled-config", check_type="full", enabled=True
        )
        disabled_config = RepositoryCheckConfig(
            name="disabled-config", check_type="full", enabled=False
        )
        test_db.add(enabled_config)
        test_db.add(disabled_config)
        test_db.commit()

        result = service.get_enabled_configs()
        assert len(result) == 1
        assert result[0].name == "enabled-config"
        assert result[0].enabled is True

    def test_get_config_by_id_success(self, service, sample_config) -> None:
        """Test getting config by ID successfully."""
        result = service.get_config_by_id(sample_config.id)
        assert result is not None
        assert result.name == "test-config"
        assert result.id == sample_config.id

    def test_get_config_by_id_not_found(self, service) -> None:
        """Test getting non-existent config by ID."""
        result = service.get_config_by_id(999)
        assert result is None

    def test_get_config_by_name_success(self, service, sample_config) -> None:
        """Test getting config by name successfully."""
        result = service.get_config_by_name("test-config")
        assert result is not None
        assert result.name == "test-config"
        assert result.id == sample_config.id

    def test_get_config_by_name_not_found(self, service) -> None:
        """Test getting non-existent config by name."""
        result = service.get_config_by_name("non-existent")
        assert result is None

    def test_create_config_success(self, service, test_db: Session) -> None:
        """Test successful config creation."""
        success, config, error = service.create_config(
            name="new-config",
            description="New test config",
            check_type="repository_only",
            verify_data=True,
            repair_mode=False,
            save_space=True,
            max_duration=3600,
            archive_prefix="test-",
            archive_glob="*.tar",
            first_n_archives=5,
            last_n_archives=10,
        )

        assert success is True
        assert error is None
        assert config.name == "new-config"
        assert config.description == "New test config"
        assert config.check_type == "repository_only"
        assert config.verify_data is True
        assert config.repair_mode is False
        assert config.save_space is True
        assert config.max_duration == 3600
        assert config.archive_prefix == "test-"
        assert config.archive_glob == "*.tar"
        assert config.first_n_archives == 5
        assert config.last_n_archives == 10
        assert config.enabled is True  # Default value

        # Verify saved to database
        saved_config = (
            test_db.query(RepositoryCheckConfig)
            .filter(RepositoryCheckConfig.name == "new-config")
            .first()
        )
        assert saved_config is not None
        assert saved_config.check_type == "repository_only"

    def test_create_config_duplicate_name(self, service, sample_config) -> None:
        """Test config creation with duplicate name."""
        success, config, error = service.create_config(
            name="test-config",  # Same as sample_config
            check_type="full",
        )

        assert success is False
        assert config is None
        assert "already exists" in error

    def test_create_config_minimal_data(self, service) -> None:
        """Test config creation with minimal required data."""
        success, config, error = service.create_config(name="minimal-config")

        assert success is True
        assert error is None
        assert config.name == "minimal-config"
        assert config.check_type == "full"  # Default
        assert config.verify_data is False  # Default
        assert config.enabled is True  # Default

    def test_update_config_success(self, service, test_db, sample_config) -> None:
        """Test successful config update."""
        update_data = {
            "description": "Updated description",
            "check_type": "repository_only",
            "verify_data": True,
            "max_duration": 7200,
        }

        success, updated_config, error = service.update_config(
            sample_config.id, update_data
        )

        assert success is True
        assert error is None
        assert updated_config.description == "Updated description"
        assert updated_config.check_type == "repository_only"
        assert updated_config.verify_data is True
        assert updated_config.max_duration == 7200
        # Unchanged fields should remain the same
        assert updated_config.name == "test-config"

    def test_update_config_not_found(self, service) -> None:
        """Test updating non-existent config."""
        success, config, error = service.update_config(999, {"name": "new-name"})

        assert success is False
        assert config is None
        assert "not found" in error

    def test_update_config_name_conflict(self, service, test_db, sample_config) -> None:
        """Test updating config name to an existing name."""
        # Create another config
        other_config = RepositoryCheckConfig(name="other-config", check_type="full")
        test_db.add(other_config)
        test_db.commit()

        success, config, error = service.update_config(
            sample_config.id, {"name": "other-config"}
        )

        assert success is False
        assert config is None
        assert "already exists" in error

    def test_update_config_same_name_allowed(self, service, sample_config) -> None:
        """Test updating config with same name is allowed."""
        success, config, error = service.update_config(
            sample_config.id, {"name": "test-config", "description": "Updated"}
        )

        assert success is True
        assert error is None
        assert config.name == "test-config"
        assert config.description == "Updated"

    def test_enable_config_success(self, service, test_db: Session) -> None:
        """Test successful config enabling."""
        # Create disabled config
        config = RepositoryCheckConfig(
            name="disabled-config", check_type="full", enabled=False
        )
        test_db.add(config)
        test_db.commit()
        test_db.refresh(config)

        success, success_msg, error = service.enable_config(config.id)

        assert success is True
        assert error is None
        assert "enabled successfully" in success_msg
        assert config.name in success_msg

        # Verify in database
        test_db.refresh(config)
        assert config.enabled is True

    def test_enable_config_not_found(self, service) -> None:
        """Test enabling non-existent config."""
        success, success_msg, error = service.enable_config(999)

        assert success is False
        assert success_msg is None
        assert "not found" in error

    def test_disable_config_success(self, service, test_db: Session) -> None:
        """Test successful config disabling."""
        # Create enabled config
        config = RepositoryCheckConfig(
            name="enabled-config", check_type="full", enabled=True
        )
        test_db.add(config)
        test_db.commit()
        test_db.refresh(config)

        success, success_msg, error = service.disable_config(config.id)

        assert success is True
        assert error is None
        assert "disabled successfully" in success_msg
        assert config.name in success_msg

        # Verify in database
        test_db.refresh(config)
        assert config.enabled is False

    def test_disable_config_not_found(self, service) -> None:
        """Test disabling non-existent config."""
        success, success_msg, error = service.disable_config(999)

        assert success is False
        assert success_msg is None
        assert "not found" in error

    def test_delete_config_success(self, service, test_db, sample_config) -> None:
        """Test successful config deletion."""
        config_id = sample_config.id
        config_name = sample_config.name

        success, returned_name, error = service.delete_config(config_id)

        assert success is True
        assert returned_name == config_name
        assert error is None

        # Verify removed from database
        deleted_config = (
            test_db.query(RepositoryCheckConfig)
            .filter(RepositoryCheckConfig.id == config_id)
            .first()
        )
        assert deleted_config is None

    def test_delete_config_not_found(self, service) -> None:
        """Test deleting non-existent config."""
        success, name, error = service.delete_config(999)

        assert success is False
        assert name is None
        assert "not found" in error

    def test_get_form_data_success(self, service, test_db, sample_repository) -> None:
        """Test getting form data successfully."""
        # Create some configs
        enabled_config = RepositoryCheckConfig(
            name="enabled-config", check_type="full", enabled=True
        )
        disabled_config = RepositoryCheckConfig(
            name="disabled-config", check_type="full", enabled=False
        )
        test_db.add(enabled_config)
        test_db.add(disabled_config)
        test_db.commit()

        result = service.get_form_data()

        assert "repositories" in result
        assert "check_configs" in result

        # Should contain our sample repository
        assert len(result["repositories"]) == 1
        assert result["repositories"][0].name == "test-repo"

        # Should only contain enabled configs
        assert len(result["check_configs"]) == 1
        assert result["check_configs"][0].name == "enabled-config"

    def test_get_form_data_empty_database(self, service) -> None:
        """Test getting form data when database is empty."""
        result = service.get_form_data()

        assert "repositories" in result
        assert "check_configs" in result
        assert result["repositories"] == []
        assert result["check_configs"] == []

    def test_config_lifecycle(self, service, test_db: Session) -> None:
        """Test complete config lifecycle: create, update, enable/disable, delete."""
        # Create
        success, created_config, error = service.create_config(
            name="lifecycle-test",
            description="Test config lifecycle",
            check_type="full",
        )
        assert success is True
        config_id = created_config.id

        # Update
        success, updated_config, error = service.update_config(
            config_id, {"check_type": "repository_only", "verify_data": True}
        )
        assert success is True
        assert updated_config.check_type == "repository_only"
        assert updated_config.verify_data is True

        # Disable
        success, success_msg, error = service.disable_config(config_id)
        assert success is True

        # Enable
        success, success_msg, error = service.enable_config(config_id)
        assert success is True

        # Delete
        success, config_name, error = service.delete_config(config_id)
        assert success is True
        assert config_name == "lifecycle-test"

        # Verify completely removed
        deleted_config = (
            test_db.query(RepositoryCheckConfig)
            .filter(RepositoryCheckConfig.id == config_id)
            .first()
        )
        assert deleted_config is None
