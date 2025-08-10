# Database.py
print("Starting database file...")

import mysql.connector
from mysql.connector.pooling import MySQLConnectionPool
import traceback
import time
import asyncio
from datetime import timezone
import datetime
import socket
import sys
print("Imports completed...")

try:
    from utils.utils import config, logger, lock
    print("Utils imports completed...")
    print(f"Database config: host={config.get('sql_host')}, user={config.get('sql_user')}, database={config.get('sql_database')}, port={config.get('sql_port')}")
except Exception as e:
    print(f"Failed to import utils or access config: {e}")
    print(traceback.format_exc())
    sys.exit(1)

def test_socket_connection(host, port, timeout=5):
    """Test raw socket connection to database server"""
    print(f"Testing socket connection to {host}:{port}")
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        print("Socket connection successful")
        return True
    except socket.timeout:
        print(f"Socket connection timed out after {timeout} seconds")
        return False
    except socket.gaierror:
        print(f"Socket address resolution failed - Could not resolve {host}")
        return False
    except ConnectionRefusedError:
        print(f"Connection refused - Nothing listening on {host}:{port}")
        return False
    except Exception as e:
        print(f"Socket connection failed: {e}")
        return False
    
def get_safe_connection_params(params):
    """
    Create a safe copy of connection parameters for printing,
    hiding sensitive information.
    """
    safe_params = params.copy()
    if 'password' in safe_params:
        safe_params['password'] = '***'
    return safe_params

def test_database_connection():
    """
    Test database connection with credentials from config.
    Returns:
        bool: True if connection successful, False otherwise
    """
    print("Testing database connection...")
    
    # First test raw socket connection
    if not test_socket_connection(config['sql_host'], config['sql_port']):
        print("Basic connectivity test failed - check firewall and network settings")
        return False

    connection_attempts = [
        # Attempt 1: Basic connection
        {
            'host': config['sql_host'],
            'user': config['sql_user'],
            'password': config['sql_password'],
            'database': config['sql_database'],
            'port': config['sql_port']
        },
        # Attempt 2: With connection timeout
        {
            'host': config['sql_host'],
            'user': config['sql_user'],
            'password': config['sql_password'],
            'database': config['sql_database'],
            'port': config['sql_port'],
            'connect_timeout': 10
        },
        # Attempt 3: Force pure Python implementation
        {
            'host': config['sql_host'],
            'user': config['sql_user'],
            'password': config['sql_password'],
            'database': config['sql_database'],
            'port': config['sql_port'],
            'use_pure': True
        }
    ]

    for i, connect_args in enumerate(connection_attempts, 1):
        try:
            print(f"\nAttempting MySQL connection (Method {i})...")
            safe_params = get_safe_connection_params(connect_args)
            print(f"Connection parameters: {safe_params}")
            
            # Add small delay between attempts
            if i > 1:
                time.sleep(2)
            
            # Try to establish connection
            print("Establishing connection...")
            conn = mysql.connector.connect(**connect_args)
            
            print("Connection established, testing query...")
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            print(f"Test query result: {result}")
            cursor.close()
            
            print("Test query successful")
            conn.close()
            print("Database connection test successful")
            
            # Store successful connection parameters
            global successful_connection_params
            successful_connection_params = connect_args.copy()
            return True
            
        except mysql.connector.Error as err:
            print(f"Method {i} failed: {err}")
            if hasattr(err, 'errno'):
                print(f"MySQL Error Code: {err.errno}")
                if err.errno == 2003:
                    print("Can't connect to MySQL server - Is the server running and accessible?")
                elif err.errno == 1045:
                    print("Access denied - Check username and password")
                elif err.errno == 1049:
                    print("Unknown database - Check database name")
                elif err.errno == 2013:
                    print("Lost connection to MySQL server - Check network stability")
            continue
        except Exception as e:
            print(f"Method {i} failed with unexpected error: {e}")
            print(traceback.format_exc())
            continue

    print("\nAll connection attempts failed")
    return False

print("Testing basic MySQL connection...")
try:
    # Most basic possible connection
    print("Attempting basic connection...")
    db = mysql.connector.connect(
        host=config['sql_host'],
        user=config['sql_user'],
        password=config['sql_password'],
        database=config['sql_database'],
        port=config['sql_port'],
        connect_timeout=5  # Short timeout
    )
    print("Connection successful!")
    db.close()
except mysql.connector.Error as err:
    print(f"MySQL Connection Error: {err}")
    if hasattr(err, 'errno'):
        print(f"Error code: {err.errno}")
    sys.exit(1)
except Exception as e:
    print(f"Unexpected error: {e}")
    print(traceback.format_exc())
    sys.exit(1)

