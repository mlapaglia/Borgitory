"""
Test suite for verifying cloud sync and notification task output saving
"""
import pytest
import uuid
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, UTC

from app.services.composite_job_manager import CompositeJobManager, CompositeJobInfo, CompositeJobTaskInfo
from app.services.job_database_manager import JobDatabaseManager


class TestTaskOutputSaving:
    """Test that cloud sync and notification tasks properly save output"""

    @pytest.fixture
    def mock_db_session_factory(self):
        """Create mock database session factory"""
        session = Mock()
        factory = Mock()
        factory.return_value.__enter__ = Mock(return_value=session)
        factory.return_value.__exit__ = Mock(return_value=None)
        return factory, session

    @pytest.fixture
    def composite_job_manager(self, mock_db_session_factory):
        """Create CompositeJobManager with mocked dependencies"""
        factory, _ = mock_db_session_factory
        manager = CompositeJobManager(db_session_factory=factory)
        return manager

    @pytest.fixture
    def job_database_manager(self, mock_db_session_factory):
        """Create JobDatabaseManager with mocked dependencies"""
        factory, _ = mock_db_session_factory
        return JobDatabaseManager(db_session_factory=factory)

    def test_cloud_sync_task_has_output_lines(self):
        """Test that cloud sync task properly structures output_lines"""
        task = CompositeJobTaskInfo(
            task_type="cloud_sync",
            task_name="Sync to Cloud"
        )
        
        # Simulate adding output lines like the real implementation does
        from datetime import datetime
        
        # This is how the cloud sync task adds output
        log_line = "[rclone] Syncing repository to cloud..."
        task.output_lines.append(
            {"timestamp": datetime.now().isoformat(), "text": log_line}
        )
        
        log_line2 = "[rclone] Upload completed successfully"  
        task.output_lines.append(
            {"timestamp": datetime.now().isoformat(), "text": log_line2}
        )
        
        # Verify output_lines structure
        assert len(task.output_lines) == 2
        assert task.output_lines[0]["text"] == "[rclone] Syncing repository to cloud..."
        assert task.output_lines[1]["text"] == "[rclone] Upload completed successfully"
        assert "timestamp" in task.output_lines[0]
        assert "timestamp" in task.output_lines[1]

    def test_notification_task_has_output_lines(self):
        """Test that notification task properly structures output_lines"""
        task = CompositeJobTaskInfo(
            task_type="notification",
            task_name="Send Notification"
        )
        
        # Simulate adding output lines like the real implementation does
        from datetime import datetime
        
        # This is how the notification task adds output
        initial_output = "Sending notification via pushover"
        task.output_lines.append(
            {"timestamp": datetime.now().isoformat(), "text": initial_output}
        )
        
        success_msg = "✅ Notification sent successfully via pushover"
        task.output_lines.append(
            {"timestamp": datetime.now().isoformat(), "text": success_msg}
        )
        
        # Verify output_lines structure
        assert len(task.output_lines) == 2
        assert task.output_lines[0]["text"] == "Sending notification via pushover"
        assert task.output_lines[1]["text"] == "✅ Notification sent successfully via pushover"

    def test_save_job_tasks_converts_output_lines_to_string(self, job_database_manager, mock_db_session_factory):
        """Test that save_job_tasks correctly converts output_lines to string output"""
        _, mock_session = mock_db_session_factory
        
        # Mock database job
        mock_job = Mock()
        mock_job.id = str(uuid.uuid4())
        mock_session.query().filter().first.return_value = mock_job
        
        # Create tasks with output_lines (like cloud sync and notification do)
        cloud_task = CompositeJobTaskInfo(
            task_type="cloud_sync", 
            task_name="Sync to Cloud"
        )
        cloud_task.status = "completed"
        cloud_task.output_lines = [
            {"timestamp": "2023-01-01T12:00:00", "text": "Starting cloud sync..."},
            {"timestamp": "2023-01-01T12:01:00", "text": "Uploading files..."},
            {"timestamp": "2023-01-01T12:02:00", "text": "Cloud sync completed"}
        ]
        
        notification_task = CompositeJobTaskInfo(
            task_type="notification",
            task_name="Send Notification"  
        )
        notification_task.status = "completed"
        notification_task.output_lines = [
            {"timestamp": "2023-01-01T12:03:00", "text": "Sending notification via pushover"},
            {"timestamp": "2023-01-01T12:03:30", "text": "✅ Notification sent successfully"}
        ]
        
        tasks = [cloud_task, notification_task]
        
        # Mock JobTask creation
        created_tasks = []
        def mock_add(task):
            created_tasks.append(task)
        mock_session.add.side_effect = mock_add
        
        # Call save_job_tasks
        import asyncio
        result = asyncio.run(job_database_manager.save_job_tasks(mock_job.id, tasks))
        
        # Verify it succeeded
        assert result is True
        
        # Verify tasks were created with proper output
        assert len(created_tasks) == 2
        
        # Check cloud sync task output
        cloud_db_task = created_tasks[0]
        expected_cloud_output = "Starting cloud sync...\nUploading files...\nCloud sync completed"
        assert cloud_db_task.output == expected_cloud_output
        assert cloud_db_task.task_type == "cloud_sync"
        assert cloud_db_task.task_name == "Sync to Cloud"
        
        # Check notification task output  
        notification_db_task = created_tasks[1]
        expected_notification_output = "Sending notification via pushover\n✅ Notification sent successfully"
        assert notification_db_task.output == expected_notification_output
        assert notification_db_task.task_type == "notification"
        assert notification_db_task.task_name == "Send Notification"

    def test_save_job_tasks_handles_empty_output_lines(self, job_database_manager, mock_db_session_factory):
        """Test that save_job_tasks handles tasks with empty output_lines"""
        _, mock_session = mock_db_session_factory
        
        # Mock database job
        mock_job = Mock()
        mock_job.id = str(uuid.uuid4())
        mock_session.query().filter().first.return_value = mock_job
        
        # Create task with empty output_lines
        empty_task = CompositeJobTaskInfo(
            task_type="cloud_sync",
            task_name="Empty Sync Task"
        )
        empty_task.status = "skipped"
        empty_task.output_lines = []  # Empty output
        
        tasks = [empty_task]
        
        # Mock JobTask creation
        created_tasks = []
        mock_session.add.side_effect = lambda task: created_tasks.append(task)
        
        # Call save_job_tasks
        import asyncio
        result = asyncio.run(job_database_manager.save_job_tasks(mock_job.id, tasks))
        
        # Verify it succeeded
        assert result is True
        
        # Verify task was created with empty output
        assert len(created_tasks) == 1
        db_task = created_tasks[0]
        assert db_task.output == ""  # Should be empty string, not None
        assert db_task.task_type == "cloud_sync"

    def test_save_job_tasks_handles_mixed_output_formats(self, job_database_manager, mock_db_session_factory):
        """Test that save_job_tasks handles both output_lines and output formats"""
        _, mock_session = mock_db_session_factory
        
        # Mock database job
        mock_job = Mock()
        mock_job.id = str(uuid.uuid4())
        mock_session.query().filter().first.return_value = mock_job
        
        # Task with output_lines (new format)
        task_with_lines = CompositeJobTaskInfo(
            task_type="notification",
            task_name="New Format Task"
        )
        task_with_lines.status = "completed"
        task_with_lines.output_lines = [
            {"text": "Line 1"},
            {"text": "Line 2"}
        ]
        
        # Task with output string (old format)  
        task_with_output = CompositeJobTaskInfo(
            task_type="backup",
            task_name="Old Format Task"
        )
        task_with_output.status = "completed"
        task_with_output.output = "Direct output string"
        
        tasks = [task_with_lines, task_with_output]
        
        # Mock JobTask creation
        created_tasks = []
        mock_session.add.side_effect = lambda task: created_tasks.append(task)
        
        # Call save_job_tasks
        import asyncio
        result = asyncio.run(job_database_manager.save_job_tasks(mock_job.id, tasks))
        
        # Verify both formats work
        assert result is True
        assert len(created_tasks) == 2
        
        # Check output_lines was converted to string
        assert created_tasks[0].output == "Line 1\nLine 2"
        
        # Check direct output was preserved
        assert created_tasks[1].output == "Direct output string"


