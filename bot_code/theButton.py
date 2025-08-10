# The button.py
print("Starting bot file...")
import asyncio
from datetime import timezone
import traceback
import signal
import datetime
import random
import sys

# Nextcord
import nextcord
from nextcord.ext import commands
print("Nextcord imported...")
# Local imports
try:
    from utils.utils import logger, config, paused_games
    from database.database import setup_pool, close_disconnect_database, fix_missing_users, get_game_session_by_guild_id, execute_query, update_local_game_sessions, game_sessions_dict
    from message.message_handlers import handle_message, start_boot_game
    from button.button_functions import setup_roles, MenuTimer, create_button_message  
    from button.button_view import ButtonView
    from game.game_cache import button_message_cache
except Exception as e:
    print(f"Error importing local modules: {e}")
    print(traceback.format_exc())
    sys.exit(1)

print("Local imports done...")

try:
    # Bot setup, intents, and event handlers
    intents = nextcord.Intents.default()
    intents.message_content = True
    intents.members = True
    bot = commands.Bot(command_prefix='!', intents=intents, shard_count=5) 

    # Global menu timer 
    menu_timer = None
except Exception as e:
    print(f"Error initializing bot: {e}")
    print(traceback.format_exc())
    sys.exit(1)

print("Bot initialized...")

# Bot event handler for new messages
@bot.event
async def on_message(message):
    await handle_message(message, bot, menu_timer=menu_timer)

# Bot event handlers for rate limits and errors
@bot.event
async def on_http_ratelimit(limit, remaining, reset_after, bucket, scope):
    shard_id = getattr(bot, 'shard_id', 'unknown')
    logger.warning(f"Shard {shard_id}: HTTP Rate limited. {limit=} {remaining=} {reset_after=}")
    # Add extra delay with jitter
    await asyncio.sleep(reset_after + random.uniform(0, 2))

@bot.event
async def on_global_ratelimit(retry_after):
    print(f"{retry_after=}")
    # logger.warning(f"Global Rate limited. {retry_after=}")
    await asyncio.sleep(retry_after + 1)

@bot.event
async def on_socket_raw_receive(msg):
    if msg and isinstance(msg, str) and "heartbeat" not in msg.lower():
        logger.debug(f"Socket Received: {msg[:100]}...")  # Log first 100 chars to avoid spam

@bot.event
async def on_resumed():
    logger.info("Session resumed successfully")
    await restore_button_views()  # Restore views after resume
    
async def restore_button_views():
    """Restore persistent button views for all active games with better efficiency"""
    try:
        logger.info("Starting to restore button views...")
        
        # Get all game sessions at once
        sessions = update_local_game_sessions()
        
        # Dictionary to track processed message IDs to avoid duplicates
        processed_messages = set()
        
        # Group sessions by guild and channel ID
        sessions_by_channel = {}
        for session in sessions:
            if session[6] is not None:  # Skip ended games
                continue
                
            channel_id = session[3]  # button_channel_id is at index 3
            game_id = session[0]     # game_id is at index 0
            
            if channel_id not in sessions_by_channel:
                sessions_by_channel[channel_id] = []
                
            # Convert to dictionary for easier access
            session_dict = {
                "game_id": int(session[0]),
                "admin_role_id": int(session[1]) if session[1] else 0,
                "guild_id": int(session[2]),
                "button_channel_id": int(session[3]),
                "game_chat_channel_id": int(session[4]),
                "start_time": session[5],
                "end_time": session[6],
                "timer_duration": int(session[7]),
                "cooldown_duration": int(session[8])
            }
            
            sessions_by_channel[channel_id].append((game_id, session_dict))
            
        # Process each channel once to minimize API calls
        for channel_id, channel_sessions in sessions_by_channel.items():
            # Skip if invalid channel ID
            if not channel_id:
                continue
                
            # Get channel object
            channel = bot.get_channel(int(channel_id))
            if not channel:
                logger.warning(f"Channel {channel_id} not found for view restoration")
                continue
                
            try:
                # Get all relevant messages once
                button_messages = {}
                async for message in channel.history(limit=5):
                    if message.id in processed_messages:
                        continue
                        
                    if message.author == bot.user and message.embeds:
                        button_messages[message.id] = message
                        
                if not button_messages:
                    logger.info(f"No button messages found in channel {channel_id}")
                    continue
                    
                # Process each session for this channel
                for game_id, session in channel_sessions:
                    # Use the first available message (most recent)
                    for message_id, message in button_messages.items():
                        if message_id not in processed_messages:
                            # Create and attach the view
                            view = ButtonView(
                                timer_value=session['timer_duration'],
                                bot=bot,
                                game_id=session['game_id']
                            )
                            bot.add_view(view, message_id=message_id)
                            
                            # Add to message cache
                            button_message_cache.update_message_cache(message, session['game_id'])
                            
                            # Mark as processed
                            processed_messages.add(message_id)
                            
                            logger.info(f"Restored button view for game {session['game_id']} in {channel.guild.name}")
                            break
            except Exception as e:
                logger.error(f"Error restoring button views for channel {channel_id}: {e}")
                
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Error restoring button views: {e}\n{tb}")

