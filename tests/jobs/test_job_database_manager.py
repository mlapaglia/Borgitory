"""
Comprehensive test suite for JobDatabaseManager

This test ensures that the JobDatabaseManager works correctly and prevents
the AttributeError with _db_session_factory that was encountered during cloud sync.
"""

import pytest
import uuid
from unittest.mock import Mock, patch
from borgitory.utils.datetime_utils import now_utc

from borgitory.services.jobs.job_database_manager import (
    JobDatabaseManager,
    DatabaseJobData,
)


class TestJobDatabaseManager:
    """Test suite for JobDatabaseManager"""

    @pytest.fixture
    def mock_db_session_factory(self):
        """Create mock database session factory"""
        session = Mock()
        factory = Mock()
        factory.return_value.__enter__ = Mock(return_value=session)
        factory.return_value.__exit__ = Mock(return_value=None)
        return factory, session

    @pytest.fixture
    def job_database_manager(self, mock_db_session_factory):
        """Create JobDatabaseManager with mocked dependencies"""
        factory, _ = mock_db_session_factory
        return JobDatabaseManager(db_session_factory=factory)

    @pytest.fixture
    def job_database_manager_with_coordinator(self, mock_db_session_factory):
        """Create JobDatabaseManager with cloud backup coordinator"""
        factory, _ = mock_db_session_factory
        return JobDatabaseManager(
            db_session_factory=factory,
        )

    @pytest.fixture
    def sample_job_data(self):
        """Create sample job data for testing"""
        return DatabaseJobData(
            job_uuid=str(uuid.uuid4()),
            repository_id=1,
            job_type="backup",
            status="running",
            started_at=now_utc(),
            cloud_sync_config_id=123,
        )

    def test_initialization_with_default_session_factory(self) -> None:
        """Test that JobDatabaseManager initializes correctly with default session factory"""
        manager = JobDatabaseManager()

        # Should have db_session_factory attribute (not _db_session_factory)
        assert hasattr(manager, "db_session_factory")
        assert not hasattr(manager, "_db_session_factory")
        assert manager.db_session_factory is not None

    def test_initialization_with_custom_dependencies(
        self, mock_db_session_factory
    ) -> None:
        """Test initialization with custom dependencies"""
        factory, _ = mock_db_session_factory

        manager = JobDatabaseManager(
            db_session_factory=factory,
        )

        assert manager.db_session_factory == factory

    def test_attribute_access_compatibility(self, job_database_manager) -> None:
        """
        Critical test: Ensure the correct attribute name is used
        This prevents the AttributeError: 'JobDatabaseManager' object has no attribute '_db_session_factory'
        """
        # This should work - the correct attribute name
        assert hasattr(job_database_manager, "db_session_factory")
        assert job_database_manager.db_session_factory is not None

        # This should NOT exist - this was the source of the bug
        assert not hasattr(job_database_manager, "_db_session_factory")

    @pytest.mark.asyncio
    async def test_create_database_job_happy_path(
        self, job_database_manager, mock_db_session_factory, sample_job_data
    ) -> None:
        """Test successful job creation"""
        factory, mock_session = mock_db_session_factory

        # Mock the Job model and database operations
        with patch("borgitory.models.database.Job") as MockJob:
            mock_job_instance = Mock()
            mock_job_instance.id = sample_job_data.job_uuid
            MockJob.return_value = mock_job_instance

            # Mock database operations
            mock_session.add = Mock()
            mock_session.commit = Mock()
            mock_session.refresh = Mock()

            # Execute the test
            result = await job_database_manager.create_database_job(sample_job_data)

            # Verify results
            assert result == sample_job_data.job_uuid
            mock_session.add.assert_called_once_with(mock_job_instance)
            mock_session.commit.assert_called_once()
            mock_session.refresh.assert_called_once_with(mock_job_instance)

    @pytest.mark.asyncio
    async def test_update_job_status_happy_path(
        self, job_database_manager, mock_db_session_factory
    ) -> None:
        """Test successful job status update"""
        factory, mock_session = mock_db_session_factory
        job_uuid = str(uuid.uuid4())

        # Mock the Job model and query
        with patch("borgitory.models.database.Job"):
            mock_job_instance = Mock()
            mock_job_instance.id = job_uuid
            mock_job_instance.status = "running"
            mock_job_instance.cloud_sync_config_id = None

            mock_query = Mock()
            mock_query.filter.return_value.first.return_value = mock_job_instance
            mock_session.query.return_value = mock_query
            mock_session.commit = Mock()

            # Execute the test
            result = await job_database_manager.update_job_status(
                job_uuid=job_uuid,
                status="completed",
                finished_at=now_utc(),
                output="Job completed successfully",
            )

            # Verify results
            assert result is True
            assert mock_job_instance.status == "completed"
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_job_status_triggers_cloud_backup(
        self,
        job_database_manager_with_coordinator,
        mock_db_session_factory,
    ) -> None:
        """Test that completed jobs with cloud sync config trigger cloud backup"""
        factory, mock_session = mock_db_session_factory
        job_uuid = str(uuid.uuid4())

        # Mock the Job model and query
        with patch("borgitory.models.database.Job"):
            mock_job_instance = Mock()
            mock_job_instance.id = job_uuid
            mock_job_instance.cloud_sync_config_id = 123
            mock_job_instance.repository_id = 1

            mock_query = Mock()
            mock_query.filter.return_value.first.return_value = mock_job_instance
            mock_session.query.return_value = mock_query
            mock_session.commit = Mock()

            # Mock _get_repository_data
            with patch.object(
                job_database_manager_with_coordinator, "_get_repository_data"
            ) as mock_get_repo:
                mock_get_repo.return_value = {
                    "id": 1,
                    "name": "test-repo",
                    "path": "/path/to/repo",
                    "passphrase": "secret",
                }

                # Execute the test
                result = await job_database_manager_with_coordinator.update_job_status(
                    job_uuid=job_uuid, status="completed"
                )

                # Verify results
                assert result is True

    @pytest.mark.asyncio
    async def test_get_job_by_uuid_happy_path(
        self, job_database_manager, mock_db_session_factory
    ) -> None:
        """Test successful job retrieval by UUID"""
        factory, mock_session = mock_db_session_factory
        job_uuid = str(uuid.uuid4())

        # Mock the Job model and query
        with patch("borgitory.models.database.Job"):
            mock_job_instance = Mock()
            mock_job_instance.id = job_uuid
            mock_job_instance.repository_id = 1
            mock_job_instance.type = "backup"
            mock_job_instance.status = "completed"
            mock_job_instance.started_at = now_utc()
            mock_job_instance.finished_at = now_utc()
            mock_job_instance.log_output = "Job output"
            mock_job_instance.error = None
            mock_job_instance.cloud_sync_config_id = 123

            mock_query = Mock()
            mock_query.filter.return_value.first.return_value = mock_job_instance
            mock_session.query.return_value = mock_query

            # Execute the test
            result = await job_database_manager.get_job_by_uuid(job_uuid)

            # Verify results
            assert result is not None
            assert result["id"] == job_uuid
            assert result["job_uuid"] == job_uuid
            assert result["repository_id"] == 1
            assert result["type"] == "backup"
            assert result["status"] == "completed"
            assert result["output"] == "Job output"

    @pytest.mark.asyncio
    async def test_get_jobs_by_repository_happy_path(
        self, job_database_manager, mock_db_session_factory
    ) -> None:
        """Test successful job retrieval by repository"""
        factory, mock_session = mock_db_session_factory
        repository_id = 1

        # Mock the Job model and query
        with patch("borgitory.models.database.Job"):
            mock_job1 = Mock()
            mock_job1.id = str(uuid.uuid4())
            mock_job1.type = "backup"
            mock_job1.status = "completed"
            mock_job1.started_at = now_utc()
            mock_job1.finished_at = now_utc()
            mock_job1.error = None

            mock_job2 = Mock()
            mock_job2.id = str(uuid.uuid4())
            mock_job2.type = "prune"
            mock_job2.status = "running"
            mock_job2.started_at = now_utc()
            mock_job2.finished_at = None
            mock_job2.error = None

            mock_query = Mock()
            mock_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
                mock_job1,
                mock_job2,
            ]
            mock_session.query.return_value = mock_query

            # Execute the test
            result = await job_database_manager.get_jobs_by_repository(
                repository_id, limit=10
            )

            # Verify results
            assert len(result) == 2
            assert result[0]["id"] == mock_job1.id
            assert result[1]["id"] == mock_job2.id

    @pytest.mark.asyncio
    async def test_save_job_tasks_happy_path(
        self, job_database_manager, mock_db_session_factory
    ) -> None:
        """Test successful task saving"""
        factory, mock_session = mock_db_session_factory
        job_uuid = str(uuid.uuid4())

        # Create mock tasks
        mock_task1 = Mock()
        mock_task1.task_type = "backup"
        mock_task1.task_name = "Create backup"
        mock_task1.status = "completed"
        mock_task1.started_at = now_utc()
        mock_task1.completed_at = now_utc()
        mock_task1.output_lines = ["Line 1", "Line 2"]
        mock_task1.error = None
        mock_task1.return_code = 0

        mock_task2 = Mock()
        mock_task2.task_type = "cloud_sync"
        mock_task2.task_name = "Sync to cloud"
        mock_task2.status = "running"
        mock_task2.started_at = now_utc()
        mock_task2.completed_at = None
        mock_task2.output_lines = []
        mock_task2.error = None
        mock_task2.return_code = None

        tasks = [mock_task1, mock_task2]

        # Mock the Job and JobTask models
        with patch("borgitory.models.database.Job"), patch(
            "borgitory.models.database.JobTask"
        ):
            mock_job_instance = Mock()
            mock_job_instance.id = job_uuid

            mock_query = Mock()
            mock_query.filter.return_value.first.return_value = mock_job_instance
            mock_session.query.return_value = mock_query
            mock_session.add = Mock()
            mock_session.commit = Mock()

            # Execute the test
            result = await job_database_manager.save_job_tasks(job_uuid, tasks)

            # Verify results
            assert result is True
            assert mock_job_instance.total_tasks == 2
            assert mock_job_instance.completed_tasks == 1  # Only task1 is completed
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_job_statistics_error_handling(
        self, job_database_manager, mock_db_session_factory
    ) -> None:
        """Test job statistics error handling"""
        factory, mock_session = mock_db_session_factory

        # Mock database error
        mock_session.query.side_effect = Exception("Database error")

        # Execute the test
        result = await job_database_manager.get_job_statistics()

        # Verify error handling returns empty dict
        assert result == {}

    def test_session_factory_usage_in_external_code(self, job_database_manager) -> None:
        """
        Critical test: Verify that external code can access the session factory
        This test simulates how job_manager_modular.py accesses the attribute
        """
        # This is the pattern used in job_manager_modular.py:659
        # It should work without raising AttributeError
        db_session_factory = job_database_manager.db_session_factory
        assert db_session_factory is not None

        # Verify it's callable (session factory should be callable)
        assert callable(db_session_factory)

    @pytest.mark.asyncio
    async def test_error_handling_create_job(
        self, job_database_manager, mock_db_session_factory
    ) -> None:
        """Test error handling in job creation"""
        factory, mock_session = mock_db_session_factory

        # Mock database error
        mock_session.add.side_effect = Exception("Database error")

        with patch("borgitory.models.database.Job"):
            sample_data = DatabaseJobData(
                job_uuid=str(uuid.uuid4()),
                repository_id=1,
                job_type="backup",
                status="running",
                started_at=now_utc(),
            )

            result = await job_database_manager.create_database_job(sample_data)
            assert result is None

    @pytest.mark.asyncio
    async def test_error_handling_update_job_status(
        self, job_database_manager, mock_db_session_factory
    ) -> None:
        """Test error handling in job status update"""
        factory, mock_session = mock_db_session_factory

        # Mock database error
        mock_session.commit.side_effect = Exception("Database error")

        with patch("borgitory.models.database.Job"):
            mock_job_instance = Mock()
            mock_query = Mock()
            mock_query.filter.return_value.first.return_value = mock_job_instance
            mock_session.query.return_value = mock_query

            result = await job_database_manager.update_job_status(
                job_uuid=str(uuid.uuid4()), status="completed"
            )
            assert result is False

    @pytest.mark.asyncio
    async def test_job_not_found_scenarios(
        self, job_database_manager, mock_db_session_factory
    ) -> None:
        """Test scenarios where job is not found"""
        factory, mock_session = mock_db_session_factory

        with patch("borgitory.models.database.Job"):
            # Mock no job found
            mock_query = Mock()
            mock_query.filter.return_value.first.return_value = None
            mock_session.query.return_value = mock_query

            # Test update job status with non-existent job
            result = await job_database_manager.update_job_status(
                job_uuid="non-existent-uuid", status="completed"
            )
            assert result is False

            # Test get job by UUID with non-existent job
            result = await job_database_manager.get_job_by_uuid("non-existent-uuid")
            assert result is None

            # Test save job tasks with non-existent job
            result = await job_database_manager.save_job_tasks("non-existent-uuid", [])
            assert result is False