# If we get here, basic connection worked, now try pools
print("Basic connection successful, setting up pools...")

# Test connection before proceeding
if not test_database_connection():
    sys.exit(1)

# Global variables
db = None
cursor = None
timer_db = None
cursor_tb = None
db_pool = None
db_pool_timer = None
_sessions_dict_cache = None
_last_dict_update = None
_sessions_dict_lock = asyncio.Lock()

# Constants
MAIN_POOL_SIZE = 5
TIMER_POOL_SIZE = 3
CONNECTION_TIMEOUT = 120
RETRY_DELAY = 5  # seconds
MAX_RETRIES = 3

GAME_CHANNELS = []

# Functions to get database connections
def get_db_connection():
    """
    Gets a connection from the main connection pool.
    
    Returns:
        MySQLConnection: A connection from the main pool
        
    Raises:
        mysql.connector.Error: If unable to get connection
    """
    global db_pool
    if db_pool is None:
        setup_pool()
    return db_pool.get_connection()

def get_db_connection_timer():
    """
    Gets a connection from the timer connection pool.
    
    Returns:
        MySQLConnection: A connection from the timer pool
        
    Raises:
        mysql.connector.Error: If unable to get connection
    """
    global db_pool_timer
    if db_pool_timer is None:
        setup_pool()
    return db_pool_timer.get_connection()

def get_current_new_cursor():
    """
    DEPRECATED: This function is maintained for backward compatibility.
    Use execute_query() for new code.
    
    Returns:
        tuple: (connection, cursor) from the main pool
    """
    logger.warning("get_current_new_cursor is deprecated. Please use execute_query instead.")
    connection = get_db_connection()
    return connection, connection.cursor()

# Function to get the current database connection and cursor for the timer pool
# In database.py, replace the setup_pool and execute_query functions:
def setup_pool(config=config):
    """
    Sets up MySQL connection pools with robust error handling.
    Returns:
        bool: True if pools were successfully set up, False otherwise
    """
    global db_pool, db_pool_timer
    
    for attempt in range(MAX_RETRIES):
        try:
            pool_config = {
                'host': config['sql_host'],
                'user': config['sql_user'],
                'password': config['sql_password'],
                'database': config['sql_database'],
                'port': config['sql_port'],
                'pool_reset_session': True,
                'connect_timeout': CONNECTION_TIMEOUT
            }
            
            # Create main pool
            if db_pool is None:
                db_pool = MySQLConnectionPool(
                    pool_name="button_pool",
                    pool_size=MAIN_POOL_SIZE,
                    **pool_config
                )
                logger.info("Main connection pool created successfully")

            # Create timer pool
            if db_pool_timer is None:
                db_pool_timer = MySQLConnectionPool(
                    pool_name="button_pool_timer",
                    pool_size=TIMER_POOL_SIZE,
                    **pool_config
                )
                logger.info("Timer connection pool created successfully")

            # Test both pools
            test_conn1 = db_pool.get_connection()
            test_conn1.close()
            test_conn2 = db_pool_timer.get_connection()
            test_conn2.close()
            
            return True

        except mysql.connector.Error as error:
            logger.error(f"Database pool setup attempt {attempt + 1} failed: {error}")
            print(f"Database pool setup attempt {attempt + 1} failed: {error}")
            
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                continue
            else:
                logger.critical("Failed to set up database pools after all retries")
                print("Critical: Failed to set up database pools after all retries")
                return False

        except Exception as e:
            logger.critical(f"Unexpected error setting up database pools: {e}")
            logger.critical(traceback.format_exc())
            print(f"Critical unexpected error in database setup: {e}")
            return False

