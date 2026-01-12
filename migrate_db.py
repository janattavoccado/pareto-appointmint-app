#!/usr/bin/env python3
"""
Database Migration Script for Admin Dashboard
==============================================

This script creates the necessary database tables for the admin dashboard:
- admin_users: Stores admin user accounts with secure password hashing
- session_states: Stores conversation session state for multi-worker support

Usage:
    # Run locally
    python migrate_db.py
    
    # Run on Heroku
    heroku run python migrate_db.py -a your-app-name

The script will:
1. Create the admin_users table if it doesn't exist
2. Create the session_states table if it doesn't exist
3. Create a default admin user (admin/admin123) if no admins exist

WARNING: Change the default admin password immediately after first login!
"""

import os
import sys
import hashlib
import secrets
from datetime import datetime

# Try to import SQLAlchemy
try:
    from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, Text, Boolean, inspect
    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy.orm import sessionmaker
except ImportError:
    print("ERROR: SQLAlchemy is not installed.")
    print("Install it with: pip install sqlalchemy")
    sys.exit(1)

# Try to import psycopg2 for PostgreSQL
try:
    import psycopg2
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False


def get_database_url():
    """Get the database URL from environment variables."""
    database_url = os.getenv('DATABASE_URL')
    
    if database_url is None:
        print("WARNING: DATABASE_URL not set, using SQLite for local development")
        return 'sqlite:///restaurant_bookings.db'
    
    # Heroku uses 'postgres://' but SQLAlchemy 1.4+ requires 'postgresql://'
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    return database_url


def hash_password(password: str, salt: str) -> str:
    """Create a secure hash of the password with salt."""
    return hashlib.sha256((password + salt).encode()).hexdigest()


def run_migration():
    """Run the database migration."""
    print("=" * 60)
    print("Admin Dashboard Database Migration")
    print("=" * 60)
    
    database_url = get_database_url()
    db_type = 'PostgreSQL' if 'postgresql' in database_url else 'SQLite'
    print(f"\nDatabase type: {db_type}")
    
    if db_type == 'PostgreSQL' and not HAS_PSYCOPG2:
        print("WARNING: psycopg2 not installed. Install with: pip install psycopg2-binary")
    
    # Create engine
    try:
        if database_url.startswith('sqlite'):
            engine = create_engine(database_url, connect_args={'check_same_thread': False})
        else:
            engine = create_engine(database_url, pool_pre_ping=True)
        
        print("Database connection: OK")
    except Exception as e:
        print(f"ERROR: Failed to connect to database: {e}")
        sys.exit(1)
    
    # Check existing tables
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    print(f"\nExisting tables: {existing_tables}")
    
    # Create session
    Session = sessionmaker(bind=engine)
    session = Session()
    
    # =========================================================================
    # Create admin_users table
    # =========================================================================
    print("\n" + "-" * 40)
    print("Creating admin_users table...")
    
    if 'admin_users' in existing_tables:
        print("  Table already exists, skipping creation")
    else:
        if db_type == 'PostgreSQL':
            create_admin_users_sql = """
            CREATE TABLE admin_users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) UNIQUE NOT NULL,
                email VARCHAR(255) UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                salt VARCHAR(64) NOT NULL,
                full_name VARCHAR(200),
                is_active BOOLEAN DEFAULT TRUE,
                is_superadmin BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            );
            CREATE INDEX idx_admin_users_username ON admin_users(username);
            """
        else:
            create_admin_users_sql = """
            CREATE TABLE admin_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username VARCHAR(100) UNIQUE NOT NULL,
                email VARCHAR(255) UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                salt VARCHAR(64) NOT NULL,
                full_name VARCHAR(200),
                is_active BOOLEAN DEFAULT 1,
                is_superadmin BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            );
            CREATE INDEX idx_admin_users_username ON admin_users(username);
            """
        
        try:
            with engine.connect() as conn:
                for statement in create_admin_users_sql.strip().split(';'):
                    if statement.strip():
                        conn.execute(statement)
                conn.commit()
            print("  Table created successfully")
        except Exception as e:
            print(f"  ERROR: {e}")
            sys.exit(1)
    
    # =========================================================================
    # Create session_states table
    # =========================================================================
    print("\n" + "-" * 40)
    print("Creating session_states table...")
    
    if 'session_states' in existing_tables:
        print("  Table already exists, skipping creation")
    else:
        if db_type == 'PostgreSQL':
            create_session_states_sql = """
            CREATE TABLE session_states (
                user_id VARCHAR(255) PRIMARY KEY,
                state_json TEXT NOT NULL,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX idx_session_states_last_updated ON session_states(last_updated);
            """
        else:
            create_session_states_sql = """
            CREATE TABLE session_states (
                user_id VARCHAR(255) PRIMARY KEY,
                state_json TEXT NOT NULL,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX idx_session_states_last_updated ON session_states(last_updated);
            """
        
        try:
            with engine.connect() as conn:
                for statement in create_session_states_sql.strip().split(';'):
                    if statement.strip():
                        conn.execute(statement)
                conn.commit()
            print("  Table created successfully")
        except Exception as e:
            print(f"  ERROR: {e}")
            sys.exit(1)
    
    # =========================================================================
    # Create default admin user
    # =========================================================================
    print("\n" + "-" * 40)
    print("Checking for default admin user...")
    
    try:
        with engine.connect() as conn:
            result = conn.execute("SELECT COUNT(*) FROM admin_users")
            count = result.fetchone()[0]
            
            if count == 0:
                print("  No admin users found, creating default admin...")
                
                salt = secrets.token_hex(32)
                password_hash = hash_password('admin123', salt)
                
                if db_type == 'PostgreSQL':
                    insert_sql = """
                    INSERT INTO admin_users (username, email, password_hash, salt, full_name, is_active, is_superadmin, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    conn.execute(insert_sql, (
                        'admin',
                        'admin@restaurant.com',
                        password_hash,
                        salt,
                        'Default Administrator',
                        True,
                        True,
                        datetime.utcnow()
                    ))
                else:
                    insert_sql = """
                    INSERT INTO admin_users (username, email, password_hash, salt, full_name, is_active, is_superadmin, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    conn.execute(insert_sql, (
                        'admin',
                        'admin@restaurant.com',
                        password_hash,
                        salt,
                        'Default Administrator',
                        1,
                        1,
                        datetime.utcnow().isoformat()
                    ))
                
                conn.commit()
                print("  Default admin created:")
                print("    Username: admin")
                print("    Password: admin123")
                print("")
                print("  ⚠️  WARNING: Change this password immediately!")
            else:
                print(f"  Found {count} existing admin user(s), skipping default creation")
    except Exception as e:
        print(f"  ERROR: {e}")
    
    # =========================================================================
    # Summary
    # =========================================================================
    print("\n" + "=" * 60)
    print("Migration completed!")
    print("=" * 60)
    
    # Verify tables
    inspector = inspect(engine)
    final_tables = inspector.get_table_names()
    print(f"\nFinal tables: {final_tables}")
    
    if 'admin_users' in final_tables and 'session_states' in final_tables:
        print("\n✅ All required tables are present")
    else:
        print("\n❌ Some tables are missing!")
        if 'admin_users' not in final_tables:
            print("   - admin_users is missing")
        if 'session_states' not in final_tables:
            print("   - session_states is missing")
    
    print("\nNext steps:")
    print("1. Deploy your application")
    print("2. Go to /admin to access the dashboard")
    print("3. Login with admin/admin123")
    print("4. Change the default password immediately!")
    print("")


if __name__ == '__main__':
    run_migration()
