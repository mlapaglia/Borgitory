#!/usr/bin/env python3
"""Debug script to check job tasks loading"""

import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.db_session import get_db_session
from models.database import Job
from sqlalchemy.orm import joinedload


def main():
    with get_db_session() as db:
        print("=== Testing Job Tasks Loading ===")

        # Get recent jobs with tasks loaded
        jobs = (
            db.query(Job)
            .options(joinedload(Job.tasks))
            .order_by(Job.started_at.desc())
            .limit(3)
            .all()
        )

        if not jobs:
            print("No jobs found")
            return

        for job in jobs:
            print(f"\nJob: {job.id[:8]}...")
            print(f"  Type: {job.type}")
            print(f"  Status: {job.status}")
            print(f"  Total tasks: {job.total_tasks}")
            print(f"  Completed tasks: {job.completed_tasks}")
            print(f"  Tasks loaded: {len(job.tasks) if job.tasks else 0}")

            # Check if tasks relationship is working
            if hasattr(job, "tasks"):
                print(f"  Tasks attribute exists: {job.tasks}")
                if job.tasks:
                    print("  Tasks details:")
                    for i, task in enumerate(job.tasks):
                        print(f"    Task {i}: {task.task_name} ({task.task_type})")
                        print(f"      Status: {task.status}, Order: {task.task_order}")
                        print(f"      Has output: {'Yes' if task.output else 'No'}")
                else:
                    print("  Tasks list is empty")
            else:
                print("  No tasks attribute found")


if __name__ == "__main__":
    main()