def execute_query(query, params=None, is_timer=False, retry_attempts=3, commit=False):
    """
    Executes a database query using the appropriate connection pool with retry logic.
    Args:
        query (str): SQL query to execute
        params (tuple, optional): Parameters for the query
        is_timer (bool): Whether to use the timer pool (default: False)
        retry_attempts (int): Number of retry attempts for failed queries (default: 3)
        commit (bool): Whether to commit the transaction (default: False)
    Returns:
        list/bool: Query results if SELECT, True if successful INSERT/UPDATE/DELETE, None if failed
    """
    global db_pool, db_pool_timer
    
    # Determine if this is a SELECT query
    is_select_query = query.strip().upper().startswith("SELECT")
    
    # Ensure pools are set up
    if db_pool is None or db_pool_timer is None:
        if not setup_pool():
            logger.error("Failed to setup database pools")
            return [] if is_select_query else None
    
    pool = db_pool_timer if is_timer else db_pool
    last_error = None
    
    for attempt in range(retry_attempts):
        connection = None
        cursor = None
        try:
            connection = pool.get_connection()
            cursor = connection.cursor()
            cursor.execute(query, params)
            
            if commit:
                connection.commit()
            
            # For SELECT queries, always fetch results
            if is_select_query:
                result = cursor.fetchall()
                # Debug info to help diagnose
                if not result:
                    logger.debug(f"SELECT query returned no rows: {query[:100]}")
            else:
                # For non-SELECT queries, return success indicator
                result = True
                if cursor.rowcount > 0:
                    logger.debug(f"Non-SELECT query affected {cursor.rowcount} rows")
            
            return result
            
        except mysql.connector.Error as error:
            last_error = error
            logger.warning(
                f"Database error (attempt {attempt + 1}/{retry_attempts}): {error}\n"
                f"Query: {query[:100]}, Params: {params}"
            )
            if attempt < retry_attempts - 1:  # Don't sleep on last attempt
                time.sleep(min(2 ** attempt, 10))  # Exponential backoff
        except Exception as e:
            logger.error(f"Unexpected error executing query: {e}")
            logger.error(traceback.format_exc())
            raise
        finally:
            if cursor:
                try:
                    cursor.close()
                except:
                    pass
            if connection:
                try:
                    connection.close()
                except:
                    pass
    
    # If we get here, all attempts failed
    logger.error(
        f"Query failed after {retry_attempts} attempts. Last error: {last_error}\n"
        f"Query: {query[:100]}, Params: {params}"
    )
    
    # Return appropriate failure value based on query type
    return [] if is_select_query else None

def check_button_clicks(game_id):
    """
    Diagnostic function to check if there are button clicks for a specific game.
    Args:
        game_id (int): Game ID to check
    Returns:
        list: List of button clicks or empty list if none found
    """
    query = "SELECT COUNT(*) FROM button_clicks WHERE game_id = %s"
    params = (game_id,)
    try:
        result = execute_query(query, params)
        count = result[0][0] if result and result[0] else 0
        logger.info(f"Found {count} button clicks for game {game_id}")
        
        if count > 0:
            # Get a sample of clicks
            sample_query = """
                SELECT user_id, timer_value, click_time
                FROM button_clicks 
                WHERE game_id = %s 
                ORDER BY click_time DESC LIMIT 5
            """
            sample = execute_query(sample_query, params)
            for click in sample:
                logger.info(f"Sample click: user={click[0]}, timer={click[1]}, time={click[2]}")
        
        return count
    except Exception as e:
        logger.error(f"Error checking button clicks for game {game_id}: {e}")
        logger.error(traceback.format_exc())
        return 0

# Function to close and disconnect all database connections, cursors, and pools
def close_disconnect_database():
    """
    Closes and disconnects all database connections, cursors, and resets pool references.
    Handles each connection component separately to ensure proper cleanup.
    """
    global db_pool, db_pool_timer, db, cursor, timer_db, cursor_tb

    try:
        # Close the cursor if it exists
        if cursor:
            try:
                cursor.close()
                logger.info("Cursor closed successfully.")
            except mysql.connector.Error as e:
                logger.error(f"Error closing cursor: {e}")

        # Close the database connection if it exists
        if db:
            try:
                db.close()
                logger.info("Database connection closed successfully.")
            except mysql.connector.Error as e:
                logger.error(f"Error closing database connection: {e}")

        # Close the timer cursor if it exists
        if cursor_tb:
            try:
                cursor_tb.close()
                logger.info("Timer cursor closed successfully.")
            except mysql.connector.Error as e:
                logger.error(f"Error closing timer cursor: {e}")

        # Close the timer database connection if it exists
        if timer_db:
            try:
                timer_db.close()
                logger.info("Timer database connection closed successfully.")
            except mysql.connector.Error as e:
                logger.error(f"Error closing timer database connection: {e}")
                
        # For connection pools, we don't close them directly since MySQLConnectionPool
        # doesn't have a close() method. Instead, we just reset the references.
        if db_pool:
            logger.info("Resetting main connection pool reference.")
            db_pool = None

        if db_pool_timer:
            logger.info("Resetting timer connection pool reference.")
            db_pool_timer = None

    except Exception as e:
        logger.error(f"Error during database cleanup: {e}")
        logger.error(traceback.format_exc())
    finally:
        # Reset all global references
        db = None
        cursor = None
        timer_db = None
        cursor_tb = None
        db_pool = None
        db_pool_timer = None

# # Global variables for game sessions as a dictionary
game_sessions_as_dict = {}