@bot.event
async def on_ready():
    global menu_timer
    print(f"Starting bot... ")
    start_time = datetime.datetime.now()
    
    # Log guild connections
    guild_count = len(bot.guilds)
    logger.info(f"Connected to {guild_count} guilds")
    for guild in bot.guilds:
        logger.info(f'Connected to guild: {guild.name}')
    
    # Initialize database pool if needed
    if not setup_pool(): 
        logger.error(f"Failed to initialize database pools.")
        return
        
    # Load all game sessions and guild data at once to reduce DB queries
    all_sessions = update_local_game_sessions()
    sessions_by_guild = {}
    
    # Group sessions by guild
    for session in all_sessions:
        guild_id = session[2]  # guild_id is at index 2
        if guild_id not in sessions_by_guild:
            sessions_by_guild[guild_id] = []
        sessions_by_guild[guild_id].append(session)
    
    # Update guild names individually (can't do batch with current driver)
    for guild in bot.guilds:
        logger.info(f"Updating guild name: {guild.name}")
        query = """
            INSERT IGNORE INTO guild_names (guild_id, guild_name, last_updated)
            VALUES (%s, %s, UTC_TIMESTAMP())
        """
        try:
            execute_query(query, (guild.id, guild.name), commit=True)
        except Exception as e:
            logger.error(f"Failed to update guild name for {guild.id}: {e}")
    
    # Initialize menu timer
    if menu_timer is None:
        menu_timer = MenuTimer(bot)
    
    # Process each guild once with parallel tasks
    pending_tasks = []
    for guild in bot.guilds:
        guild_id = guild.id
        logger.info(f"Processing guild: {guild.name}")
        
        # Skip if no session for this guild
        if guild_id not in sessions_by_guild:
            logger.info(f"No game session found for guild: {guild.name}")
            continue
        
        # Process all sessions for this guild
        for session in sessions_by_guild[guild_id]:
            game_id = session[0]  # game_id is at index 0
            button_channel_id = session[3]  # button_channel_id is at index 3
            
            # Add game to menu timer tracking
            if menu_timer is not None:
                menu_timer.add_game(str(game_id))
            
            # Start the boot game process in parallel for each guild
            # Use existing start_boot_game function which handles button creation
            task = asyncio.create_task(
                start_boot_game(bot, guild_id, button_channel_id, menu_timer)
            )
            pending_tasks.append(task)
    
    # Wait for critical tasks to complete
    if pending_tasks:
        await asyncio.gather(*pending_tasks)
            
    # Start the timer task after adding all games
    if menu_timer and not menu_timer.update_timer_task.is_running():
        logger.info('Starting update timer task...')
        menu_timer.update_timer_task.start()
    
    # Restore persistent views for existing button messages
    await restore_button_views()
    
    # Log boot time statistics
    end_time = datetime.datetime.now()
    boot_duration = (end_time - start_time).total_seconds()
    logger.info(f'Bot started as {bot.user} in {boot_duration:.2f} seconds')
    logger.info(f"Number of guilds: {len(bot.guilds)}")
    logger.info(f'Bot ready!')  
    
    # Fix missing users in the background (non-blocking)
    asyncio.create_task(fix_missing_users(bot=bot))