class TestTaskOutputDebugging:
    """Tests to help debug why cloud sync/notification show 'No output available'"""

    def test_task_output_lines_structure_matches_expectations(self):
        """Test that task output_lines match what save_job_tasks expects"""
        
        # This is what the composite job manager actually creates
        task = CompositeJobTaskInfo(
            task_type="cloud_sync",
            task_name="Test Cloud Sync"
        )
        
        # This is exactly how the composite job manager adds output
        from datetime import datetime
        log_line = "[stdout] Syncing to S3..."
        task.output_lines.append(
            {"timestamp": datetime.now().isoformat(), "text": log_line}
        )
        
        # Test the extraction logic from save_job_tasks
        task_output = ""
        if hasattr(task, "output_lines") and task.output_lines:
            task_output = "\n".join([
                line.get("text", "") if isinstance(line, dict) else str(line)
                for line in task.output_lines
            ])
        
        # Should extract the text properly
        assert task_output == "[stdout] Syncing to S3..."
        
        # Test with multiple lines
        task.output_lines.append(
            {"timestamp": datetime.now().isoformat(), "text": "Upload complete"}
        )
        
        task_output = "\n".join([
            line.get("text", "") if isinstance(line, dict) else str(line)
            for line in task.output_lines
        ])
        
        assert task_output == "[stdout] Syncing to S3...\nUpload complete"

    def test_task_without_output_shows_empty_string(self):
        """Test that tasks without output get empty string, not None"""
        
        task = CompositeJobTaskInfo(
            task_type="notification", 
            task_name="Empty Notification"
        )
        
        # No output_lines added (like a skipped task might have)
        
        # Test the extraction logic from save_job_tasks
        task_output = ""
        if hasattr(task, "output_lines") and task.output_lines:
            task_output = "\n".join([
                line.get("text", "") if isinstance(line, dict) else str(line)
                for line in task.output_lines
            ])
        elif hasattr(task, "output") and task.output:
            task_output = task.output
        
        # Should be empty string
        assert task_output == ""
        assert task_output is not None

    def test_identify_potential_output_loss_scenarios(self):
        """Test scenarios where output might be lost"""
        
        scenarios = [
            # Scenario 1: output_lines is None instead of empty list
            {"output_lines": None, "expected": ""},
            
            # Scenario 2: output_lines has items but no 'text' key
            {"output_lines": [{"timestamp": "2023-01-01"}], "expected": ""},
            
            # Scenario 3: output_lines has None values
            {"output_lines": [{"text": None}], "expected": ""},
            
            # Scenario 4: output_lines has empty strings
            {"output_lines": [{"text": ""}], "expected": ""},
            
            # Scenario 5: Mixed valid/invalid entries
            {"output_lines": [
                {"text": "Valid line"}, 
                {"timestamp": "2023-01-01"},  # No text key
                {"text": "Another valid line"}
            ], "expected": "Valid line\n\nAnother valid line"},
        ]
        
        for i, scenario in enumerate(scenarios):
            task = CompositeJobTaskInfo(
                task_type="test",
                task_name=f"Test Scenario {i+1}"
            )
            
            # Set the scenario output_lines
            task.output_lines = scenario["output_lines"]
            
            # Apply save_job_tasks extraction logic
            task_output = ""
            if hasattr(task, "output_lines") and task.output_lines:
                task_output = "\n".join([
                    (line.get("text", "") or "") if isinstance(line, dict) else str(line)
                    for line in task.output_lines
                ])
            
            assert task_output == scenario["expected"], f"Scenario {i+1} failed"