async def game_sessions_dict(game_sessions_arg=None):
    """Convert game sessions into a dictionary format with intelligent caching"""
    global _sessions_dict_cache, _last_dict_update, _sessions_dict_lock
    async with _sessions_dict_lock:
        now = datetime.datetime.now(timezone.utc)
        # Return cached result if fresh (within 5 seconds)
        if (_sessions_dict_cache and _last_dict_update and 
            (now - _last_dict_update).total_seconds() < 5):
            return _sessions_dict_cache.copy()
        output = {}
        sessions_to_process = game_sessions_arg or update_local_game_sessions()
        # Handle case where sessions_to_process is boolean or None
        if not isinstance(sessions_to_process, list):
            logger.warning(f"Invalid sessions_to_process type: {type(sessions_to_process)}")
            return output
        if not sessions_to_process:
            logger.warning("No game sessions to process")
            return output
        for game in sessions_to_process:
            if game[6] is not None:  # Skip ended games
                continue
            try:
                game_id = str(game[0])
                formatted_output = {
                    "game_id": int(game[0]),
                    "admin_role_id": int(game[1]) if game[1] else 0,
                    "guild_id": int(game[2]),
                    "button_channel_id": int(game[3]),
                    "game_chat_channel_id": int(game[4]),
                    "start_time": game[5],
                    "end_time": game[6],
                    "timer_duration": int(game[7]),
                    "cooldown_duration": int(game[8])
                }
                output[game_id] = formatted_output
                output[int(game_id)] = formatted_output
            except (ValueError, TypeError) as e:
                logger.error(f'Error formatting game session {game[0]}: {e}')
                continue
        # Update cache
        _sessions_dict_cache = output.copy()
        _last_dict_update = now
        return output

def update_local_game_sessions():
    """
    Updates the local cache of game sessions from the database.
    Only returns active (non-ended) sessions.
    Returns:
        list: Updated list of game sessions
    """
    #logger.info('Updating local game sessions')
    query = """
        SELECT 
            id,
            admin_role_id,
            guild_id,
            button_channel_id,
            game_chat_channel_id,
            start_time,
            end_time,
            timer_duration,
            cooldown_duration
        FROM game_sessions
        WHERE end_time IS NULL
        ORDER BY start_time DESC
    """
    try:
        result = execute_query(query)
        global game_sessions
        if not result:
            logger.warning('No active game sessions found in database')
            game_sessions = []
            return []
        # Handle case where result is boolean instead of a list
        if isinstance(result, bool):
            logger.warning('Unexpected boolean result when querying game sessions')
            game_sessions = []
            return []
        game_sessions = result
        #logger.info(f'Game sessions updated: {len(game_sessions)}')
        return game_sessions
    except Exception as e:
        logger.error(f'Error updating game sessions: {e}')
        logger.error(traceback.format_exc())
        return []
    
async def get_game_session_by_id(game_id):
    """Get a game session directly from database by ID, including ended games."""
    try:
        # Query the database directly, including ended games
        query = """
            SELECT 
                id,
                admin_role_id,
                guild_id,
                button_channel_id,
                game_chat_channel_id,
                start_time,
                end_time,
                timer_duration,
                cooldown_duration
            FROM game_sessions
            WHERE id = %s
        """
        params = (game_id,)
        result = execute_query(query, params)
        
        if not result or len(result) == 0:
            logger.warning(f"Game with ID {game_id} not found in database")
            return None
            
        # Format results into dictionary
        game = result[0]
        formatted_output = {
            "game_id": int(game[0]),
            "admin_role_id": int(game[1]) if game[1] else 0,
            "guild_id": int(game[2]),
            "button_channel_id": int(game[3]),
            "game_chat_channel_id": int(game[4]),
            "start_time": game[5],
            "end_time": game[6],
            "timer_duration": int(game[7]),
            "cooldown_duration": int(game[8])
        }
        
        return formatted_output
        
    except Exception as e:
        logger.error(f'Error in get_game_session_by_id_direct for {game_id}: {e}')
        logger.error(traceback.format_exc())
        return None

async def get_game_session_by_guild_id(guild_id):
    """Get game session by guild ID with improved caching."""
    # Check if we have a cached dictionary first
    global _sessions_dict_cache
    if _sessions_dict_cache:
        # Look for a session with this guild ID
        for game_id, session in _sessions_dict_cache.items():
            if isinstance(session, dict) and session.get('guild_id') == guild_id:
                return session
    
    # If not in cache, get all game sessions at once
    global game_sessions
    if not game_sessions:
        game_sessions = update_local_game_sessions()
    
    # Look for the guild ID in the sessions
    for game in game_sessions:
        if game[2] == guild_id:  # guild_id is at index 2
            # Get complete game session data
            return await get_game_session_by_id(game[0])
    
    return None

def get_game_session_count():
    global game_sessions
    return len(game_sessions)