# Also update the error handler
@bot.event
async def on_error(event, *args, **kwargs):
    if event == "on_message": 
        logger.error(f"Unhandled message: {args[0]}")
    elif args and isinstance(args[0], nextcord.HTTPException):
        if args[0].status == 429:
            retry_after = args[0].response.headers["Retry-After"]
            logger.warning(f"Rate limited. Retrying in {retry_after} seconds.")
            await asyncio.sleep(float(retry_after * 2))
            return
    
    # Log the actual error
    error = sys.exc_info()
    logger.error(f"Error in {event}: {error[0].__name__}: {error[1]}")
    logger.error(traceback.format_exc())
    print(f"Error in {event}: {error[0].__name__}: {error[1]}")

@bot.event
async def on_disconnect():
    logger.warning("Bot disconnecting - attempting graceful shutdown")
    try:
        # Give pending operations a chance to complete
        await asyncio.sleep(2)
        await close_bot()
    except Exception as e:
        logger.error(f"Error during disconnect handling: {e}")
        logger.error(traceback.format_exc())
    finally:
        logger.info("Disconnect handling completed")

async def close_bot():
    """Gracefully close the bot with proper cleanup"""
    logger.info("Starting graceful shutdown...")
    print("Starting graceful shutdown...")
    try:
        # Cancel any pending tasks
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        logger.info(f"Cancelled {len(tasks)} pending tasks")
        
        # Wait briefly for tasks to clean up
        await asyncio.sleep(1)
        
        # Close database connections
        close_disconnect_database()
        
        logger.info("Graceful shutdown completed")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")
        logger.error(traceback.format_exc())
    finally:
        # Use sys.exit instead of exit() to avoid raising SystemExit
        import sys
        sys.exit(0)

# Modify your existing signal handler
def terminate_handler(signal, frame):
    logger.info("Termination signal received")
    asyncio.create_task(close_bot())


print("Starting bot...")
try:
    logger.info(f"""
          
░▒▓████████▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓████████▓▒░      ░▒▓███████▓▒░░▒▓█▓▒░░▒▓█▓▒░▒▓████████▓▒░▒▓████████▓▒░▒▓██████▓▒░░▒▓███████▓▒░  
   ░▒▓█▓▒░   ░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░             ░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░  ░▒▓█▓▒░      ░▒▓█▓▒░  ░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░ 
   ░▒▓█▓▒░   ░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░             ░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░  ░▒▓█▓▒░      ░▒▓█▓▒░  ░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░ 
   ░▒▓█▓▒░   ░▒▓████████▓▒░▒▓██████▓▒░        ░▒▓███████▓▒░░▒▓█▓▒░░▒▓█▓▒░  ░▒▓█▓▒░      ░▒▓█▓▒░  ░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░ 
   ░▒▓█▓▒░   ░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░             ░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░  ░▒▓█▓▒░      ░▒▓█▓▒░  ░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░ 
   ░▒▓█▓▒░   ░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░             ░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░  ░▒▓█▓▒░      ░▒▓█▓▒░  ░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░ 
   ░▒▓█▓▒░   ░▒▓█▓▒░░▒▓█▓▒░▒▓████████▓▒░      ░▒▓███████▓▒░ ░▒▓██████▓▒░   ░▒▓█▓▒░      ░▒▓█▓▒░   ░▒▓██████▓▒░░▒▓█▓▒░░▒▓█▓▒░ 
    """)                                                                                                  

    bot.run(config['discord_token'])
except Exception as e:
    logger.error(f"Error starting bot: {e}")
    logger.error(traceback.format_exc())
    asyncio.create_task(close_bot())