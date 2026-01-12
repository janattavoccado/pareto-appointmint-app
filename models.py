"""
Database Model Updates for Session State Storage
================================================

Add these methods to your existing DatabaseManager class in models.py
to support persistent session state across multiple workers.

Also add the session_states table creation to init_db().
"""

# ============================================================================
# Add to init_db() function - Create session_states table
# ============================================================================

SESSION_STATES_TABLE_SQL = """
-- Add this to your init_db() function after the reservations table creation

CREATE TABLE IF NOT EXISTS session_states (
    user_id TEXT PRIMARY KEY,
    state_json TEXT NOT NULL,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_session_states_last_updated 
ON session_states(last_updated);
"""


# ============================================================================
# Add these methods to DatabaseManager class
# ============================================================================

"""
Add these three methods to your DatabaseManager class:

    def get_session_state(self, user_id: str) -> Optional[str]:
        '''Get session state JSON for a user.'''
        try:
            if self.db_type == 'postgresql':
                self.cursor.execute(
                    "SELECT state_json FROM session_states WHERE user_id = %s",
                    (user_id,)
                )
            else:
                self.cursor.execute(
                    "SELECT state_json FROM session_states WHERE user_id = ?",
                    (user_id,)
                )
            
            result = self.cursor.fetchone()
            return result[0] if result else None
        except Exception as e:
            logger.error(f"Error getting session state: {e}")
            return None
    
    def save_session_state(self, user_id: str, state_json: str) -> bool:
        '''Save session state JSON for a user.'''
        try:
            if self.db_type == 'postgresql':
                self.cursor.execute('''
                    INSERT INTO session_states (user_id, state_json, last_updated)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (user_id) 
                    DO UPDATE SET state_json = EXCLUDED.state_json, 
                                  last_updated = CURRENT_TIMESTAMP
                ''', (user_id, state_json))
            else:
                self.cursor.execute('''
                    INSERT OR REPLACE INTO session_states (user_id, state_json, last_updated)
                    VALUES (?, ?, datetime('now'))
                ''', (user_id, state_json))
            
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error saving session state: {e}")
            return False
    
    def delete_session_state(self, user_id: str) -> bool:
        '''Delete session state for a user.'''
        try:
            if self.db_type == 'postgresql':
                self.cursor.execute(
                    "DELETE FROM session_states WHERE user_id = %s",
                    (user_id,)
                )
            else:
                self.cursor.execute(
                    "DELETE FROM session_states WHERE user_id = ?",
                    (user_id,)
                )
            
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error deleting session state: {e}")
            return False
    
    def cleanup_old_sessions(self, hours: int = 24) -> int:
        '''Delete session states older than specified hours.'''
        try:
            if self.db_type == 'postgresql':
                self.cursor.execute('''
                    DELETE FROM session_states 
                    WHERE last_updated < NOW() - INTERVAL '%s hours'
                ''', (hours,))
            else:
                self.cursor.execute('''
                    DELETE FROM session_states 
                    WHERE last_updated < datetime('now', '-' || ? || ' hours')
                ''', (hours,))
            
            deleted = self.cursor.rowcount
            self.conn.commit()
            return deleted
        except Exception as e:
            logger.error(f"Error cleaning up old sessions: {e}")
            return 0
"""

# ============================================================================
# Complete updated init_db() function
# ============================================================================

UPDATED_INIT_DB = '''
def init_db(self):
    """Initialize database tables."""
    try:
        # Create reservations table
        if self.db_type == 'postgresql':
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS reservations (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    user_name TEXT NOT NULL,
                    phone_number TEXT NOT NULL,
                    number_of_guests INTEGER NOT NULL,
                    date_time TIMESTAMP NOT NULL,
                    time_slot REAL DEFAULT 2.0,
                    status TEXT DEFAULT 'confirmed',
                    special_requests TEXT,
                    time_created TEXT
                )
            """)
            
            # Create session_states table for multi-worker support
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS session_states (
                    user_id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create index for faster session lookups
            self.cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_session_states_last_updated 
                ON session_states(last_updated)
            """)
        else:
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS reservations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    user_name TEXT NOT NULL,
                    phone_number TEXT NOT NULL,
                    number_of_guests INTEGER NOT NULL,
                    date_time TEXT NOT NULL,
                    time_slot REAL DEFAULT 2.0,
                    status TEXT DEFAULT 'confirmed',
                    special_requests TEXT,
                    time_created TEXT
                )
            """)
            
            # Create session_states table for multi-worker support
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS session_states (
                    user_id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    last_updated TEXT DEFAULT (datetime('now'))
                )
            """)
        
        self.conn.commit()
        print("Database tables initialized successfully")
        
    except Exception as e:
        print(f"Database tables already exist or error: {e}")
'''
