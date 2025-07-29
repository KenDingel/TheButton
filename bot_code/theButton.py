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
    from utils.timer_button import warm_session_cache
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

# async def restore_button_views():
#     """Restore persistent button views for all active games"""
#     try:
#         for guild in bot.guilds:
#             game_session = await get_game_session_by_guild_id(guild.id)
#             if game_session:
#                 channel = bot.get_channel(game_session['button_channel_id'])
#                 if channel:
#                     # Fetch the most recent button message
#                     async for message in channel.history(limit=5):
#                         if message.author == bot.user and message.embeds:
#                             view = ButtonView(
#                                 timer_value=game_session['timer_duration'],
#                                 bot=bot,
#                                 game_id=game_session['game_id']
#                             )
#                             # Add the view without modifying the message
#                             bot.add_view(view, message_id=message.id)
#                             logger.info(f"Restored button view for game {game_session['game_id']} in {guild.name}")
#                             break
#     except Exception as e:
#         tb = traceback.format_exc()
#         logger.error(f"Error restoring button views: {e}\n{tb}")

# 5-12-2025
# async def restore_button_views():
#     """Restore persistent button views for all active games with better efficiency"""
#     try:
#         # Load all game sessions once
#         game_sessions = update_local_game_sessions()
#         sessions_dict = game_sessions_dict(game_sessions)
        
#         # Group game sessions by guild to process each guild once
#         sessions_by_guild = {}
#         for game_id, session in sessions_dict.items():
#             if isinstance(session, dict):
#                 guild_id = session.get('guild_id')
#                 if guild_id:
#                     if guild_id not in sessions_by_guild:
#                         sessions_by_guild[guild_id] = []
#                     sessions_by_guild[guild_id].append(session)
        
#         # Process each guild once
#         for guild_id, guild_sessions in sessions_by_guild.items():
#             guild = bot.get_guild(guild_id)
#             if not guild:
#                 continue
                
#             for game_session in guild_sessions:
#                 channel_id = game_session.get('button_channel_id')
#                 if not channel_id:
#                     continue
                    
#                 channel = bot.get_channel(int(channel_id))
#                 if not channel:
#                     continue
                
#                 # Find the button message
#                 try:
#                     async for message in channel.history(limit=5):
#                         if message.author == bot.user and message.embeds:
#                             # Add the view
#                             view = ButtonView(
#                                 timer_value=game_session['timer_duration'],
#                                 bot=bot,
#                                 game_id=game_session['game_id']
#                             )
#                             # Add the view without modifying the message
#                             bot.add_view(view, message_id=message.id)
#                             logger.info(f"Restored button view for game {game_session['game_id']} in {guild.name}")
                            
#                             # Add to message cache
#                             button_message_cache.update_message_cache(message, game_session['game_id'])
#                             break
#                 except Exception as e:
#                     logger.error(f"Error restoring button view for guild {guild_id}: {e}")
        
#     except Exception as e:
#         tb = traceback.format_exc()
#         logger.error(f"Error restoring button views: {e}\n{tb}")

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
        
# # Bot event handler for bot on_ready, on_disconnect, termination
# @bot.event
# async def on_ready():
#     global menu_timer
#     print(f"Starting bot... ")

#     # Print what servers the bot is connected to
#     for guild in bot.guilds:
#         print(f'Connected to guild: {guild.name}')
#         logger.info(f'Connected to guild: {guild.name}')

#     for guild in bot.guilds:
#         try:
#             game_session = await get_game_session_by_guild_id(guild.id)
#             if game_session:
#                 view = ButtonView(
#                     timer_value=await game_session['timer_duration'],
#                     bot=bot,
#                     game_id=game_session['game_id']
#                 )
#                 bot.add_view(view)
#         except Exception as e:
#             logger.error(f"Error processing guild {guild.name}: {e}")
#             continue

#     if not setup_pool(): 
#         logger.error(f"Failed to initialize database pools.")
#         return 
    
#     # Initialize menu timer if it doesn't exist
#     if menu_timer is None:
#         menu_timer = MenuTimer(bot)
        
#         # Add all active games to the timer
#         for guild in bot.guilds:
#             try:
#                 game_session = await get_game_session_by_guild_id(guild.id)
#                 if game_session:
#                     menu_timer.add_game(str(game_session['game_id']))  # Add each game to tracking
#                     view = ButtonView(
#                         timer_value=game_session['timer_duration'],
#                         bot=bot,
#                         game_id=game_session['game_id']
#                     )
#                     bot.add_view(view)
#             except Exception as e:
#                 logger.error(f"Error adding game for guild {guild.name}: {e}")
#                 continue
        
#         # Start the timer task after adding all games
#         menu_timer.update_timer_task.start()

#     # Restore persistent views for existing button messages
#     await restore_button_views()
        
#     print(f'Bot started as {bot.user}')
#     logger.info(f'Bot started as {bot.user}')
    
#     logger.info(f"Number of guilds: {len(bot.guilds)}")
#     for guild in bot.guilds:
#         logger.info(f'Connected to guild: {guild.name}')
#         guild_id = guild.id
        
