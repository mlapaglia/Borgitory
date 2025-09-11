"""
Tests for PushoverService - Service to send notifications via Pushover
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiohttp import ClientResponse, ClientSession
from app.services.pushover_service import PushoverService


@pytest.fixture
def pushover_service():
    return PushoverService()


class TestPushoverService:
    """Test the PushoverService class"""

    @pytest.mark.asyncio
    @patch('aiohttp.ClientSession')
    async def test_send_notification_success(self, mock_session_class, pushover_service):
        """Test successful notification sending"""
        # Mock response
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"status": 1})

        # Mock session and its context managers
        mock_session_instance = MagicMock()
        mock_session_class.return_value = mock_session_instance
        mock_session_instance.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session_instance.__aexit__ = AsyncMock(return_value=None)
        mock_session_instance.post = MagicMock()
        mock_session_instance.post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session_instance.post.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await pushover_service.send_notification(
            user_key="test_user",
            app_token="test_token",
            title="Test Title",
            message="Test Message"
        )

        assert result is True
        mock_session_instance.post.assert_called_once_with(
            pushover_service.PUSHOVER_API_URL,
            data={
                "token": "test_token",
                "user": "test_user",
                "title": "Test Title",
                "message": "Test Message",
                "priority": 0,
                "sound": "default"
            }
        )

    @pytest.mark.asyncio
    @patch('aiohttp.ClientSession')
    async def test_send_notification_custom_priority_sound(self, mock_session_class, pushover_service):
        """Test notification with custom priority and sound"""
        # Mock response
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"status": 1})

        # Mock session and its context managers
        mock_session_instance = MagicMock()
        mock_session_class.return_value = mock_session_instance
        mock_session_instance.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session_instance.__aexit__ = AsyncMock(return_value=None)
        mock_session_instance.post = MagicMock()
        mock_session_instance.post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session_instance.post.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await pushover_service.send_notification(
            user_key="test_user",
            app_token="test_token",
            title="Urgent Alert",
            message="Critical message",
            priority=2,
            sound="siren"
        )

        assert result is True
        mock_session_instance.post.assert_called_once_with(
            pushover_service.PUSHOVER_API_URL,
            data={
                "token": "test_token",
                "user": "test_user",
                "title": "Urgent Alert",
                "message": "Critical message",
                "priority": 2,
                "sound": "siren"
            }
        )

    @pytest.mark.asyncio
    async def test_send_notification_api_error_response(self, pushover_service):
        """Test handling of API error response"""
        mock_response = MagicMock(spec=ClientResponse)
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "status": 0,
            "errors": ["invalid user key"]
        })

        mock_session = MagicMock(spec=ClientSession)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.post.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch('aiohttp.ClientSession', return_value=mock_session):
            result = await pushover_service.send_notification(
                user_key="invalid_user",
                app_token="test_token",
                title="Test Title",
                message="Test Message"
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_send_notification_http_error(self, pushover_service):
        """Test handling of HTTP error status codes"""
        mock_response = MagicMock(spec=ClientResponse)
        mock_response.status = 400
        mock_response.text = AsyncMock(return_value="Bad Request")

        mock_session = MagicMock(spec=ClientSession)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.post.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch('aiohttp.ClientSession', return_value=mock_session):
            result = await pushover_service.send_notification(
                user_key="test_user",
                app_token="invalid_token",
                title="Test Title",
                message="Test Message"
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_send_notification_exception_handling(self, pushover_service):
        """Test exception handling in send_notification"""
        with patch('aiohttp.ClientSession', side_effect=Exception("Connection error")):
            result = await pushover_service.send_notification(
                user_key="test_user",
                app_token="test_token",
                title="Test Title",
                message="Test Message"
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_send_backup_success_notification_basic(self, pushover_service):
        """Test backup success notification with basic parameters"""
        with patch.object(pushover_service, 'send_notification', return_value=True) as mock_send:
            result = await pushover_service.send_backup_success_notification(
                user_key="test_user",
                app_token="test_token",
                repository_name="test-repo",
                job_type="backup_create"
            )

            assert result is True
            mock_send.assert_called_once_with(
                user_key="test_user",
                app_token="test_token",
                title="✅ Backup Complete - test-repo",
                message="Backup Create completed successfully",
                priority=0,
                sound="default"
            )

    @pytest.mark.asyncio
    async def test_send_backup_success_notification_with_details(self, pushover_service):
        """Test backup success notification with duration and archive count"""
        with patch.object(pushover_service, 'send_notification', return_value=True) as mock_send:
            result = await pushover_service.send_backup_success_notification(
                user_key="test_user",
                app_token="test_token",
                repository_name="test-repo",
                job_type="backup_create",
                duration="2m 30s",
                archive_count=15
            )

            assert result is True
            expected_message = "Backup Create completed successfully\nDuration: 2m 30s\nArchive count: 15"
            mock_send.assert_called_once_with(
                user_key="test_user",
                app_token="test_token",
                title="✅ Backup Complete - test-repo",
                message=expected_message,
                priority=0,
                sound="default"
            )

    @pytest.mark.asyncio
    async def test_send_backup_failure_notification_basic(self, pushover_service):
        """Test backup failure notification with basic parameters"""
        with patch.object(pushover_service, 'send_notification', return_value=True) as mock_send:
            result = await pushover_service.send_backup_failure_notification(
                user_key="test_user",
                app_token="test_token",
                repository_name="test-repo",
                job_type="backup_create"
            )

            assert result is True
            mock_send.assert_called_once_with(
                user_key="test_user",
                app_token="test_token",
                title="❌ Backup Failed - test-repo",
                message="Backup Create failed",
                priority=1,
                sound="siren"
            )

    @pytest.mark.asyncio
    async def test_send_backup_failure_notification_with_error(self, pushover_service):
        """Test backup failure notification with error message"""
        with patch.object(pushover_service, 'send_notification', return_value=True) as mock_send:
            result = await pushover_service.send_backup_failure_notification(
                user_key="test_user",
                app_token="test_token",
                repository_name="test-repo",
                job_type="backup_create",
                error_message="Repository not accessible"
            )

            assert result is True
            expected_message = "Backup Create failed\nError: Repository not accessible"
            mock_send.assert_called_once_with(
                user_key="test_user",
                app_token="test_token",
                title="❌ Backup Failed - test-repo",
                message=expected_message,
                priority=1,
                sound="siren"
            )

    @pytest.mark.asyncio
    async def test_send_backup_failure_notification_truncate_long_error(self, pushover_service):
        """Test that long error messages are truncated"""
        long_error = "A" * 250  # 250 characters, should be truncated
        
        with patch.object(pushover_service, 'send_notification', return_value=True) as mock_send:
            result = await pushover_service.send_backup_failure_notification(
                user_key="test_user",
                app_token="test_token",
                repository_name="test-repo",
                job_type="backup_create",
                error_message=long_error
            )

            assert result is True
            expected_message = f"Backup Create failed\nError: {'A' * 200}..."
            mock_send.assert_called_once_with(
                user_key="test_user",
                app_token="test_token",
                title="❌ Backup Failed - test-repo",
                message=expected_message,
                priority=1,
                sound="siren"
            )

    @pytest.mark.asyncio
    async def test_test_pushover_connection_success(self, pushover_service):
        """Test successful Pushover connection test"""
        with patch.object(pushover_service, 'send_notification', return_value=True) as mock_send:
            result = await pushover_service.test_pushover_connection(
                user_key="test_user",
                app_token="test_token"
            )

            assert result["status"] == "success"
            assert "Test notification sent successfully!" in result["message"]
            mock_send.assert_called_once_with(
                user_key="test_user",
                app_token="test_token",
                title="Borgitory Test",
                message="This is a test notification from Borgitory backup system.",
                priority=0,
                sound="default"
            )

    @pytest.mark.asyncio
    async def test_test_pushover_connection_failure(self, pushover_service):
        """Test failed Pushover connection test"""
        with patch.object(pushover_service, 'send_notification', return_value=False):
            result = await pushover_service.test_pushover_connection(
                user_key="invalid_user",
                app_token="invalid_token"
            )

            assert result["status"] == "error"
            assert "Failed to send test notification" in result["message"]

    @pytest.mark.asyncio
    async def test_test_pushover_connection_exception(self, pushover_service):
        """Test connection test with exception"""
        with patch.object(pushover_service, 'send_notification', 
                         side_effect=Exception("Network error")):
            result = await pushover_service.test_pushover_connection(
                user_key="test_user",
                app_token="test_token"
            )

            assert result["status"] == "error"
            assert "Connection test failed: Network error" in result["message"]

    @pytest.mark.asyncio
    async def test_send_notification_api_error_without_errors_field(self, pushover_service):
        """Test handling API error response without errors field"""
        mock_response = MagicMock(spec=ClientResponse)
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"status": 0})

        mock_session = MagicMock(spec=ClientSession)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.post.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch('aiohttp.ClientSession', return_value=mock_session):
            result = await pushover_service.send_notification(
                user_key="test_user",
                app_token="test_token",
                title="Test Title",
                message="Test Message"
            )

            assert result is False

    def test_pushover_api_url_constant(self, pushover_service):
        """Test that the Pushover API URL is correctly set"""
        assert pushover_service.PUSHOVER_API_URL == "https://api.pushover.net/1/messages.json"

    @pytest.mark.asyncio
    async def test_job_type_formatting_in_success_notification(self, pushover_service):
        """Test that job types are properly formatted in success notifications"""
        with patch.object(pushover_service, 'send_notification', return_value=True) as mock_send:
            await pushover_service.send_backup_success_notification(
                user_key="test_user",
                app_token="test_token",
                repository_name="test-repo",
                job_type="backup_prune_compact"
            )

            # Job type should be formatted with spaces and title case
            args, kwargs = mock_send.call_args
            assert "Backup Prune Compact completed successfully" in kwargs["message"]

    @pytest.mark.asyncio
    async def test_job_type_formatting_in_failure_notification(self, pushover_service):
        """Test that job types are properly formatted in failure notifications"""
        with patch.object(pushover_service, 'send_notification', return_value=True) as mock_send:
            await pushover_service.send_backup_failure_notification(
                user_key="test_user",
                app_token="test_token",
                repository_name="test-repo",
                job_type="backup_prune_compact"
            )

            # Job type should be formatted with spaces and title case
            args, kwargs = mock_send.call_args
            assert "Backup Prune Compact failed" in kwargs["message"]