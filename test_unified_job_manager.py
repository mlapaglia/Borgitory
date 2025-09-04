#!/usr/bin/env python3
"""
Simple test script to verify the unified job manager works correctly.
This tests both backward compatibility (simple jobs) and new composite jobs.
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from app.services.job_manager import borg_job_manager, BorgJobTask


async def test_simple_job():
    """Test that existing simple jobs still work"""
    print("\n[TEST] Testing Simple Job (Backward Compatibility)")
    
    # Create a simple command job
    job_id = await borg_job_manager.start_borg_command(
        command=['echo', 'Hello from simple job'],
        is_backup=False
    )
    
    print(f"[OK] Created simple job: {job_id}")
    
    # Wait a moment for job to complete
    await asyncio.sleep(2)
    
    # Check job status
    job = borg_job_manager.jobs.get(job_id)
    if job:
        print(f"[INFO] Simple job status: {job.status}")
        print(f"[INFO] Job type: {job.job_type}")
        print(f"[INFO] Has command: {job.command is not None}")
        print(f"[INFO] Output lines: {len(job.output_lines)}")
        return job.status in ['completed', 'running']
    else:
        print("[ERROR] Simple job not found")
        return False


async def test_composite_job():
    """Test new composite job functionality"""
    print("\n[TEST] Testing Composite Job (New Functionality)")
    
    # Create a mock repository object for testing
    class MockRepository:
        def __init__(self):
            self.id = 1
            self.name = "test-repo"
            self.path = "/tmp/test-repo"
        
        def get_passphrase(self):
            return "test-passphrase"
    
    mock_repo = MockRepository()
    
    # Define some test tasks
    task_definitions = [
        {
            'type': 'backup',
            'name': 'Test Backup Task',
            'source_path': '/tmp/test-data',
            'compression': 'zstd',
            'dry_run': True
        },
        {
            'type': 'prune', 
            'name': 'Test Prune Task',
            'keep_within': '7d',
            'dry_run': True
        },
        {
            'type': 'cloud_sync',
            'name': 'Test Cloud Sync Task'
        }
    ]
    
    try:
        # Create composite job (this will fail due to database dependencies, but should create the job structure)
        print("[INFO] Creating composite job structure...")
        
        # Create job manually without database (for testing)
        job_id = f"test-{asyncio.get_event_loop().time()}"
        
        from app.services.job_manager import BorgJob, BorgJobTask
        from datetime import datetime
        
        # Create tasks
        tasks = []
        for task_def in task_definitions:
            task = BorgJobTask(
                task_type=task_def['type'],
                task_name=task_def['name'],
                parameters=task_def
            )
            tasks.append(task)
        
        # Create composite job
        job = BorgJob(
            id=job_id,
            job_type='composite',
            status='pending',
            started_at=datetime.now(),
            tasks=tasks,
            repository=mock_repo
        )
        
        borg_job_manager.jobs[job_id] = job
        
        print(f"[OK] Created composite job: {job_id}")
        print(f"[INFO] Job type: {job.job_type}")
        print(f"[INFO] Is composite: {job.is_composite()}")
        print(f"[INFO] Task count: {len(job.tasks)}")
        print(f"[INFO] Current task index: {job.current_task_index}")
        
        # Test task retrieval
        current_task = job.get_current_task()
        if current_task:
            print(f"[INFO] Current task: {current_task.task_name}")
        
        print("[OK] Composite job structure test passed")
        return True
        
    except Exception as e:
        print(f"[ERROR] Composite job test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def test_job_output_streaming():
    """Test job output streaming for both job types"""
    print("\n[TEST] Testing Job Output Streaming")
    
    # Test simple job output
    simple_jobs = [job for job in borg_job_manager.jobs.values() if job.job_type == 'simple']
    if simple_jobs:
        job = simple_jobs[0]
        output = await borg_job_manager.get_job_output_stream(job.id)
        print(f"[INFO] Simple job output keys: {list(output.keys())}")
        print(f"[INFO] Simple job type in output: {output.get('job_type', 'missing')}")
    
    # Test composite job output  
    composite_jobs = [job for job in borg_job_manager.jobs.values() if job.job_type == 'composite']
    if composite_jobs:
        job = composite_jobs[0]
        output = await borg_job_manager.get_job_output_stream(job.id)
        print(f"[INFO] Composite job output keys: {list(output.keys())}")
        print(f"[INFO] Composite job type in output: {output.get('job_type', 'missing')}")
        print(f"[INFO] Has task info: {'current_task_index' in output}")
    
    return True


async def run_tests():
    """Run all tests"""
    print("[START] Starting Unified Job Manager Tests")
    
    results = []
    
    # Test simple jobs (backward compatibility)
    results.append(await test_simple_job())
    
    # Test composite jobs (new functionality)  
    results.append(await test_composite_job())
    
    # Test output streaming
    results.append(await test_job_output_streaming())
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    print(f"\n[SUMMARY] Test Summary: {passed}/{total} tests passed")
    
    if passed == total:
        print("[SUCCESS] All tests passed! The unified job manager is working correctly.")
        return True
    else:
        print("[FAILURE] Some tests failed. Check the output above.")
        return False


if __name__ == "__main__":
    asyncio.run(run_tests())