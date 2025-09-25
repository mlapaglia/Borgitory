"""
Tests for PruneService - Business logic tests
"""

import pytest
from unittest.mock import patch

from sqlalchemy.orm import Session

from borgitory.services.prune_service import PruneService
from borgitory.models.database import PruneConfig, Repository
from borgitory.models.schemas import PruneConfigCreate, PruneConfigUpdate, PruneStrategy


@pytest.fixture
def service(test_db: Session):
    """PruneService instance with real database session."""
    return PruneService(test_db)


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


class TestPruneService:
    """Test class for PruneService business logic."""

    def test_get_prune_configs_empty(self, service) -> None:
        """Test getting prune configs when none exist."""
        result = service.get_prune_configs()
        assert result == []

    def test_get_prune_configs_with_data(self, service, test_db: Session) -> None:
        """Test getting prune configs with data."""
        config1 = PruneConfig(
            name="config-1",
            strategy="simple",
            keep_within_days=30,
            keep_secondly=0,
            keep_minutely=0,
            keep_hourly=0,
            keep_daily=0,
            keep_weekly=0,
            keep_monthly=0,
            keep_yearly=0,
            enabled=True,
        )
        config2 = PruneConfig(
            name="config-2",
            strategy="advanced",
            keep_secondly=0,
            keep_minutely=0,
            keep_hourly=0,
            keep_daily=7,
            keep_weekly=4,
            keep_monthly=12,
            keep_yearly=2,
            enabled=False,
        )
        test_db.add_all([config1, config2])
        test_db.commit()

        result = service.get_prune_configs()
        assert len(result) == 2
        names = [c.name for c in result]
        assert "config-1" in names
        assert "config-2" in names

    def test_get_prune_configs_with_pagination(self, service, test_db: Session) -> None:
        """Test getting prune configs with pagination."""
        for i in range(5):
            config = PruneConfig(
                name=f"config-{i}",
                strategy="simple",
                keep_within_days=30,
                keep_secondly=0,
                keep_minutely=0,
                keep_hourly=0,
                keep_daily=0,
                keep_weekly=0,
                keep_monthly=0,
                keep_yearly=0,
                enabled=True,
            )
            test_db.add(config)
        test_db.commit()

        result = service.get_prune_configs(skip=2, limit=2)
        assert len(result) == 2

    def test_get_prune_config_by_id_success(self, service, test_db: Session) -> None:
        """Test getting prune config by ID successfully."""
        config = PruneConfig(
            name="test-config",
            strategy="simple",
            keep_within_days=30,
            keep_secondly=0,
            keep_minutely=0,
            keep_hourly=0,
            keep_daily=0,
            keep_weekly=0,
            keep_monthly=0,
            keep_yearly=0,
            enabled=True,
        )
        test_db.add(config)
        test_db.commit()
        test_db.refresh(config)

        result = service.get_prune_config_by_id(config.id)
        assert result is not None
        assert result.name == "test-config"
        assert result.id == config.id

    def test_get_prune_config_by_id_not_found(self, service) -> None:
        """Test getting non-existent prune config raises exception."""
        with pytest.raises(
            Exception, match="Prune configuration with id 999 not found"
        ):
            service.get_prune_config_by_id(999)

    def test_create_prune_config_success(self, service, test_db: Session) -> None:
        """Test successful prune config creation."""
        config_data = PruneConfigCreate(
            name="new-config",
            strategy=PruneStrategy.SIMPLE,
            keep_within_days=30,
            keep_secondly=0,
            keep_minutely=0,
            keep_hourly=0,
            keep_daily=0,
            keep_weekly=0,
            keep_monthly=0,
            keep_yearly=0,
        )

        success, config, error = service.create_prune_config(config_data)

        assert success is True
        assert error is None
        assert config.name == "new-config"
        assert config.strategy == PruneStrategy.SIMPLE
        assert config.keep_within_days == 30
        assert config.enabled is True

        # Verify saved to database
        saved_config = (
            test_db.query(PruneConfig).filter(PruneConfig.name == "new-config").first()
        )
        assert saved_config is not None
        assert saved_config.strategy == PruneStrategy.SIMPLE

    def test_create_prune_config_duplicate_name(
        self, service, test_db: Session
    ) -> None:
        """Test prune config creation with duplicate name."""
        existing_config = PruneConfig(
            name="duplicate-name",
            strategy=PruneStrategy.SIMPLE,
            keep_within_days=30,
            keep_secondly=0,
            keep_minutely=0,
            keep_hourly=0,
            keep_daily=0,
            keep_weekly=0,
            keep_monthly=0,
            keep_yearly=0,
        )
        test_db.add(existing_config)
        test_db.commit()

        config_data = PruneConfigCreate(
            name="duplicate-name",
            strategy=PruneStrategy.ADVANCED,
            keep_within_days=1,
            keep_daily=7,
            keep_secondly=0,
            keep_minutely=0,
            keep_hourly=0,
            keep_weekly=0,
            keep_monthly=0,
            keep_yearly=0,
        )

        success, config, error = service.create_prune_config(config_data)

        assert success is False
        assert config is None
        assert "A prune policy with this name already exists" in error

    def test_create_prune_config_database_error(
        self, service, test_db: Session
    ) -> None:
        """Test prune config creation with database error."""
        config_data = PruneConfigCreate(
            name="error-config",
            strategy=PruneStrategy.SIMPLE,
            keep_within_days=30,
            keep_secondly=0,
            keep_minutely=0,
            keep_hourly=0,
            keep_daily=0,
            keep_weekly=0,
            keep_monthly=0,
            keep_yearly=0,
        )

        with patch.object(test_db, "commit", side_effect=Exception("Database error")):
            success, config, error = service.create_prune_config(config_data)

            assert success is False
            assert config is None
            assert "Failed to create prune configuration" in error

    def test_update_prune_config_success(self, service, test_db: Session) -> None:
        """Test successful prune config update."""
        config = PruneConfig(
            name="original-config",
            strategy=PruneStrategy.SIMPLE,
            keep_within_days=30,
            keep_secondly=0,
            keep_minutely=0,
            keep_hourly=0,
            keep_daily=0,
            keep_weekly=0,
            keep_monthly=0,
            keep_yearly=0,
            enabled=True,
        )
        test_db.add(config)
        test_db.commit()
        test_db.refresh(config)

        config_update = PruneConfigUpdate(name="updated-config", keep_within_days=60)

        success, updated_config, error = service.update_prune_config(
            config.id, config_update
        )

        assert success is True
        assert error is None
        assert updated_config.name == "updated-config"
        assert updated_config.keep_within_days == 60

    def test_update_prune_config_not_found(self, service) -> None:
        """Test updating non-existent prune config."""
        config_update = PruneConfigUpdate(name="new-name")

        success, config, error = service.update_prune_config(999, config_update)

        assert success is False
        assert config is None
        assert "Prune configuration not found" in error

    def test_update_prune_config_duplicate_name(
        self, service, test_db: Session
    ) -> None:
        """Test updating prune config with duplicate name."""
        config1 = PruneConfig(
            name="config-1",
            strategy=PruneStrategy.SIMPLE,
            keep_within_days=30,
            keep_secondly=0,
            keep_minutely=0,
            keep_hourly=0,
            keep_daily=0,
            keep_weekly=0,
            keep_monthly=0,
            keep_yearly=0,
            enabled=True,
        )
        config2 = PruneConfig(
            name="config-2",
            strategy=PruneStrategy.ADVANCED,
            keep_daily=7,
            keep_secondly=0,
            keep_minutely=0,
            keep_hourly=0,
            keep_weekly=0,
            keep_monthly=0,
            keep_yearly=0,
            enabled=True,
        )
        test_db.add_all([config1, config2])
        test_db.commit()

        config_update = PruneConfigUpdate(name="config-2")

        success, config, error = service.update_prune_config(config1.id, config_update)

        assert success is False
        assert config is None
        assert "A prune policy with this name already exists" in error

    def test_enable_prune_config_success(self, service, test_db: Session) -> None:
        """Test successfully enabling prune config."""
        config = PruneConfig(
            name="test-config",
            strategy=PruneStrategy.SIMPLE,
            keep_within_days=30,
            keep_secondly=0,
            keep_minutely=0,
            keep_hourly=0,
            keep_daily=0,
            keep_weekly=0,
            keep_monthly=0,
            keep_yearly=0,
            enabled=False,
        )
        test_db.add(config)
        test_db.commit()
        test_db.refresh(config)

        success, updated_config, error = service.enable_prune_config(config.id)

        assert success is True
        assert error is None
        assert updated_config.enabled is True

    def test_enable_prune_config_not_found(self, service) -> None:
        """Test enabling non-existent prune config."""
        success, config, error = service.enable_prune_config(999)

        assert success is False
        assert config is None
        assert "Prune configuration not found" in error

    def test_disable_prune_config_success(self, service, test_db: Session) -> None:
        """Test successfully disabling prune config."""
        config = PruneConfig(
            name="test-config",
            strategy=PruneStrategy.SIMPLE,
            keep_within_days=30,
            keep_secondly=0,
            keep_minutely=0,
            keep_hourly=0,
            keep_daily=0,
            keep_weekly=0,
            keep_monthly=0,
            keep_yearly=0,
            enabled=True,
        )
        test_db.add(config)
        test_db.commit()
        test_db.refresh(config)

        success, updated_config, error = service.disable_prune_config(config.id)

        assert success is True
        assert error is None
        assert updated_config.enabled is False

    def test_disable_prune_config_not_found(self, service) -> None:
        """Test disabling non-existent prune config."""
        success, config, error = service.disable_prune_config(999)

        assert success is False
        assert config is None
        assert "Prune configuration not found" in error

    def test_delete_prune_config_success(self, service, test_db: Session) -> None:
        """Test successful prune config deletion."""
        config = PruneConfig(
            name="test-config",
            strategy=PruneStrategy.SIMPLE,
            keep_within_days=30,
            keep_secondly=0,
            keep_minutely=0,
            keep_hourly=0,
            keep_daily=0,
            keep_weekly=0,
            keep_monthly=0,
            keep_yearly=0,
            enabled=True,
        )
        test_db.add(config)
        test_db.commit()
        test_db.refresh(config)
        config_id = config.id

        success, config_name, error = service.delete_prune_config(config_id)

        assert success is True
        assert config_name == "test-config"
        assert error is None

        # Verify removed from database
        deleted_config = (
            test_db.query(PruneConfig).filter(PruneConfig.id == config_id).first()
        )
        assert deleted_config is None

    def test_delete_prune_config_not_found(self, service) -> None:
        """Test deleting non-existent prune config."""
        success, config_name, error = service.delete_prune_config(999)

        assert success is False
        assert config_name is None
        assert "Prune configuration not found" in error

    def test_get_configs_with_descriptions_simple_strategy(
        self, service, test_db: Session
    ) -> None:
        """Test getting configs with descriptions for simple strategy."""
        config = PruneConfig(
            name="simple-config",
            strategy=PruneStrategy.SIMPLE,
            keep_within_days=30,
            keep_secondly=0,
            keep_minutely=0,
            keep_hourly=0,
            keep_daily=0,
            keep_weekly=0,
            keep_monthly=0,
            keep_yearly=0,
            enabled=True,
        )
        test_db.add(config)
        test_db.commit()

        result = service.get_configs_with_descriptions()

        assert len(result) == 1
        assert result[0]["description"] == "Keep archives within 30 days"

    def test_get_configs_with_descriptions_advanced_strategy(
        self, service, test_db: Session
    ) -> None:
        """Test getting configs with descriptions for advanced strategy."""
        config = PruneConfig(
            name="advanced-config",
            strategy=PruneStrategy.ADVANCED,
            keep_daily=7,
            keep_weekly=4,
            keep_monthly=12,
            keep_yearly=2,
            enabled=True,
        )
        test_db.add(config)
        test_db.commit()

        result = service.get_configs_with_descriptions()

        assert len(result) == 1
        expected_desc = "7 daily, 4 weekly, 12 monthly, 2 yearly"
        assert result[0]["description"] == expected_desc

    def test_get_configs_with_descriptions_partial_advanced(
        self, service, test_db: Session
    ) -> None:
        """Test getting configs with descriptions for partial advanced strategy."""
        config = PruneConfig(
            name="partial-config",
            strategy=PruneStrategy.ADVANCED,
            keep_daily=7,
            keep_monthly=12,
            enabled=True,
        )
        test_db.add(config)
        test_db.commit()

        result = service.get_configs_with_descriptions()

        assert len(result) == 1
        expected_desc = "7 daily, 12 monthly"
        assert result[0]["description"] == expected_desc

    def test_get_configs_with_descriptions_no_rules(
        self, service, test_db: Session
    ) -> None:
        """Test getting configs with descriptions for no retention rules."""
        config = PruneConfig(
            name="empty-config",
            strategy=PruneStrategy.ADVANCED,
            keep_secondly=0,
            keep_minutely=0,
            keep_hourly=0,
            keep_daily=0,
            keep_weekly=0,
            keep_monthly=0,
            keep_yearly=0,
            enabled=True,
        )
        test_db.add(config)
        test_db.commit()

        result = service.get_configs_with_descriptions()

        assert len(result) == 1
        assert result[0]["description"] == "No retention rules"

    def test_get_configs_with_descriptions_error_handling(self, service) -> None:
        """Test error handling in get_configs_with_descriptions."""
        with patch.object(
            service, "get_prune_configs", side_effect=Exception("Database error")
        ):
            result = service.get_configs_with_descriptions()
            assert result == []

    def test_get_form_data_success(self, service, test_db, sample_repository) -> None:
        """Test successful form data retrieval."""
        result = service.get_form_data()

        assert "repositories" in result
        assert len(result["repositories"]) == 1
        assert result["repositories"][0].name == "test-repo"

    def test_get_form_data_error_handling(self, service, test_db: Session) -> None:
        """Test error handling in get_form_data."""
        with patch.object(test_db, "query", side_effect=Exception("Database error")):
            result = service.get_form_data()
            assert result == {"repositories": []}

    def test_prune_config_lifecycle(self, service, test_db: Session) -> None:
        """Test complete prune config lifecycle: create, update, enable/disable, delete."""
        # Create
        config_data = PruneConfigCreate(
            name="lifecycle-test",
            strategy=PruneStrategy.SIMPLE,
            keep_within_days=30,
            keep_secondly=0,
            keep_minutely=0,
            keep_hourly=0,
            keep_daily=0,
            keep_weekly=0,
            keep_monthly=0,
            keep_yearly=0,
        )
        success, created_config, error = service.create_prune_config(config_data)
        assert success is True
        config_id = created_config.id

        # Update
        config_update = PruneConfigUpdate(keep_within_days=60)
        success, updated_config, error = service.update_prune_config(
            config_id, config_update
        )
        assert success is True
        assert updated_config.keep_within_days == 60

        # Disable
        success, disabled_config, error = service.disable_prune_config(config_id)
        assert success is True
        assert disabled_config.enabled is False

        # Enable
        success, enabled_config, error = service.enable_prune_config(config_id)
        assert success is True
        assert enabled_config.enabled is True

        # Delete
        success, config_name, error = service.delete_prune_config(config_id)
        assert success is True
        assert config_name == "lifecycle-test"

        # Verify completely removed
        deleted_config = (
            test_db.query(PruneConfig).filter(PruneConfig.id == config_id).first()
        )
        assert deleted_config is None
