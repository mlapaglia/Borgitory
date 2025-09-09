"""
Tests for repository_check_configs API endpoints
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi import Request
from fastapi.testclient import TestClient
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.api.repository_check_configs import router
from app.models.database import RepositoryCheckConfig, Repository
from app.models.schemas import RepositoryCheckConfigCreate, RepositoryCheckConfigUpdate


@pytest.fixture
def mock_db():
    """Mock database session"""
    return MagicMock(spec=Session)


@pytest.fixture
def mock_request():
    """Mock FastAPI request"""
    request = MagicMock(spec=Request)
    request.headers = {}
    return request


@pytest.fixture
def mock_htmx_request():
    """Mock HTMX request"""
    request = MagicMock(spec=Request)
    request.headers = {"hx-request": "true"}
    return request


@pytest.fixture
def mock_config():
    """Mock repository check config"""
    config = MagicMock(spec=RepositoryCheckConfig)
    config.id = 1
    config.name = "test-config"
    config.description = "Test configuration"
    config.check_type = "full"
    config.verify_data = True
    config.repair_mode = False
    config.save_space = True
    config.max_duration = 3600
    config.archive_prefix = "test-"
    config.archive_glob = "*"
    config.first_n_archives = 1
    config.last_n_archives = 1
    config.enabled = True
    return config


@pytest.fixture
def sample_config_create():
    """Sample config creation data"""
    return RepositoryCheckConfigCreate(
        name="new-config",
        description="New configuration",
        check_type="full",
        verify_data=True,
        repair_mode=False,
        save_space=True,
        max_duration=None,  # max_duration only for repository_only checks
        archive_prefix="new-",
        archive_glob="*",
        first_n_archives=1,
        last_n_archives=None  # Cannot specify both first_n_archives and last_n_archives
    )


class TestRepositoryCheckConfigs:
    """Test the repository check configs API endpoints"""

    @pytest.mark.asyncio
    async def test_create_repository_check_config_success(self, mock_request, mock_db, sample_config_create):
        """Test successful creation of repository check config"""
        from app.api.repository_check_configs import create_repository_check_config
        
        # Mock no existing config with same name
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        result = await create_repository_check_config(mock_request, sample_config_create, mock_db)
        
        # Should add, commit, and refresh
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_repository_check_config_duplicate_name(self, mock_request, mock_db, sample_config_create):
        """Test creation with duplicate name"""
        from app.api.repository_check_configs import create_repository_check_config
        
        # Mock existing config with same name
        existing_config = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = existing_config
        
        with pytest.raises(Exception):  # Should raise HTTPException
            await create_repository_check_config(mock_request, sample_config_create, mock_db)

    @pytest.mark.asyncio
    async def test_create_repository_check_config_htmx_success(self, mock_htmx_request, mock_db, sample_config_create):
        """Test successful HTMX creation"""
        from app.api.repository_check_configs import create_repository_check_config
        
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        with patch('app.api.repository_check_configs.templates') as mock_templates:
            mock_response = MagicMock()
            mock_response.headers = {}
            mock_templates.TemplateResponse.return_value = mock_response
            
            result = await create_repository_check_config(mock_htmx_request, sample_config_create, mock_db)
            
            # Should return template response with HX-Trigger header
            assert "HX-Trigger" in mock_response.headers
            assert mock_response.headers["HX-Trigger"] == "checkConfigUpdate"

    @pytest.mark.asyncio
    async def test_create_repository_check_config_htmx_duplicate(self, mock_htmx_request, mock_db, sample_config_create):
        """Test HTMX creation with duplicate name"""
        from app.api.repository_check_configs import create_repository_check_config
        
        existing_config = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = existing_config
        
        with patch('app.api.repository_check_configs.templates') as mock_templates:
            mock_templates.TemplateResponse.return_value = MagicMock()
            
            result = await create_repository_check_config(mock_htmx_request, sample_config_create, mock_db)
            
            # Should return error template
            mock_templates.TemplateResponse.assert_called()

    @pytest.mark.asyncio
    async def test_create_repository_check_config_exception(self, mock_request, mock_db, sample_config_create):
        """Test creation with database exception"""
        from app.api.repository_check_configs import create_repository_check_config
        
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.commit.side_effect = Exception("Database error")
        
        with pytest.raises(Exception):
            await create_repository_check_config(mock_request, sample_config_create, mock_db)

    def test_get_repository_check_configs(self, mock_db, mock_config):
        """Test getting all repository check configs"""
        from app.api.repository_check_configs import get_repository_check_configs
        
        mock_db.query.return_value.order_by.return_value.all.return_value = [mock_config]
        
        result = get_repository_check_configs(mock_db)
        
        assert result == [mock_config]
        mock_db.query.assert_called_once_with(RepositoryCheckConfig)

    @pytest.mark.asyncio
    async def test_get_repository_check_form(self, mock_request, mock_db):
        """Test getting repository check form"""
        from app.api.repository_check_configs import get_repository_check_form
        
        mock_repository = MagicMock(spec=Repository)
        mock_config = MagicMock(spec=RepositoryCheckConfig)
        mock_config.enabled = True
        
        # Mock different queries for Repository and RepositoryCheckConfig
        def query_side_effect(model):
            if model == Repository:
                query_mock = MagicMock()
                query_mock.all.return_value = [mock_repository]
                return query_mock
            elif model == RepositoryCheckConfig:
                query_mock = MagicMock()
                query_mock.filter.return_value.all.return_value = [mock_config]
                return query_mock
            return MagicMock()
        
        mock_db.query.side_effect = query_side_effect
        
        with patch('app.api.repository_check_configs.templates') as mock_templates:
            result = await get_repository_check_form(mock_request, mock_db)
            
            mock_templates.TemplateResponse.assert_called_once()
            args, kwargs = mock_templates.TemplateResponse.call_args
            context = args[2]
            assert "repositories" in context
            assert "check_configs" in context

    def test_get_repository_check_configs_html_success(self, mock_request, mock_db, mock_config):
        """Test getting repository check configs as HTML"""
        from app.api.repository_check_configs import get_repository_check_configs_html
        
        mock_db.query.return_value.order_by.return_value.all.return_value = [mock_config]
        
        with patch('app.api.repository_check_configs.templates') as mock_templates:
            result = get_repository_check_configs_html(mock_request, mock_db)
            
            mock_templates.TemplateResponse.assert_called_once()
            args, kwargs = mock_templates.TemplateResponse.call_args
            assert args[1] == "partials/repository_check/config_list_content.html"
            assert "configs" in args[2]

    def test_get_repository_check_configs_html_exception(self, mock_request, mock_db):
        """Test getting repository check configs HTML with exception"""
        from app.api.repository_check_configs import get_repository_check_configs_html
        
        mock_db.query.side_effect = Exception("Database error")
        
        with patch('app.api.repository_check_configs.templates') as mock_templates:
            result = get_repository_check_configs_html(mock_request, mock_db)
            
            mock_templates.TemplateResponse.assert_called_once()
            args, kwargs = mock_templates.TemplateResponse.call_args
            assert args[1] == "partials/common/error_message.html"
            assert "error_message" in args[2]

    def test_toggle_custom_options_show(self, mock_request):
        """Test toggling custom options to show"""
        from app.api.repository_check_configs import toggle_custom_options
        
        with patch('app.api.repository_check_configs.templates') as mock_templates:
            result = toggle_custom_options(mock_request, check_config_id="")
            
            args, kwargs = mock_templates.TemplateResponse.call_args
            context = args[2]
            assert context["show_custom"] is True

    def test_toggle_custom_options_hide(self, mock_request):
        """Test toggling custom options to hide"""
        from app.api.repository_check_configs import toggle_custom_options
        
        with patch('app.api.repository_check_configs.templates') as mock_templates:
            result = toggle_custom_options(mock_request, check_config_id="123")
            
            args, kwargs = mock_templates.TemplateResponse.call_args
            context = args[2]
            assert context["show_custom"] is False

    def test_update_check_options_repository_only(self, mock_request):
        """Test updating check options for repository_only type"""
        from app.api.repository_check_configs import update_check_options
        
        with patch('app.api.repository_check_configs.templates') as mock_templates:
            result = update_check_options(
                mock_request,
                check_type="repository_only",
                max_duration="3600",
                repair_mode="false"
            )
            
            args, kwargs = mock_templates.TemplateResponse.call_args
            context = args[2]
            assert context["verify_data_disabled"] is True
            assert context["time_limit_display"] == "block"
            assert context["archive_filters_display"] == "none"

    def test_update_check_options_full_check(self, mock_request):
        """Test updating check options for full check type"""
        from app.api.repository_check_configs import update_check_options
        
        with patch('app.api.repository_check_configs.templates') as mock_templates:
            result = update_check_options(
                mock_request,
                check_type="full",
                max_duration="",
                repair_mode="true"
            )
            
            args, kwargs = mock_templates.TemplateResponse.call_args
            context = args[2]
            assert context["verify_data_disabled"] is False
            assert context["time_limit_display"] == "none"
            assert context["archive_filters_display"] == "block"
            assert context["repair_mode_checked"] is True

    def test_update_check_options_repair_conflict(self, mock_request):
        """Test repair mode conflict with time limits"""
        from app.api.repository_check_configs import update_check_options
        
        with patch('app.api.repository_check_configs.templates') as mock_templates:
            result = update_check_options(
                mock_request,
                check_type="full",
                max_duration="3600",  # Has time limit
                repair_mode="true"    # Wants repair mode
            )
            
            args, kwargs = mock_templates.TemplateResponse.call_args
            context = args[2]
            assert context["repair_mode_checked"] is False  # Should be disabled due to conflict
            assert context["repair_mode_disabled"] is True

    def test_get_repository_check_config_success(self, mock_db, mock_config):
        """Test getting specific repository check config"""
        from app.api.repository_check_configs import get_repository_check_config
        
        mock_db.query.return_value.filter.return_value.first.return_value = mock_config
        
        result = get_repository_check_config(1, mock_db)
        
        assert result == mock_config

    def test_get_repository_check_config_not_found(self, mock_db):
        """Test getting non-existent repository check config"""
        from app.api.repository_check_configs import get_repository_check_config
        
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        with pytest.raises(Exception):  # Should raise HTTPException
            get_repository_check_config(999, mock_db)

    def test_update_repository_check_config_success(self, mock_db, mock_config):
        """Test successful update of repository check config"""
        from app.api.repository_check_configs import update_repository_check_config
        
        mock_config.name = "old-config"
        # First call finds config to update, second call finds no existing config with new name
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_config,  # First call finds the config to update
            None          # Second call finds no existing config with same name
        ]
        
        update_data = RepositoryCheckConfigUpdate(name="updated-config")
        
        result = update_repository_check_config(1, update_data, mock_db)
        
        assert result == mock_config
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once_with(mock_config)

    def test_update_repository_check_config_not_found(self, mock_db):
        """Test updating non-existent repository check config"""
        from app.api.repository_check_configs import update_repository_check_config
        
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        update_data = RepositoryCheckConfigUpdate(name="updated-config")
        
        with pytest.raises(Exception):  # Should raise HTTPException
            update_repository_check_config(999, update_data, mock_db)

    def test_update_repository_check_config_name_conflict(self, mock_db, mock_config):
        """Test updating with conflicting name"""
        from app.api.repository_check_configs import update_repository_check_config
        
        # Mock finding the config to update
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_config,  # First call finds the config to update
            MagicMock()   # Second call finds existing config with same name
        ]
        
        update_data = RepositoryCheckConfigUpdate(name="conflicting-name")
        
        with pytest.raises(Exception):  # Should raise HTTPException
            update_repository_check_config(1, update_data, mock_db)

    def test_update_repository_check_config_same_name(self, mock_db, mock_config):
        """Test updating with same name (should be allowed)"""
        from app.api.repository_check_configs import update_repository_check_config
        
        mock_config.name = "existing-name"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_config
        
        update_data = RepositoryCheckConfigUpdate(name="existing-name")  # Same name
        
        result = update_repository_check_config(1, update_data, mock_db)
        
        assert result == mock_config
        mock_db.commit.assert_called_once()

    def test_delete_repository_check_config_success(self, mock_request, mock_db, mock_config):
        """Test successful deletion of repository check config"""
        from app.api.repository_check_configs import delete_repository_check_config
        
        mock_db.query.return_value.filter.return_value.first.return_value = mock_config
        
        result = delete_repository_check_config(1, mock_request, mock_db)
        
        mock_db.delete.assert_called_once_with(mock_config)
        mock_db.commit.assert_called_once()
        assert result == {"message": "Check policy deleted successfully"}

    def test_delete_repository_check_config_htmx(self, mock_htmx_request, mock_db, mock_config):
        """Test HTMX deletion of repository check config"""
        from app.api.repository_check_configs import delete_repository_check_config
        
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_config,  # First call finds config to delete
            [mock_config]  # Second call gets updated list
        ]
        mock_db.query.return_value.order_by.return_value.all.return_value = [mock_config]
        
        with patch('app.api.repository_check_configs.templates') as mock_templates:
            result = delete_repository_check_config(1, mock_htmx_request, mock_db)
            
            mock_db.delete.assert_called_once_with(mock_config)
            mock_templates.TemplateResponse.assert_called_once()

    def test_delete_repository_check_config_not_found(self, mock_request, mock_db):
        """Test deleting non-existent repository check config"""
        from app.api.repository_check_configs import delete_repository_check_config
        
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        with pytest.raises(Exception):  # Should raise HTTPException
            delete_repository_check_config(999, mock_request, mock_db)

    def test_update_check_options_various_parameters(self, mock_request):
        """Test update_check_options with various parameter combinations"""
        from app.api.repository_check_configs import update_check_options
        
        with patch('app.api.repository_check_configs.templates') as mock_templates:
            # Test with empty repair_mode
            result = update_check_options(
                mock_request,
                check_type="full",
                max_duration="",
                repair_mode=""
            )
            
            args, kwargs = mock_templates.TemplateResponse.call_args
            context = args[2]
            # Empty string evaluates to falsy in "repair_mode and ..." expression, results in ""
            assert context["repair_mode_checked"] == ""
            assert context["repair_mode_disabled"] is False

    def test_update_check_options_repair_mode_variations(self, mock_request):
        """Test repair mode with different boolean string representations"""
        from app.api.repository_check_configs import update_check_options
        
        test_cases = [
            ("true", True),
            ("on", True),
            ("1", True),
            ("false", False),   # "false" is truthy, but not in the list, so expression returns False
            ("off", False),     # Similar to "false"
            ("0", False),       # Similar to "false"
            ("", "")            # Empty string evaluates to falsy, so expression returns ""
        ]
        
        with patch('app.api.repository_check_configs.templates') as mock_templates:
            for repair_mode_value, expected_checked in test_cases:
                update_check_options(
                    mock_request,
                    check_type="full",
                    max_duration="",
                    repair_mode=repair_mode_value
                )
                
                args, kwargs = mock_templates.TemplateResponse.call_args
                context = args[2]
                assert context["repair_mode_checked"] == expected_checked