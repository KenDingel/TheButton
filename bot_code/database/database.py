# Database.py
import mysql.connector
from mysql.connector.pooling import MySQLConnectionPool
import traceback
import time
import datetime
from datetime import timezone

from utils.utils import config, logger, lock, get_color_name

db = None
cursor = None
timer_db = None
cursor_tb = None

# Global connection pools
db_pool = None
db_pool_timer = None

# Constants for pool configuration
MAIN_POOL_SIZE = 5
TIMER_POOL_SIZE = 1
CONNECTION_TIMEOUT = 120

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
    Sets up MySQL connection pools for main operations and timer operations.
    Creates pools if they don't exist or have been closed.
    
    Args:
        config (dict): Configuration dictionary containing database credentials
        
    Returns:
        bool: True if pools were successfully set up, False otherwise
        
    Raises:
        mysql.connector.Error: If there's an error creating the connection pools
    """
    global db_pool, db_pool_timer
    
    # If both pools exist, no need to recreate
    if db_pool is not None and db_pool_timer is not None:
        try:
            # Test connections from both pools
            with db_pool.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
            with db_pool_timer.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
            return True
        except mysql.connector.Error:
            # If test fails, pools might be stale - proceed to recreate them
            logger.warning("Existing pools failed connection test - recreating...")
            db_pool = None
            db_pool_timer = None

    try:
        # Common pool configuration
        pool_config = {
            'host': config['sql_host'],
            'user': config['sql_user'],
            'password': config['sql_password'],
            'database': config['sql_database'],
            'port': config['sql_port'],
            'pool_reset_session': True,
            'connect_timeout': CONNECTION_TIMEOUT
        }

        # Create main pool if needed
        if db_pool is None:
            db_pool = MySQLConnectionPool(
                pool_name="button_pool",
                pool_size=MAIN_POOL_SIZE,
                **pool_config
            )
            logger.info("Main connection pool created successfully")

        # Create timer pool if needed
        if db_pool_timer is None:
            db_pool_timer = MySQLConnectionPool(
                pool_name="button_pool_timer",
                pool_size=TIMER_POOL_SIZE,
                **pool_config
            )
            logger.info("Timer connection pool created successfully")

        return True

    except mysql.connector.Error as error:
        logger.error(f"Error setting up connection pools: {error}")
        logger.error(traceback.format_exc())
        # Clean up if partial setup occurred
        if db_pool is not None:
            db_pool = None
        if db_pool_timer is not None:
            db_pool_timer = None
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
        
    Raises:
        mysql.connector.Error: If database error occurs after all retries
    """
    global db_pool, db_pool_timer
    
    # Ensure pools are set up
    if db_pool is None or db_pool_timer is None:
        if not setup_pool():
            logger.error("Failed to setup database pools")
            return None
            
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
                
            # For SELECT queries, fetch results
            result = cursor.fetchall() if cursor.description else True

            logger.info(f"Query executed successfully: {query}, Params: {params}")
            logger.info(f"Result: {result}")
            
            if cursor:
                cursor.close()
            if connection:
                connection.close()
            close_disconnect_database()

            return result

        except mysql.connector.Error as error:
            last_error = error
            logger.warning(
                f"Database error (attempt {attempt + 1}/{retry_attempts}): {error}\n"
                f"Query: {query}, Params: {params}"
            )
            if attempt < retry_attempts - 1:  # Don't sleep on last attempt
                time.sleep(min(2 ** attempt, 10))  # Exponential backoff
                
        except Exception as e:
            logger.error(f"Unexpected error executing query: {e}")
            logger.error(traceback.format_exc())
            raise
        finally:
            try:
                if cursor:
                    cursor.close()
                if connection:
                    connection.close()
            except Exception as e:
                pass

    # If we get here, all attempts failed
    logger.error(
        f"Query failed after {retry_attempts} attempts. Last error: {last_error}\n"
        f"Query: {query}, Params: {params}"
    )
    raise last_error

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
        
# Function to execute a query on the database
# This function will attempt to execute the query multiple times if it fails
# It will return the result of the query if successful, or None if it fails
# Accepts the query, parameters, and whether to commit the query
# def execute_query(query, params=None, is_timer=False, retry_attempts=3, commit=False):
#     global db, cursor
    
#     if not cursor: db, cursor = get_current_new_cursor()
#     #logger.info(f'Executing query: {query}, Params: {params}')
#     attempt = 0
#     try:
#         while attempt < retry_attempts:
#             if not is_timer:
#                 try:
#                     if not db_pool or db_pool is None: setup_pool()
#                     with db_pool.get_connection() as connection:
#                         with connection.cursor() as cursor:
#                             cursor.execute(query, params)
#                             logger.info(f'Query executed successfully')
#                             if commit:
#                                 connection.commit()
#                                 return True
#                             return cursor.fetchall()
#                 except mysql.connector.Error as e:
#                     logger.error(f'Error executing query: Exception: {e}, Query: {query}, Params: {params}')
#                     tb = traceback.format_exc()
#                     logger.error(f'Error executing query 1: {e}, {tb}')
#                     attempt += 1
#             else:
#                 try:
#                     if not db_pool_timer or db_pool_timer is None: setup_pool()
#                     with db_pool_timer.get_connection() as connection:
#                         with connection.cursor() as cursor:
#                             cursor.execute(query, params)
#                             logger.info(f'Query executed successfully')
#                             if commit: connection.commit(); return True
#                             return cursor.fetchall()
#                 except mysql.connector.Error as e:
#                     logger.error(f'Error executing query: Exception: {e}, Query: {query}, Params: {params}')
#                     tb = traceback.format_exc()
#                     logger.error(f'Error executing query: {e}, {tb}')
#                     attempt += 1
#         logger.error(f'Failed to execute query after {retry_attempts} attempts, query: {query}')
#         return None
#     except Exception as e:
#         logger.error(f'Error executing query: Exception: {e}, Query: {query}, Params: {params}')
#         tb = traceback.format_exc()
#         logger.error(f'Error executing query 2: {e}, {tb}')
#         return None

