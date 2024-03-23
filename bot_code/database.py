# Database.py
import mysql.connector
from mysql.connector.pooling import MySQLConnectionPool

from utils import config, logger

db_pool = None
db_pool_timer = None

db = None
cursor = None
timer_db = None
cursor_tb = None

def get_db_connection():
    return db_pool.get_connection()

def get_db_connection_timer():
    return db_pool_timer.get_connection()

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

def kill_sql_processes():
    query = "SHOW PROCESSLIST"
    processes = execute_query(query)
    for process in processes:
        if process[1] == 'root':
            query = f"KILL {process[0]}"
            execute_query(query, commit=True)
    logger.info('SQL processes killed')

def setup_pool(config=config):
    global db_pool, db_pool_timer
    """
    Set up the connection pools for the main and timer databases.

    Args:
        config (dict): A dictionary containing the database configuration.

    """
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

def close_disconnect_database():
    """
    Close and disconnect all database connections, cursors, and pools.
    """
    global db_pool, db_pool_timer
    global db, cursor
    global timer_db, cursor_tb

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

        # Close the cursor if it exists
        if cursor_tb:
            try:
                cursor_tb.close()
                logger.info("Cursor closed successfully.")
            except mysql.connector.Error as e:
                logger.error(f"Error closing cursor: {e}")

        # Close the database connection if it exists
        if timer_db:
            try:
                timer_db.close()
                logger.info("Database connection closed successfully.")
            except mysql.connector.Error as e:
                logger.error(f"Error closing database connection: {e}")
                
        # Close the connection pools
        if db_pool:
            try:
                db_pool.pool_clear_pool_connections()
                db_pool.pool_reset_session()
                db_pool.close()
                db_pool = None
                logger.info("Main connection pool closed successfully.")
            except mysql.connector.Error as e:
                logger.error(f"Error closing main connection pool: {e}")

        if db_pool_timer:
            try:
                db_pool_timer.pool_clear_pool_connections()
                db_pool_timer.pool_reset_session()
                db_pool_timer.close()
                db_pool_timer = None
                logger.info("Timer connection pool closed successfully.")
            except mysql.connector.Error as e:
                logger.error(f"Error closing timer connection pool: {e}")

    except Exception as e:
        logger.error(f"Error closing database connections: {e}")

    finally:
        db = None
        cursor = None
        db_pool = None
        db_pool_timer = None
        
def execute_query(query, params=None, var_db=None, var_cursor=None, is_timer=False, retry_attempts=3, commit=False):
    global db, cursor
    #logger.info(f'Executing query: {query}, Params: {params}')
    attempt = 0
    try:
        while attempt < retry_attempts:
            if not is_timer:
                try:
                    if not db_pool or db_pool is None:
                        setup_pool()
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
                    if not db_pool_timer or db_pool_timer is None:
                        setup_pool()
                    with db_pool_timer.get_connection() as connection:
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
        logger.error(f'Failed to execute query after {retry_attempts} attempts, query: {query}')
        return None
    except Exception as e:
        logger.error(f'Error executing query: Exception: {e}, Query: {query}, Params: {params}')
        return None

game_sessions = []
game_sessions_as_dict = {}

def update_local_game_sessions():
    logger.info('Updating local game sessions')
    global game_sessions, cursor, db
    
    if not cursor:
        db, cursor = get_current_new_cursor()
        
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
    
    if len(game_sessions) == len(game_sessions_as_dict.keys()):
        return game_sessions_as_dict
    
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
    #logger.info(f'Game sessions dict created: {output}')
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
        if game[2] == guild_id:
            return get_game_session_by_id(game[0])
    return None

def get_game_session_count():
    global game_sessions
    return len(game_sessions)

def create_tables():
    global db, cursor
    if not cursor:
        db, cursor = get_current_new_cursor()
        
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
    
def create_game_session(admin_role_id, guild_id, button_channel_id, game_chat_channel_id, start_time, timer_duration, cooldown_duration):
    global cursor
    query = """
        INSERT INTO game_sessions (admin_role_id, guild_id, button_channel_id, game_chat_channel_id, start_time, timer_duration, cooldown_duration)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    params = (admin_role_id, guild_id, button_channel_id, game_chat_channel_id, start_time, timer_duration, cooldown_duration)
    execute_query(query, params)
    game_session_id = cursor.lastrowid
    return game_session_id

def get_game_channels_from_db():
    global cursor, db
    if not cursor:
        db, cursor = get_current_new_cursor()
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

GAME_CHANNELS = None

def get_all_game_channels():
    global GAME_CHANNELS
    if GAME_CHANNELS:
        return GAME_CHANNELS
    GAME_CHANNELS = get_game_channels_from_db()
    return GAME_CHANNELS


if setup_pool():
    logger.info('Connection pools set up successfully')
else:
    logger.error('Error setting up connection pools')

GAME_CHANNELS = get_all_game_channels()
db, cursor = get_current_new_cursor()
create_tables()
update_local_game_sessions()

def get_missing_users():
    try:
        # Get a connection from the pool
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

        # Convert the result to a list of user_id values
        missing_user_ids = [user_id for user_id, in missing_users]

        return missing_user_ids

    except mysql.connector.Error as error:
        logger.error(f"Error getting missing users: {error}")
        return []

    finally:
        # Close the cursor and connection
        if cursor:
            cursor.close()
        if connection:
            connection.close()

missing_users = get_missing_users()
logger.info(f"Missing users: {missing_users}")