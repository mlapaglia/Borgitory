#!/usr/bin/env python3
"""Database management CLI for Borgitory using Alembic."""

import argparse
import sys
import os
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Set SECRET_KEY for import compatibility
if not os.getenv("SECRET_KEY"):
    os.environ["SECRET_KEY"] = "dev-secret-key-for-db-management"

from app.utils.migrations import (  # noqa: E402
    run_migrations,
    create_migration,
    stamp_database,
    show_migration_history,
    show_current_revision,
    get_current_revision,
    get_head_revision,
    database_needs_migration
)
from app.models.database import reset_db  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Borgitory Database Management")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Migrate command
    migrate_parser = subparsers.add_parser("migrate", help="Run database migrations")
    migrate_parser.add_argument("--dry-run", action="store_true", 
                               help="Show what would be migrated without applying changes")
    
    # Create migration command
    create_parser = subparsers.add_parser("create", help="Create a new migration")
    create_parser.add_argument("message", help="Migration message")
    create_parser.add_argument("--no-autogenerate", action="store_true",
                              help="Don't use autogenerate (create empty migration)")
    
    # Status command
    subparsers.add_parser("status", help="Show migration status")
    
    # History command
    subparsers.add_parser("history", help="Show migration history")
    
    # Current command
    subparsers.add_parser("current", help="Show current revision")
    
    # Stamp command
    stamp_parser = subparsers.add_parser("stamp", help="Stamp database with revision")
    stamp_parser.add_argument("revision", help="Revision to stamp (e.g., 'head', '001')")
    
    # Reset command
    reset_parser = subparsers.add_parser("reset", help="Reset database (DANGEROUS)")
    reset_parser.add_argument("--yes", action="store_true", 
                             help="Skip confirmation prompt")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    try:
        if args.command == "migrate":
            if args.dry_run:
                current = get_current_revision()
                head = get_head_revision()
                print(f"Current revision: {current}")
                print(f"Head revision: {head}")
                if database_needs_migration():
                    print("Migration would be applied")
                else:
                    print("No migration needed")
            else:
                success = run_migrations()
                return 0 if success else 1
                
        elif args.command == "create":
            autogenerate = not args.no_autogenerate
            success = create_migration(args.message, autogenerate)
            return 0 if success else 1
            
        elif args.command == "status":
            current = get_current_revision()
            head = get_head_revision()
            print(f"Current revision: {current or 'None'}")
            print(f"Head revision: {head or 'None'}")
            
            if database_needs_migration():
                print("Status: Migration needed")
            else:
                print("Status: Up to date")
                
        elif args.command == "history":
            show_migration_history()
            
        elif args.command == "current":
            show_current_revision()
            
        elif args.command == "stamp":
            success = stamp_database(args.revision)
            return 0 if success else 1
            
        elif args.command == "reset":
            if not args.yes:
                confirm = input("WARNING: This will DELETE ALL DATA! Are you sure? (yes/no): ")
                if confirm.lower() != "yes":
                    print("Operation cancelled")
                    return 0
            
            print("Resetting database...")
            reset_db()
            print("Database reset completed")
            
        return 0
        
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())