# # Global variables for the game sessions, game sessions as a dictionary, and game channels
game_sessions = []
game_sessions_as_dict = {}
GAME_CHANNELS = None

# Function to update the local game sessions list
def update_local_game_sessions():
    """
    Updates the local cache of game sessions from the database.
    Only returns the latest session per guild based on start_time.
    
    Returns:
        list: Updated list of game sessions
    """
    logger.info('Updating local game sessions')
    query = """
        WITH LatestSessions AS (
            SELECT 
                id,
                admin_role_id,
                guild_id,
                button_channel_id,
                game_chat_channel_id,
                start_time,
                end_time,
                timer_duration,
                cooldown_duration,
                ROW_NUMBER() OVER (PARTITION BY guild_id ORDER BY start_time DESC) as rn
            FROM game_sessions
        )
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
        FROM LatestSessions
        WHERE rn = 1
        ORDER BY start_time DESC
    """
    try:
        result = execute_query(query)
        global game_sessions
        game_sessions = result
        logger.info(f'Game sessions updated: {len(game_sessions)} sessions')
        return game_sessions
    except Exception as e:
        logger.error(f'Error updating game sessions: {e}')
        logger.error(traceback.format_exc())
        return []
    
def game_sessions_dict(game_sessions_arg=None):
    global game_sessions, game_sessions_as_dict
    output = {}
    if game_sessions_arg: game_sessions = game_sessions_arg
    
    logger.info(f'Creating game sessions dict, lengths - game_sessions: {len(game_sessions)}, game_sessions_as_dict: {len(game_sessions_as_dict.keys())}')
    for game in game_sessions:
        formatted_output = {
            "game_id": int(game[0]),
            "admin_role_id": int(game[1]),
            "guild_id": int(game[2]),
            "button_channel_id": int(game[3]),
            "game_chat_channel_id": int(game[4]),
            "start_time": game[5],
            "end_time": game[6],
            "timer_duration": int(game[7]),
            "cooldown_duration": int(game[8])
        }
        output[int(game[0])] = formatted_output
    game_sessions_as_dict = output
    logger.debug(f"Game sessions dict keys: {list(output.keys())}")
    return output

def get_game_session_by_id(game_id):
    global game_sessions
    if not game_sessions:
        game_sessions = update_local_game_sessions()
    
    for game in game_sessions:
        if game[0] == game_id:
            formatted_output = {
                "game_id": game[0],
                "admin_role_id": game[1],
                "guild_id": game[2],
                "button_channel_id": game[3],
                "game_chat_channel_id": game[4],
                "start_time": game[5],
                "end_time": game[6],
                "timer_duration": game[7],
                "cooldown_duration": game[8]
            }
            return formatted_output
    return None

def get_game_session_by_guild_id(guild_id):
    global game_sessions
    for game in game_sessions:
        if game[2] == guild_id: return get_game_session_by_id(game[0])
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

    db.commit()
    
# Function to create a game session in the database
def create_game_session(admin_role_id, guild_id, button_channel_id, game_chat_channel_id, start_time, timer_duration, cooldown_duration):
    global cursor, lock
    query = """
        INSERT INTO game_sessions (admin_role_id, guild_id, button_channel_id, game_chat_channel_id, start_time, timer_duration, cooldown_duration)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    params = (admin_role_id, guild_id, button_channel_id, game_chat_channel_id, start_time, timer_duration, cooldown_duration)
    with lock:
        game_session_id = execute_query(query, params, commit=True)
    if not cursor:
        db, cursor = get_current_new_cursor()
    game_session_id = cursor.lastrowid
    return game_session_id

# Function to get the game channels from the database
def get_game_channels_from_db():
    """
    Retrieves game channel IDs from the database.
    
    Returns:
        list: List of channel IDs or None if query fails
    """
    try:
        query = """
            SELECT button_channel_id, game_chat_channel_id 
            FROM game_sessions
        """
        channels = execute_query(query)
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

# Setup the connection pools
if setup_pool(): logger.info('Connection pools set up successfully')
else: logger.error('Error setting up connection pools')

# Initialize variables, get database connection and cursor, create tables, and update local game sessions
GAME_CHANNELS = get_all_game_channels()
db, cursor = get_current_new_cursor()
create_tables()
game_sessions = update_local_game_sessions()

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
                with lock: success = execute_query(query, params, commit=True)

                if success: logger.info(f"Fixed missing user {user_id} ({user_name})")
                else: logger.error(f"Failed to fix missing user {user_id} ({user_name})")

            except Exception as e:
                logger.error(f"Error fixing missing user {user_id}: {e}")
                traceback.print_exc()
                
        logger.info("Finished fixing missing users.")

    except Exception as e:
        logger.error(f"Error fixing missing users: {e}")
        traceback.print_exc()

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
    
# Fix missing users
missing_users = get_missing_users()
logger.info(f"Missing users: {missing_users}")