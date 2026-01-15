#!/usr/bin/env python3
"""
Database Migration Script
Adds missing columns to existing tables for v4.0 compatibility.

Run this script after deploying the new code:
    heroku run python migrate_add_columns.py -a your-app-name
"""

import os
import sys
from sqlalchemy import create_engine, text, inspect

def get_database_url():
    """Get database URL from environment."""
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set")
        sys.exit(1)
    
    # Fix for Heroku PostgreSQL URL format
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    return database_url

def run_migration():
    """Run database migrations to add missing columns."""
    database_url = get_database_url()
    engine = create_engine(database_url)
    
    print("=" * 60)
    print("Database Migration Script v4.0")
    print("=" * 60)
    
    with engine.connect() as conn:
        inspector = inspect(engine)
        
        # =====================================================
        # RESERVATIONS TABLE MIGRATIONS
        # =====================================================
        print("\n[1/4] Checking reservations table...")
        
        if 'reservations' in inspector.get_table_names():
            existing_columns = [col['name'] for col in inspector.get_columns('reservations')]
            print(f"     Existing columns: {existing_columns}")
            
            # Add special_requests column if missing
            if 'special_requests' not in existing_columns:
                print("     Adding 'special_requests' column...")
                conn.execute(text("""
                    ALTER TABLE reservations 
                    ADD COLUMN special_requests TEXT
                """))
                conn.commit()
                print("     ✓ Added 'special_requests' column")
            else:
                print("     ✓ 'special_requests' column already exists")
            
            # Add table_number column if missing
            if 'table_number' not in existing_columns:
                print("     Adding 'table_number' column...")
                conn.execute(text("""
                    ALTER TABLE reservations 
                    ADD COLUMN table_number VARCHAR(50)
                """))
                conn.commit()
                print("     ✓ Added 'table_number' column")
            else:
                print("     ✓ 'table_number' column already exists")
        else:
            print("     ! reservations table does not exist (will be created on first run)")
        
        # =====================================================
        # SESSION_STATES TABLE
        # =====================================================
        print("\n[2/4] Checking session_states table...")
        
        if 'session_states' not in inspector.get_table_names():
            print("     Creating 'session_states' table...")
            conn.execute(text("""
                CREATE TABLE session_states (
                    user_id VARCHAR(255) PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
            print("     ✓ Created 'session_states' table")
        else:
            print("     ✓ 'session_states' table already exists")
        
        # =====================================================
        # ADMIN_USERS TABLE
        # =====================================================
        print("\n[3/4] Checking admin_users table...")
        
        if 'admin_users' not in inspector.get_table_names():
            print("     Creating 'admin_users' table...")
            conn.execute(text("""
                CREATE TABLE admin_users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(100) UNIQUE NOT NULL,
                    email VARCHAR(255),
                    password_hash VARCHAR(255) NOT NULL,
                    full_name VARCHAR(255),
                    role VARCHAR(50) DEFAULT 'admin',
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP
                )
            """))
            conn.commit()
            print("     ✓ Created 'admin_users' table")
            
            # Create default admin user
            print("     Creating default admin user...")
            from werkzeug.security import generate_password_hash
            password_hash = generate_password_hash('admin123')
            conn.execute(text("""
                INSERT INTO admin_users (username, email, password_hash, full_name, role)
                VALUES ('admin', 'admin@example.com', :password_hash, 'Administrator', 'superadmin')
                ON CONFLICT (username) DO NOTHING
            """), {'password_hash': password_hash})
            conn.commit()
            print("     ✓ Created default admin user (admin / admin123)")
        else:
            print("     ✓ 'admin_users' table already exists")
            
            # Check for missing columns in admin_users
            existing_columns = [col['name'] for col in inspector.get_columns('admin_users')]
            
            if 'role' not in existing_columns:
                print("     Adding 'role' column...")
                conn.execute(text("""
                    ALTER TABLE admin_users 
                    ADD COLUMN role VARCHAR(50) DEFAULT 'admin'
                """))
                conn.commit()
                print("     ✓ Added 'role' column")
            
            if 'is_active' not in existing_columns:
                print("     Adding 'is_active' column...")
                conn.execute(text("""
                    ALTER TABLE admin_users 
                    ADD COLUMN is_active BOOLEAN DEFAULT TRUE
                """))
                conn.commit()
                print("     ✓ Added 'is_active' column")
        
        # =====================================================
        # USER_MEMORIES TABLE
        # =====================================================
        print("\n[4/4] Checking user_memories table...")
        
        if 'user_memories' not in inspector.get_table_names():
            print("     Creating 'user_memories' table...")
            conn.execute(text("""
                CREATE TABLE user_memories (
                    id SERIAL PRIMARY KEY,
                    user_id VARCHAR(255) NOT NULL,
                    memory_key VARCHAR(255) NOT NULL,
                    memory_value TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, memory_key)
                )
            """))
            conn.commit()
            print("     ✓ Created 'user_memories' table")
        else:
            print("     ✓ 'user_memories' table already exists")
    
    print("\n" + "=" * 60)
    print("Migration completed successfully!")
    print("=" * 60)
    print("\nYou can now access the admin dashboard at /admin")
    print("Default login: admin / admin123")
    print("\n⚠️  IMPORTANT: Change the default password after first login!")

if __name__ == '__main__':
    run_migration()