#         logger.info(f"Updating guild names: {guild.name}")
#         query = """
#             INSERT INTO guild_names (guild_id, guild_name, last_updated)
#             SELECT %s, %s, UTC_TIMESTAMP()
#             WHERE NOT EXISTS (
#                 SELECT 1 FROM guild_names WHERE guild_id = %s
#             )
#             """
#         try:
#             params = (guild.id, guild.name, guild.id)
#             execute_query(query, params)
#         except Exception as e:
#             logger.error(f"Failed to update guild name for {guild.id}: {e}")

#         try:
#             game_session = await get_game_session_by_guild_id(guild_id)
#             if game_session is None:
#                 logger.info(f"No game session found for guild: {guild.name}")
#                 continue
#             logger.info(f"Game session: {game_session}")
#             await start_boot_game(bot, guild_id, game_session['button_channel_id'], menu_timer)
            
#             if game_session:
#                 try:
#                     await setup_roles(guild_id, bot)
#                 except Exception as e:
#                     logger.error(f"Error setting up roles for guild {guild.name}: {e}")
#                     pass
#         except Exception as e:
#             logger.error(f"Error processing game session for guild {guild.name}: {e}")
#             continue
    
#     logger.info(f'Bot ready!')  
#     await fix_missing_users(bot=bot)
# Removed for performance of bootup - 5-11-2025


# @bot.event
# async def on_ready():
#     global menu_timer
#     print(f"Starting bot... ")
#     # Print what servers the bot is connected to
#     for guild in bot.guilds:
#         print(f'Connected to guild: {guild.name}')
#         logger.info(f'Connected to guild: {guild.name}')
    
#     # Initialize database pool if needed
#     if not setup_pool(): 
#         logger.error(f"Failed to initialize database pools.")
#         return
        
#     # Load all game sessions at once to avoid repeated queries
#     all_sessions = update_local_game_sessions()
#     sessions_dict = game_sessions_dict(all_sessions)
    
#     # Initialize menu timer
#     if menu_timer is None:
#         menu_timer = MenuTimer(bot)
    
#     # Process each guild once with cached game sessions
#     for guild in bot.guilds:
#         try:
#             logger.info(f"Updating guild names: {guild.name}")
#             guild_id = guild.id
            
#             # Update guild name in database
#             query = """
#                 INSERT INTO guild_names (guild_id, guild_name, last_updated)
#                 SELECT %s, %s, UTC_TIMESTAMP()
#                 WHERE NOT EXISTS (
#                     SELECT 1 FROM guild_names WHERE guild_id = %s
#                 )
#                 """
#             try:
#                 params = (guild.id, guild.name, guild.id)
#                 execute_query(query, params)
#             except Exception as e:
#                 logger.error(f"Failed to update guild name for {guild.id}: {e}")
            
#             # Get game session for this guild from cached dictionary
#             game_session = None
#             for session in all_sessions:
#                 if session[2] == guild_id:  # Compare guild_id (column index 2)
#                     session_id = session[0]  # game_id is at index 0
#                     # Convert to dictionary format
#                     game_session = {
#                         "game_id": int(session[0]),
#                         "admin_role_id": int(session[1]) if session[1] else 0,
#                         "guild_id": int(session[2]),
#                         "button_channel_id": int(session[3]),
#                         "game_chat_channel_id": int(session[4]),
#                         "start_time": session[5],
#                         "end_time": session[6],
#                         "timer_duration": int(session[7]),
#                         "cooldown_duration": int(session[8])
#                     }
#                     break
                    
#             if game_session is None:
#                 logger.info(f"No game session found for guild: {guild.name}")
#                 continue
                
#             logger.info(f"Game session: {game_session}")
            
#             # Add game to menu timer tracking
#             if menu_timer is not None:
#                 menu_timer.add_game(str(game_session['game_id']))
                
#             # Start the game for this guild
#             try:
#                 await start_boot_game(bot, guild_id, game_session['button_channel_id'], menu_timer)
                
#                 # Setup roles if needed but catch permission errors
#                 try:
#                     await setup_roles(guild_id, bot)
#                 except nextcord.errors.Forbidden as e:
#                     logger.error(f"Error setting up roles for guild {guild.name}: {e}")
#                     # Continue despite role setup failure
#                 except Exception as e:
#                     logger.error(f"Error setting up roles for guild {guild.name}: {e}")
#             except Exception as e:
#                 logger.error(f"Error processing game session for guild {guild.name}: {e}")
#         except Exception as e:
#             logger.error(f"Error processing guild {guild.name}: {e}")
#             continue
    
#     # Start the timer task after adding all games
#     if menu_timer and not menu_timer.update_timer_task.is_running():
#         menu_timer.update_timer_task.start()
        
#     # Restore persistent views for existing button messages
#     await restore_button_views()
    
#     logger.info(f'Bot started as {bot.user}')
#     logger.info(f"Number of guilds: {len(bot.guilds)}")
#     logger.info(f'Bot ready!')  
    
#     # Fix missing users (can be done after bot is ready to avoid slowing boot)
#     await fix_missing_users(bot=bot)

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

    await warm_session_cache(bot)
        
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