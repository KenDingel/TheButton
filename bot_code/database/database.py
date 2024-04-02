# Database.py
import mysql.connector
from mysql.connector.pooling import MySQLConnectionPool
import traceback

from utils.utils import config, logger, lock, get_color_name

db_pool = None
db_pool_timer = None

db = None
cursor = None
timer_db = None
cursor_tb = None

# Functions to get database connections
def get_db_connection(): return db_pool.get_connection()
def get_db_connection_timer(): return db_pool_timer.get_connection()

# Function to get the current database connection and cursor
def get_current_new_cursor():
    global db, cursor
    if not db:
        global cursor
        db = get_db_connection()
        cursor = db.cursor()
        return db, cursor
    if not cursor:
        cursor = db.cursor()
    return db, cursor

# Function to get the current database connection and cursor for the timer pool
def setup_pool(config=config):
    global db_pool, db_pool_timer
    try:
        # Create the main connection pool
        if not db_pool and db_pool is None:
            db_pool = MySQLConnectionPool(
                pool_name="button_pool",
                pool_size=5,
                host=config['sql_host'],
                user=config['sql_user'],
                password=config['sql_password'],
                database=config['sql_database'],
                port=config['sql_port'],
                pool_reset_session=True,
                connect_timeout=120
            )

        # Create the timer connection pool
        if not db_pool_timer and db_pool_timer is None:
            db_pool_timer = MySQLConnectionPool(
                pool_name="button_pool_timer",
                pool_size=1,
                host=config['sql_host'],
                user=config['sql_user'],
                password=config['sql_password'],
                database=config['sql_database'],
                port=config['sql_port']
            )

        logger.info("Connection pools set up successfully.")
        return True

    except mysql.connector.Error as error:
        logger.error(f"Error setting up connection pools: {error}")
        return False

# Function to close and disconnect all database connections, cursors, and pools
def close_disconnect_database():
    global db_pool, db_pool_timer, db, cursor, timer_db, cursor_tb

    try:
        # Close the cursor if it exists
        if cursor:
            try:
                cursor.close()
                logger.info("Cursor closed successfully.")
            except mysql.connector.Error as e: logger.error(f"Error closing cursor: {e}")

        # Close the database connection if it exists
        if db:
            try:
                db.close()
                logger.info("Database connection closed successfully.")
            except mysql.connector.Error as e: logger.error(f"Error closing database connection: {e}")

        # Close the cursor if it exists
        if cursor_tb:
            try:
                cursor_tb.close()
                logger.info("Cursor closed successfully.")
            except mysql.connector.Error as e: logger.error(f"Error closing cursor: {e}")

        # Close the database connection if it exists
        if timer_db:
            try:
                timer_db.close()
                logger.info("Database connection closed successfully.")
            except mysql.connector.Error as e: logger.error(f"Error closing database connection: {e}")
                
        # Close the connection pools
        if db_pool:
            try:
                db_pool.pool_clear_pool_connections()
                db_pool.pool_reset_session()
                db_pool.close()
                db_pool = None
                logger.info("Main connection pool closed successfully.")
            except mysql.connector.Error as e: logger.error(f"Error closing main connection pool: {e}")

        if db_pool_timer:
            try:
                db_pool_timer.pool_clear_pool_connections()
                db_pool_timer.pool_reset_session()
                db_pool_timer.close()
                db_pool_timer = None
                logger.info("Timer connection pool closed successfully.")
            except mysql.connector.Error as e: logger.error(f"Error closing timer connection pool: {e}")

    except Exception as e: logger.error(f"Error closing database connections: {e}")

    finally:
        db = None
        cursor = None
        db_pool = None
        db_pool_timer = None
        