def create_tables():
    global db, cursor
    if not cursor: db, cursor = get_current_new_cursor()
        
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS game_sessions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            admin_role_id BIGINT,
            guild_id BIGINT,
            button_channel_id BIGINT,
            game_chat_channel_id BIGINT,
            start_time DATETIME,
            end_time DATETIME,
            timer_duration INT,
            cooldown_duration INT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            user_name VARCHAR(255),
            cooldown_expiration DATETIME,
            color_rank VARCHAR(255),
            total_clicks INT DEFAULT 0,
            lowest_click_time INT,
            last_click_time DATETIME,
            game_session INT,
            FOREIGN KEY (game_session) REFERENCES game_sessions(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS button_clicks (
            id INT AUTO_INCREMENT PRIMARY KEY,
            game_id INT,
            user_id BIGINT,
            click_time DATETIME,
            timer_value INT,
            FOREIGN KEY (game_id) REFERENCES game_sessions(id),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS guild_icons (
            guild_id BIGINT PRIMARY KEY,
            icon_emoji VARCHAR(32),
            last_updated DATETIME,
            INDEX idx_guild_id (guild_id)
        )
    ''')

    db.commit()
    
# Function to create a game session in the database
def create_game_session(admin_role_id, guild_id, button_channel_id, game_chat_channel_id, start_time, timer_duration, cooldown_duration):
    global cursor, lock
    query = """
        INSERT INTO game_sessions (admin_role_id, guild_id, button_channel_id, game_chat_channel_id, start_time, timer_duration, cooldown_duration)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    params = (admin_role_id, guild_id, button_channel_id, game_chat_channel_id, start_time, timer_duration, cooldown_duration)
    game_session_id = execute_query(query, params, commit=True)
    if not cursor:
        db, cursor = get_current_new_cursor()
    game_session_id = cursor.lastrowid

    # If there is no game_session_id, retry until we get one or timeout
    retry_count = 0
    while not game_session_id and retry_count < 5:
        time.sleep(1)  # Wait a bit before retrying
        game_session_id = cursor.lastrowid
        retry_count += 1

    return game_session_id

# Function to get the game channels from the database
def get_game_channels_from_db():
    """
    Retrieves game channel IDs from the database.
    
    Returns:
        list: List of channel IDs or None if query fails
    """
    try:
        # query = """
        #     SELECT button_channel_id, game_chat_channel_id 
        #     FROM game_sessions
        # """
        query = """
            SELECT bc.*
            FROM button_clicks bc
            JOIN game_sessions gs ON bc.game_id = gs.id
            WHERE gs.end_time IS NULL OR gs.end_time > NOW()  -- Active game sessions
            AND bc.click_time >= (
                SELECT MAX(click_time) - INTERVAL (gs.timer_duration) SECOND
                FROM button_clicks
                WHERE game_id = bc.game_id
            );
        """
        channels = execute_query(query)
        print(f'Channels: {channels}')
        if channels:
            return list(channels[0])
        return None
    except Exception as e:
        logger.error(f'Error getting game channels from db: {e}')
        logger.error(traceback.format_exc())
        return None

# Function to get all game channels
def get_all_game_channels():
    global GAME_CHANNELS
    if GAME_CHANNELS:
        print(f'Returning game channels from memory {GAME_CHANNELS}')
        return GAME_CHANNELS
    GAME_CHANNELS = get_game_channels_from_db()
    if not GAME_CHANNELS:
        GAME_CHANNELS = []
    return GAME_CHANNELS

# Function to fix users with missing names in the database
def get_missing_users():
    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Query to fetch missing user_id values
        query = """
            SELECT bc.user_id
            FROM button_clicks bc
            LEFT JOIN users u ON bc.user_id = u.user_id
            WHERE u.user_id IS NULL
            GROUP BY bc.user_id
        """
        cursor.execute(query)
        missing_users = cursor.fetchall()
        missing_user_ids = [user_id for user_id, in missing_users]
        return missing_user_ids
    except mysql.connector.Error as error:
        logger.error(f"Error getting missing users: {error}")
        return []

    finally:
        if cursor: cursor.close()
        if connection: connection.close()
            

# Function to fix missing users in the database
# Specifically when a user is missing from the users table, but has click data in the button_clicks table
# This function will fetch the latest click data for the user, get the total clicks, and insert the user data into the users table
# Then correct the user data if the user already exists in the users table
async def fix_missing_users(bot):
    global lock
    try:
        missing_user_ids = get_missing_users()
        if not missing_user_ids:
            logger.info("No missing users found.")
            return

        logger.info(f"Found {len(missing_user_ids)} missing users. Fixing...")

        for user_id in missing_user_ids:
            try:
                # Get the latest click data for the user
                query = '''
                    SELECT bc.user_id, bc.click_time, bc.timer_value, bc.game_id
                    FROM button_clicks bc
                    WHERE bc.user_id = %s
                    ORDER BY bc.click_time DESC
                    LIMIT 1
                '''
                params = (user_id,)
                
                result = execute_query(query, params)
                if not result: logger.warning(f"No click data found for user {user_id}. Skipping..."); continue

                _, latest_click_time, lowest_click_time, game_id = result[0]

                # Get the total clicks for the user
                query = '''
                    SELECT COUNT(*) AS total_clicks
                    FROM button_clicks
                    WHERE user_id = %s
                '''
                
                params = (user_id,)
                result = execute_query(query, params)
                total_clicks = result[0][0] if result else 0

                # Get the Discord user data
                user = await bot.fetch_user(user_id)
                if not user: logger.warning(f"Discord user {user_id} not found. Skipping..."); continue

                user_name = user.name
                color_rank = get_color_name(lowest_click_time)

                # Insert the user data into the users table
                query = '''
                    INSERT INTO users (user_id, user_name, cooldown_expiration, color_rank, total_clicks, lowest_click_time, latest_click_time, game_id)
                    VALUES (%s, %s, NULL, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        user_name = VALUES(user_name),
                        color_rank = VALUES(color_rank),
                        total_clicks = VALUES(total_clicks),
                        lowest_click_time = LEAST(lowest_click_time, VALUES(lowest_click_time)),
                        latest_click_time = GREATEST(latest_click_time, VALUES(latest_click_time)),
                        game_id = VALUES(game_id)
                '''
                params = (user_id, user_name, color_rank, total_clicks, lowest_click_time, latest_click_time, game_id)
                success = execute_query(query, params, commit=True)

                if success: logger.info(f"Fixed missing user {user_id} ({user_name})")
                else: logger.error(f"Failed to fix missing user {user_id} ({user_name})")

            except Exception as e:
                logger.error(f"Error fixing missing user {user_id}: {e}")
                traceback.print_exc()
                
        logger.info("Finished fixing missing users.")

    except Exception as e:
        logger.error(f"Error fixing missing users: {e}")
        traceback.print_exc()

def fix_ended_game_sessions():
    """
    Checks for game sessions that should have ended based on timer duration 
    and last click time, but don't have an end_time set, and ends them.
    """
    try:
        query = """
            SELECT gs.id, MAX(bc.click_time), gs.timer_duration
            FROM game_sessions gs
            INNER JOIN button_clicks bc ON gs.id = bc.game_id
            WHERE gs.end_time IS NULL  -- Only check sessions that haven't ended
            GROUP BY gs.id, gs.timer_duration
        """
        results = execute_query(query)

        if results:
            logger.info(f"Checking {len(results)} game sessions for potential end times...")

            for game_id, last_click_time, timer_duration in results:
                if last_click_time and timer_duration:  # Ensure values exist
                    last_click_time_utc = last_click_time.replace(tzinfo=timezone.utc)
                    end_time_calculated = last_click_time_utc + datetime.timedelta(seconds=timer_duration)
                    now_utc = datetime.datetime.now(timezone.utc)

                    if end_time_calculated <= now_utc:  # Should have ended
                        logger.info(f"Game session {game_id} should have ended. Ending...")
                        if end_game_session(game_id):  # End the game session
                            logger.info(f"Game session {game_id} ended successfully.")
                        else:
                            logger.error(f"Failed to end game session {game_id}.")
                    # else: # Uncomment for debugging
                    #     logger.debug(f"Game session {game_id} is still active. Calculated end: {end_time_calculated}, Now: {now_utc}")
        else:
            logger.info("No game sessions to check for end times.")

    except Exception as e:
        logger.error(f"Error checking/fixing ended game sessions: {e}")
        logger.error(traceback.format_exc())

def end_game_session(game_id):
    """
    Ends a game session by setting the end_time.  Handles potential race conditions.

    Args:
        game_id (int): The ID of the game session to end.

    Returns:
        bool: True if the game session was successfully ended, False otherwise.
    """
    try:
        # Get the current end_time (or NULL if it doesn't exist)
        check_query = "SELECT end_time FROM game_sessions WHERE id = %s"
        result = execute_query(check_query, (game_id,))

        if result and result is not None and result != [(None,)]:
            logger.info(f"Game session {game_id} already ended at {result}.")
            return True # Already ended, so consider it a success.

        # If it hasn't ended, update it.
        update_query = """
            UPDATE game_sessions
            SET end_time = CASE 
                            WHEN end_time IS NULL THEN UTC_TIMESTAMP()  -- Only set if it's currently NULL
                            ELSE end_time  -- Don't overwrite an existing end_time
                        END
            WHERE id = %s
        """
        rows_affected = execute_query(update_query, (game_id,), commit=True)

        if rows_affected > 0: # Check if a row was actually updated
            logger.info(f"Game session {game_id} ended successfully.")
            update_local_game_sessions()  # Refresh game session cache
            return True
        else:
            logger.warning(f"Failed to end game session {game_id} (may have already ended or not found).")
            return False

    except Exception as e:
        logger.error(f"Error ending game session {game_id}: {e}")
        logger.error(traceback.format_exc())
        return False

# Initialize database on first run
first_run = True
print("Starting database initialization...")

if first_run:
    print("First run detected, setting up pools...")
    if setup_pool():
        try:
            print("Pool setup successful, proceeding with initialization...")
            first_run = False
            print("Getting database cursor...")
            db, cursor = get_current_new_cursor()
            print("Creating tables...")
            create_tables()
            print("Checking for missing users...")
            missing_users = get_missing_users()
            print(f"Found {len(missing_users) if missing_users else 0} missing users")
            print("Checking for ended game sessions...")
            fix_ended_game_sessions()
            print("Getting game channels...")
            GAME_CHANNELS = get_all_game_channels()
            print("Updating game sessions...")
            game_sessions = update_local_game_sessions()
            print("Database initialization completed successfully")
        except Exception as e:
            print(f'Database initialization failed: {e}')
            print(traceback.format_exc())
            sys.exit(1)
    else:
        print("Failed to set up database pools")
        sys.exit(1)

print("Database setup complete")

def insert_first_click(game_id, user_id, user_name, timer_value):
    """
    Insert the first button click for a game session.
    
    Args:
        game_id (int): The ID of the game session
        user_id (int): The ID of the user clicking the button
        user_name (str): The name of the user clicking the button
        timer_value (float): The current timer value when clicked
        
    Returns:
        dict: The inserted click data or None if failed
    """
    try:
        # First ensure the user exists in the users table
        user_query = """
            INSERT INTO users (user_id, user_name) 
            VALUES (%s, %s) 
            ON DUPLICATE KEY UPDATE user_name = VALUES(user_name)
        """
        execute_query(user_query, (user_id, user_name), commit=True)
        
        # Then insert the first click
        click_query = """
            INSERT INTO button_clicks 
            (game_id, user_id, click_time, timer_value) 
            VALUES (%s, %s, UTC_TIMESTAMP(), %s)
        """
        execute_query(click_query, (game_id, user_id, timer_value), commit=True)
        
        # Return the inserted data
        get_click_query = """
            SELECT button_clicks.click_time, users.user_name, button_clicks.timer_value,
                1 as total_clicks,
                1 as total_players
            FROM button_clicks
            INNER JOIN users ON button_clicks.user_id = users.user_id
            WHERE button_clicks.game_id = %s
            ORDER BY button_clicks.id DESC
            LIMIT 1
        """
        result = execute_query(get_click_query, (game_id,))
        
        if result and result[0]:
            click_time, username, timer_val, total_clicks, total_players = result[0]
            return {
                'latest_click_time': click_time,
                'latest_player_name': username,
                'last_timer_value': timer_val,
                'total_clicks': total_clicks,
                'total_players': total_players,
                'last_update_time': click_time
            }
            
        return None
        
    except Exception as e:
        logger.error(f"Error inserting first click: {e}")
        logger.error(traceback.format_exc())
        return None
    
def get_or_create_guild_icon(guild_id: int) -> str:
    """
    Get existing guild icon or create new one if none exists.
    
    Args:
        guild_id (int): Discord guild ID
        
    Returns:
        str: Emoji icon for the guild
    """
    try:
        query = "SELECT icon_emoji FROM guild_icons WHERE guild_id = %s"
        result = execute_query(query, (guild_id,))
        
        if result and result[0][0]:
            return result[0][0]
            
        # No icon exists, create new one
        import random
        query = "SELECT icon_emoji FROM guild_icons"
        used_icons = execute_query(query)
        used_icons = [icon[0] for icon in used_icons] if used_icons else []
        
        # Get available icons
        available_icons = [icon for icon in GUILD_EMOJIS if icon not in used_icons]
        if not available_icons:  # If all icons used, allow reuse
            available_icons = GUILD_EMOJIS
            
        new_icon = random.choice(available_icons)
        
        # Insert new icon
        query = """
            INSERT INTO guild_icons (guild_id, icon_emoji, last_updated)
            VALUES (%s, %s, UTC_TIMESTAMP())
            ON DUPLICATE KEY UPDATE 
                icon_emoji = VALUES(icon_emoji),
                last_updated = VALUES(last_updated)
        """
        execute_query(query, (guild_id, new_icon), commit=True)
        return new_icon
    except Exception as e:
        logger.error(f"Error in get_or_create_guild_icon: {e}")
        logger.error(traceback.format_exc())
        return "🎮"  # Default fallback icon

def update_guild_icon(guild_id: int, new_icon: str) -> bool:
    """
    Update a guild's icon emoji.
    
    Args:
        guild_id (int): Discord guild ID
        new_icon (str): New emoji to use
        
    Returns:
        bool: True if update successful, False otherwise
    """
    try:
        if new_icon not in GUILD_EMOJIS:
            return False
            
        query = """
            UPDATE guild_icons 
            SET icon_emoji = %s, last_updated = UTC_TIMESTAMP()
            WHERE guild_id = %s
        """
        execute_query(query, (new_icon, guild_id), commit=True)
        return True
    except Exception as e:
        logger.error(f"Error in update_guild_icon: {e}")
        logger.error(traceback.format_exc())
        return False
def update_or_create_game_session(admin_role_id, guild_id, button_channel_id, game_chat_channel_id, start_time, timer_duration, cooldown_duration, force_create=False):
    """
    Updates existing game session or creates new one for a guild.
    If existing session's timer has expired, it will be updated with new values.
    """
    try:
        # Check for existing game session with expired timer
        query = """
            SELECT gs.id, MAX(bc.click_time), MAX(bc.timer_value)
            FROM game_sessions gs
            LEFT JOIN button_clicks bc ON gs.id = bc.game_id
            WHERE gs.guild_id = %s
            GROUP BY gs.id
        """
        result = execute_query(query, (guild_id,))
        
        # force_create
        if force_create:
            return create_game_session(admin_role_id, guild_id, button_channel_id, game_chat_channel_id, 
                                       start_time, timer_duration, cooldown_duration)

        if result and result[0]:
            game_id, last_click, last_timer = result[0]
            if last_click and last_timer:
                # Calculate if timer has expired
                elapsed = (datetime.datetime.now(timezone.utc) - last_click.replace(tzinfo=timezone.utc)).total_seconds()
                if elapsed > last_timer:
                    # Update existing session
                    update_query = """
                        UPDATE game_sessions 
                        SET admin_role_id = %s,
                            button_channel_id = %s,
                            game_chat_channel_id = %s,
                            start_time = %s,
                            end_time = NULL,
                            timer_duration = %s,
                            cooldown_duration = %s
                        WHERE id = %s
                    """
                    execute_query(update_query, (admin_role_id, button_channel_id, game_chat_channel_id, 
                                              start_time, timer_duration, cooldown_duration, game_id), commit=True)
                    update_local_game_sessions()
                    return game_id
            
        # If no session exists or timer hasn't expired, create new session
        return create_game_session(admin_role_id, guild_id, button_channel_id, game_chat_channel_id, 
                                 start_time, timer_duration, cooldown_duration)
                                 
    except Exception as e:
        logger.error(f"Error in update_or_create_game_session: {e}")
        logger.error(traceback.format_exc())
        return None
    
async def game_sessions_dict(game_sessions_arg=None):
    """Convert game sessions into a dictionary format with intelligent caching"""
    global _sessions_dict_cache, _last_dict_update, _sessions_dict_lock
    async with _sessions_dict_lock:
        now = datetime.datetime.now(timezone.utc)
        # Return cached result if fresh (within 5 seconds)
        if (_sessions_dict_cache and _last_dict_update and 
            (now - _last_dict_update).total_seconds() < 5):
            return _sessions_dict_cache.copy()
        output = {}
        sessions_to_process = game_sessions_arg or update_local_game_sessions()
        
        # Handle case where sessions_to_process is boolean or None
        if not isinstance(sessions_to_process, list):
            logger.warning(f"Invalid sessions_to_process type: {type(sessions_to_process)}")
            return output
            
        if not sessions_to_process:
            logger.warning("No game sessions to process")
            return output
            
        for game in sessions_to_process:
            if game[6] is not None:  # Skip ended games
                continue
            try:
                game_id = str(game[0])
                formatted_output = {
                    "game_id": int(game[0]),
                    "admin_role_id": int(game[1]) if game[1] else 0,
                    "guild_id": int(game[2]),
                    "button_channel_id": int(game[3]),
                    "game_chat_channel_id": int(game[4]),
                    "start_time": game[5],
                    "end_time": game[6],
                    "timer_duration": int(game[7]),
                    "cooldown_duration": int(game[8])
                }
                output[game_id] = formatted_output
                output[int(game_id)] = formatted_output
            except (ValueError, TypeError) as e:
                logger.error(f'Error formatting game session {game[0]}: {e}')
                continue
        # Update cache
        _sessions_dict_cache = output.copy()
        _last_dict_update = now
        return output
    
print('Database setup complete')