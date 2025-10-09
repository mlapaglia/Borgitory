"""
Tests for PruneService - Business logic tests
"""

import pytest
from unittest.mock import patch
from sqlalchemy import select

from sqlalchemy.ext.asyncio import AsyncSession

from borgitory.services.prune_service import PruneService
from borgitory.models.database import PruneConfig, Repository
from borgitory.models.schemas import PruneConfigCreate, PruneConfigUpdate, PruneStrategy


@pytest.fixture
def service(test_db: AsyncSession) -> PruneService:
    """PruneService instance with real database session."""
    return PruneService()


@pytest.fixture
async def sample_repository(test_db: AsyncSession) -> Repository:
    """Create a sample repository for testing."""
    repository = Repository()
    repository.name = "test-repo"
    repository.path = "/tmp/test-repo"
    repository.encrypted_passphrase = "test-encrypted-passphrase"

    test_db.add(repository)
    await test_db.commit()
    await test_db.refresh(repository)
    return repository


class TestPruneService:
    """Test class for PruneService business logic."""

    async def test_get_prune_configs_empty(
        self, service: PruneService, test_db: AsyncSession
    ) -> None:
        """Test getting prune configs when none exist."""
        result = await service.get_prune_configs(db=test_db)
        assert result == []

    async def test_get_prune_configs_with_data(
        self, service: PruneService, test_db: AsyncSession
    ) -> None:
        """Test getting prune configs with data."""
        config1 = PruneConfig()
        config1.name = "config-1"
        config1.strategy = "simple"
        config1.keep_within_days = 30
        config1.keep_secondly = 0
        config1.keep_minutely = 0
        config1.keep_hourly = 0
        config1.keep_daily = 0
        config1.keep_weekly = 0
        config1.keep_monthly = 0
        config1.keep_yearly = 0
        config1.enabled = True

        config2 = PruneConfig()
        config2.name = "config-2"
        config2.strategy = "advanced"
        config2.keep_secondly = 0
        config2.keep_minutely = 0
        config2.keep_hourly = 0
        config2.keep_daily = 7
        config2.keep_weekly = 4
        config2.keep_monthly = 12
        config2.keep_yearly = 2
        config2.enabled = False
        test_db.add_all([config1, config2])
        await test_db.commit()

        result = await service.get_prune_configs(db=test_db)
        assert len(result) == 2
        names = [c.name for c in result]
        assert "config-1" in names
        assert "config-2" in names

    async def test_get_prune_configs_with_pagination(
        self, service: PruneService, test_db: AsyncSession
    ) -> None:
        """Test getting prune configs with pagination."""
        for i in range(5):
            config = PruneConfig()
            config.name = f"config-{i}"
            config.strategy = "simple"
            config.keep_within_days = 30
            config.keep_secondly = 0
            config.keep_minutely = 0
            config.keep_hourly = 0
            config.keep_daily = 0
            config.keep_weekly = 0
            config.keep_monthly = 0
            config.keep_yearly = 0
            config.enabled = True
            test_db.add(config)
        await test_db.commit()

        result = await service.get_prune_configs(db=test_db, skip=2, limit=2)
        assert len(result) == 2

    async def test_get_prune_config_by_id_success(
        self, service: PruneService, test_db: AsyncSession
    ) -> None:
        """Test getting prune config by ID successfully."""
        config = PruneConfig()
        config.name = "test-config"
        config.strategy = "simple"
        config.keep_within_days = 30
        config.keep_secondly = 0
        config.keep_minutely = 0
        config.keep_hourly = 0
        config.keep_daily = 0
        config.keep_weekly = 0
        config.keep_monthly = 0
        config.keep_yearly = 0
        config.enabled = True
        test_db.add(config)
        await test_db.commit()
        await test_db.refresh(config)

        result = await service.get_prune_config_by_id(db=test_db, config_id=config.id)
        assert result is not None
        assert result.name == "test-config"
        assert result.id == config.id

    async def test_get_prune_config_by_id_not_found(
        self, service: PruneService, test_db: AsyncSession
    ) -> None:
        """Test getting non-existent prune config raises exception."""
        with pytest.raises(
            Exception, match="Prune configuration with id 999 not found"
        ):
            await service.get_prune_config_by_id(db=test_db, config_id=999)

    async def test_create_prune_config_success(
        self, service: PruneService, test_db: AsyncSession
    ) -> None:
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

        result = await service.create_prune_config(db=test_db, prune_config=config_data)
        success, config, error = result.success, result.config, result.error_message

        assert success is True
        assert error is None
        assert config is not None
        assert config.name == "new-config"
        assert config.strategy == PruneStrategy.SIMPLE
        assert config.keep_within_days == 30
        assert config.enabled is True

        # Verify saved to database
        result = await test_db.execute(
            select(PruneConfig).where(PruneConfig.name == "new-config")
        )
        saved_config = result.scalar_one_or_none()
        assert saved_config is not None
        assert saved_config.strategy == PruneStrategy.SIMPLE

    async def test_create_prune_config_duplicate_name(
        self, service: PruneService, test_db: AsyncSession
    ) -> None:
        """Test prune config creation with duplicate name."""
        existing_config = PruneConfig()
        existing_config.name = "duplicate-name"
        existing_config.strategy = PruneStrategy.SIMPLE
        existing_config.keep_within_days = 30
        existing_config.keep_secondly = 0
        existing_config.keep_minutely = 0
        existing_config.keep_hourly = 0
        existing_config.keep_daily = 0
        existing_config.keep_weekly = 0
        existing_config.keep_monthly = 0
        existing_config.keep_yearly = 0
        test_db.add(existing_config)
        await test_db.commit()

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

        result = await service.create_prune_config(db=test_db, prune_config=config_data)
        success, config, error = result.success, result.config, result.error_message

        assert success is False
        assert config is None
        assert error is not None
        assert "A prune policy with this name already exists" in error

    async def test_create_prune_config_database_error(
        self, service: PruneService, test_db: AsyncSession
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
            result = await service.create_prune_config(
                db=test_db, prune_config=config_data
            )
            success, config, error = result.success, result.config, result.error_message

            assert success is False
            assert config is None
            assert error is not None
            assert "Failed to create prune configuration" in error

    async def test_update_prune_config_success(
        self, service: PruneService, test_db: AsyncSession
    ) -> None:
        """Test successful prune config update."""
        config = PruneConfig()
        config.name = "original-config"
        config.strategy = PruneStrategy.SIMPLE
        config.keep_within_days = 30
        config.keep_secondly = 0
        config.keep_minutely = 0
        config.keep_hourly = 0
        config.keep_daily = 0
        config.keep_weekly = 0
        config.keep_monthly = 0
        config.keep_yearly = 0
        config.enabled = True
        test_db.add(config)
        await test_db.commit()
        await test_db.refresh(config)

        config_update = PruneConfigUpdate(name="updated-config", keep_within_days=60)

        result = await service.update_prune_config(
            db=test_db, config_id=config.id, prune_config_update=config_update
        )

        success, updated_config, error = (
            result.success,
            result.config,
            result.error_message,
        )

        assert success is True
        assert error is None
        assert updated_config is not None
        assert updated_config.name == "updated-config"
        assert updated_config.keep_within_days == 60

    async def test_update_prune_config_not_found(
        self, service: PruneService, test_db: AsyncSession
    ) -> None:
        """Test updating non-existent prune config."""
        config_update = PruneConfigUpdate(name="new-name")

        result = await service.update_prune_config(
            db=test_db, config_id=999, prune_config_update=config_update
        )
        success, config, error = result.success, result.config, result.error_message

        assert success is False
        assert config is None
        assert error is not None
        assert "Prune configuration not found" in error

    async def test_update_prune_config_duplicate_name(
        self, service: PruneService, test_db: AsyncSession
    ) -> None:
        """Test updating prune config with duplicate name."""
        config1 = PruneConfig()
        config1.name = "config-1"
        config1.strategy = PruneStrategy.SIMPLE
        config1.keep_within_days = 30
        config1.keep_secondly = 0
        config1.keep_minutely = 0
        config1.keep_hourly = 0
        config1.keep_daily = 0
        config1.keep_weekly = 0
        config1.keep_monthly = 0
        config1.keep_yearly = 0
        config1.enabled = True

        config2 = PruneConfig()
        config2.name = "config-2"
        config2.strategy = PruneStrategy.ADVANCED
        config2.keep_daily = 7
        config2.keep_secondly = 0
        config2.keep_minutely = 0
        config2.keep_hourly = 0
        config2.keep_weekly = 0
        config2.keep_monthly = 0
        config2.keep_yearly = 0
        config2.enabled = True
        test_db.add_all([config1, config2])
        await test_db.commit()

        config_update = PruneConfigUpdate(name="config-2")

        result = await service.update_prune_config(
            db=test_db, config_id=config1.id, prune_config_update=config_update
        )
        success, config, error = result.success, result.config, result.error_message

        assert success is False
        assert config is None
        assert error is not None
        assert "A prune policy with this name already exists" in error

    async def test_enable_prune_config_success(
        self, service: PruneService, test_db: AsyncSession
    ) -> None:
        """Test successfully enabling prune config."""
        config = PruneConfig()
        config.name = "test-config"
        config.strategy = PruneStrategy.SIMPLE
        config.keep_within_days = 30
        config.keep_secondly = 0
        config.keep_minutely = 0
        config.keep_hourly = 0
        config.keep_daily = 0
        config.keep_weekly = 0
        config.keep_monthly = 0
        config.keep_yearly = 0
        config.enabled = False
        test_db.add(config)
        await test_db.commit()
        await test_db.refresh(config)

        result = await service.enable_prune_config(
            db=test_db, prune_config_id=config.id
        )
        success, updated_config, error = (
            result.success,
            result.config,
            result.error_message,
        )

        assert success is True
        assert error is None
        assert updated_config is not None
        assert updated_config.enabled is True

    async def test_enable_prune_config_not_found(
        self, service: PruneService, test_db: AsyncSession
    ) -> None:
        """Test enabling non-existent prune config."""
        result = await service.enable_prune_config(db=test_db, prune_config_id=999)

        assert result.success is False
        assert result.config is None
        assert result.error_message is not None
        assert "Prune configuration not found" in result.error_message

    async def test_disable_prune_config_success(
        self, service: PruneService, test_db: AsyncSession
    ) -> None:
        """Test successfully disabling prune config."""
        config = PruneConfig()
        config.name = "test-config"
        config.strategy = PruneStrategy.SIMPLE
        config.keep_within_days = 30
        config.keep_secondly = 0
        config.keep_minutely = 0
        config.keep_hourly = 0
        config.keep_daily = 0
        config.keep_weekly = 0
        config.keep_monthly = 0
        config.keep_yearly = 0
        config.enabled = True
        test_db.add(config)
        await test_db.commit()
        await test_db.refresh(config)

        result = await service.disable_prune_config(
            db=test_db, prune_config_id=config.id
        )
        success, updated_config, error = (
            result.success,
            result.config,
            result.error_message,
        )

        assert success is True
        assert error is None
        assert updated_config is not None
        assert updated_config.enabled is False

    async def test_disable_prune_config_not_found(
        self, service: PruneService, test_db: AsyncSession
    ) -> None:
        """Test disabling non-existent prune config."""
        result = await service.disable_prune_config(db=test_db, prune_config_id=999)
        success, config, error = result.success, result.config, result.error_message

        assert success is False
        assert config is None
        assert error is not None
        assert "Prune configuration not found" in error

    async def test_delete_prune_config_success(
        self, service: PruneService, test_db: AsyncSession
    ) -> None:
        """Test successful prune config deletion."""
        config = PruneConfig()
        config.name = "test-config"
        config.strategy = PruneStrategy.SIMPLE
        config.keep_within_days = 30
        config.keep_secondly = 0
        config.keep_minutely = 0
        config.keep_hourly = 0
        config.keep_daily = 0
        config.keep_weekly = 0
        config.keep_monthly = 0
        config.keep_yearly = 0
        config.enabled = True
        test_db.add(config)
        await test_db.commit()
        await test_db.refresh(config)
        config_id = config.id

        result = await service.delete_prune_config(
            db=test_db, prune_config_id=config_id
        )
        success, config_name, error = (
            result.success,
            result.config_name,
            result.error_message,
        )

        assert success is True
        assert config_name == "test-config"
        assert error is None

        # Verify removed from database
        result = await test_db.execute(
            select(PruneConfig).where(PruneConfig.id == config_id)
        )
        deleted_config = result.scalar_one_or_none()
        assert deleted_config is None

    async def test_delete_prune_config_not_found(
        self, service: PruneService, test_db: AsyncSession
    ) -> None:
        """Test deleting non-existent prune config."""
        result = await service.delete_prune_config(db=test_db, prune_config_id=999)
        success, config_name, error = (
            result.success,
            result.config_name,
            result.error_message,
        )

        assert success is False
        assert config_name is None
        assert error is not None
        assert "Prune configuration not found" in error

    async def test_get_configs_with_descriptions_simple_strategy(
        self, service: PruneService, test_db: AsyncSession
    ) -> None:
        """Test getting configs with descriptions for simple strategy."""
        config = PruneConfig()
        config.name = "simple-config"
        config.strategy = PruneStrategy.SIMPLE
        config.keep_within_days = 30
        config.keep_secondly = 0
        config.keep_minutely = 0
        config.keep_hourly = 0
        config.keep_daily = 0
        config.keep_weekly = 0
        config.keep_monthly = 0
        config.keep_yearly = 0
        config.enabled = True
        test_db.add(config)
        await test_db.commit()

        result = await service.get_configs_with_descriptions(db=test_db)

        assert len(result) == 1
        assert result[0]["description"] == "Keep archives within 30 days"

    async def test_get_configs_with_descriptions_advanced_strategy(
        self, service: PruneService, test_db: AsyncSession
    ) -> None:
        """Test getting configs with descriptions for advanced strategy."""
        config = PruneConfig()
        config.name = "advanced-config"
        config.strategy = PruneStrategy.ADVANCED
        config.keep_daily = 7
        config.keep_weekly = 4
        config.keep_monthly = 12
        config.keep_yearly = 2
        config.enabled = True
        test_db.add(config)
        await test_db.commit()

        result = await service.get_configs_with_descriptions(db=test_db)

        assert len(result) == 1
        expected_desc = "7 daily, 4 weekly, 12 monthly, 2 yearly"
        assert result[0]["description"] == expected_desc

    async def test_get_configs_with_descriptions_partial_advanced(
        self, service: PruneService, test_db: AsyncSession
    ) -> None:
        """Test getting configs with descriptions for partial advanced strategy."""
        config = PruneConfig()
        config.name = "partial-config"
        config.strategy = PruneStrategy.ADVANCED
        config.keep_daily = 7
        config.keep_monthly = 12
        config.enabled = True
        test_db.add(config)
        await test_db.commit()

        result = await service.get_configs_with_descriptions(db=test_db)

        assert len(result) == 1
        expected_desc = "7 daily, 12 monthly"
        assert result[0]["description"] == expected_desc

    async def test_get_configs_with_descriptions_no_rules(
        self, service: PruneService, test_db: AsyncSession
    ) -> None:
        """Test getting configs with descriptions for no retention rules."""
        config = PruneConfig()
        config.name = "empty-config"
        config.strategy = PruneStrategy.ADVANCED
        config.keep_secondly = 0
        config.keep_minutely = 0
        config.keep_hourly = 0
        config.keep_daily = 0
        config.keep_weekly = 0
        config.keep_monthly = 0
        config.keep_yearly = 0
        config.enabled = True
        test_db.add(config)
        await test_db.commit()

        result = await service.get_configs_with_descriptions(db=test_db)

        assert len(result) == 1
        assert result[0]["description"] == "No retention rules"

    async def test_get_configs_with_descriptions_error_handling(
        self, service: PruneService, test_db: AsyncSession
    ) -> None:
        """Test error handling in get_configs_with_descriptions."""
        with patch.object(
            service, "get_prune_configs", side_effect=Exception("Database error")
        ):
            result = await service.get_configs_with_descriptions(db=test_db)
            assert result == []

    async def test_get_form_data_success(
        self,
        service: PruneService,
        test_db: AsyncSession,
        sample_repository: Repository,
    ) -> None:
        """Test successful form data retrieval."""
        result = await service.get_form_data(db=test_db)

        assert "repositories" in result
        assert len(result["repositories"]) == 1
        assert result["repositories"][0].name == "test-repo"

    async def test_get_form_data_error_handling(
        self, service: PruneService, test_db: AsyncSession
    ) -> None:
        """Test error handling in get_form_data."""
        with patch.object(test_db, "execute", side_effect=Exception("Database error")):
            result = await service.get_form_data(db=test_db)
            assert result == {"repositories": []}

    async def test_prune_config_lifecycle(
        self, service: PruneService, test_db: AsyncSession
    ) -> None:
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
        result = await service.create_prune_config(db=test_db, prune_config=config_data)
        success, created_config, _error = (
            result.success,
            result.config,
            result.error_message,
        )
        assert success is True
        assert created_config is not None
        config_id = created_config.id

        # Update
        config_update = PruneConfigUpdate(keep_within_days=60)
        result = await service.update_prune_config(
            db=test_db, config_id=config_id, prune_config_update=config_update
        )
        success, updated_config, _error = (
            result.success,
            result.config,
            result.error_message,
        )
        assert success is True
        assert updated_config is not None
        assert updated_config.keep_within_days == 60

        # Disable
        result = await service.disable_prune_config(
            db=test_db, prune_config_id=config_id
        )
        success, disabled_config, _error = (
            result.success,
            result.config,
            result.error_message,
        )
        assert success is True
        assert disabled_config is not None
        assert disabled_config.enabled is False

        # Enable
        result = await service.enable_prune_config(
            db=test_db, prune_config_id=config_id
        )
        assert result.success is True
        assert result.config is not None
        assert result.config.enabled is True

        # Delete
        result2 = await service.delete_prune_config(
            db=test_db, prune_config_id=config_id
        )
        assert result2 is not None
        assert result2.success is True
        assert result2.config_name is not None
        assert result2.config_name == "lifecycle-test"

        # Verify completely removed
        result = await test_db.execute(
            select(PruneConfig).where(PruneConfig.id == config_id)
        )
        deleted_config = result.scalar_one_or_none()
        assert deleted_config is None