# Function to execute a query on the database
# This function will attempt to execute the query multiple times if it fails
# It will return the result of the query if successful, or None if it fails
# Accepts the query, parameters, and whether to commit the query
def execute_query(query, params=None, is_timer=False, retry_attempts=3, commit=False):
    global db, cursor
    #logger.info(f'Executing query: {query}, Params: {params}')
    attempt = 0
    try:
        while attempt < retry_attempts:
            if not is_timer:
                try:
                    if not db_pool or db_pool is None: setup_pool()
                    with db_pool.get_connection() as connection:
                        with connection.cursor() as cursor:
                            cursor.execute(query, params)
                            logger.info(f'Query executed successfully')
                            if commit:
                                connection.commit()
                                return True
                            return cursor.fetchall()
                except mysql.connector.Error as e:
                    logger.error(f'Error executing query: Exception: {e}, Query: {query}, Params: {params}')
                    attempt += 1
            else:
                try:
                    if not db_pool_timer or db_pool_timer is None: setup_pool()
                    with db_pool_timer.get_connection() as connection:
                        with connection.cursor() as cursor:
                            cursor.execute(query, params)
                            logger.info(f'Query executed successfully')
                            if commit: connection.commit(); return True
                            return cursor.fetchall()
                except mysql.connector.Error as e:
                    logger.error(f'Error executing query: Exception: {e}, Query: {query}, Params: {params}')
                    attempt += 1
        logger.error(f'Failed to execute query after {retry_attempts} attempts, query: {query}')
        return None
    except Exception as e:
        logger.error(f'Error executing query: Exception: {e}, Query: {query}, Params: {params}')
        return None

# Global variables for the game sessions, game sessions as a dictionary, and game channels
game_sessions = []
game_sessions_as_dict = {}
GAME_CHANNELS = None

# Function to update the local game sessions list
def update_local_game_sessions():
    logger.info('Updating local game sessions')
    global game_sessions, cursor, db
    
    if not cursor: db, cursor = get_current_new_cursor()
        
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
    """
    cursor.execute(query)
    game_sessions = cursor.fetchall()
    logger.info(f'Game sessions updated: {game_sessions}')
    
def game_sessions_dict():
    global game_sessions, game_sessions_as_dict
    output = {}
    
    if len(game_sessions) == len(game_sessions_as_dict.keys()): return game_sessions_as_dict
    
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
            "timer_duration": game[7],
            "cooldown_duration": int(game[8])
        }
        output[game[0]] = formatted_output  
    game_sessions_as_dict = output
    return output

def get_game_session_by_id(game_id):
    global game_sessions
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

    db.commit()
    
# Function to create a game session in the database
def create_game_session(admin_role_id, guild_id, button_channel_id, game_chat_channel_id, start_time, timer_duration, cooldown_duration):
    global cursor, lock
    query = """
        INSERT INTO game_sessions (admin_role_id, guild_id, button_channel_id, game_chat_channel_id, start_time, timer_duration, cooldown_duration)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    params = (admin_role_id, guild_id, button_channel_id, game_chat_channel_id, start_time, timer_duration, cooldown_duration)
    with lock: execute_query(query, params)
    game_session_id = cursor.lastrowid
    return game_session_id

# Function to get the game channels from the database
def get_game_channels_from_db():
    global cursor, db
    if not cursor: db, cursor = get_current_new_cursor()
    try:
        query = """
            SELECT button_channel_id, game_chat_channel_id FROM game_sessions
        """
        cursor.execute(query)
        channels = cursor.fetchall()
        channels_list = [list(channel) for channel in channels]
        return channels_list[0]
    except Exception as e:
        logger.error(f'Error getting game channels from db: {e}')
        return None

# Function to get all game channels
def get_all_game_channels():
    global GAME_CHANNELS
    if GAME_CHANNELS:
        return GAME_CHANNELS
    GAME_CHANNELS = get_game_channels_from_db()
    return GAME_CHANNELS

# Setup the connection pools
if setup_pool(): logger.info('Connection pools set up successfully')
else: logger.error('Error setting up connection pools')

# Initialize variables, get database connection and cursor, create tables, and update local game sessions
GAME_CHANNELS = get_all_game_channels()
db, cursor = get_current_new_cursor()
create_tables()
update_local_game_sessions()

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
                
                with lock: result = execute_query(query, params)
                if not result: logger.warning(f"No click data found for user {user_id}. Skipping..."); continue

                _, latest_click_time, lowest_click_time, game_id = result[0]

                # Get the total clicks for the user
                query = '''
                    SELECT COUNT(*) AS total_clicks
                    FROM button_clicks
                    WHERE user_id = %s
                '''
                
                params = (user_id,)
                with lock: result = execute_query(query, params)
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

# Fix missing users
missing_users = get_missing_users()
logger.info(f"Missing users: {missing_users}")