# The button.py
import asyncio
from datetime import timezone
import traceback
import signal

# Nextcord
import nextcord
from nextcord.ext import commands

# Local imports
from utils.utils import logger, config
from database.database import setup_pool, close_disconnect_database, fix_missing_users, get_game_session_by_guild_id
from message.message_handlers import handle_message, start_boot_game
from button.button_functions import setup_roles, MenuTimer
from button.button_view import ButtonView

# Bot setup, intents, and event handlers
intents = nextcord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Global menu timer 
menu_timer = None

# Bot event handler for new messages
@bot.event
async def on_message(message):
    await handle_message(message, bot, menu_timer=menu_timer)

# Bot event handlers for rate limits and errors
@bot.event
async def on_http_ratelimit(limit, remaining, reset_after, bucket, scope):
    print(f"{limit=} {remaining=} {reset_after=} {bucket=} {scope=}")
    logger.warning(f"HTTP Rate limited.")
    logger.warning(f"{limit=} {remaining=} {reset_after=} {bucket=} {scope=}")
    await asyncio.sleep(reset_after)
    await asyncio.sleep(reset_after)

@bot.event
async def on_global_ratelimit(retry_after):
    print(f"{retry_after=}")
    logger.warning(f"Global Rate limited.")
    logger.warning(f"{retry_after=}")
    await asyncio.sleep(retry_after)
    
@bot.event
async def on_error(event, *args, **kwargs):
    if event == "on_message": logger.error(f"Unhandled message: {args[0]}")

    if isinstance(args[0], nextcord.HTTPException):
        if args[0].status == 429:
            retry_after = args[0].response.headers["Retry-After"]
            logger.warning(f"Rate limited. Retrying in {retry_after} seconds.")
            await asyncio.sleep(float(retry_after * 2))
            return
    raise
async def restore_button_views():
    """Restore persistent button views for all active games"""
    try:
        for guild in bot.guilds:
            game_session = get_game_session_by_guild_id(guild.id)
            if game_session:
                channel = bot.get_channel(game_session['button_channel_id'])
                if channel:
                    # Fetch the most recent button message
                    async for message in channel.history(limit=5):
                        if message.author == bot.user and message.embeds:
                            view = ButtonView(
                                timer_value=game_session['timer_duration'],
                                bot=bot,
                                game_id=game_session['game_id']
                            )
                            # Add the view without modifying the message
                            bot.add_view(view, message_id=message.id)
                            logger.info(f"Restored button view for game {game_session['game_id']} in {guild.name}")
                            break
                    
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Error restoring button views: {e}\n{tb}")

# Bot event handler for bot on_ready, on_disconnect, termination
@bot.event
async def on_ready():
    global menu_timer
    print(f"Starting bot... ")

    # Print what servers the bot is connected to
    for guild in bot.guilds:
        print(f'Connected to guild: {guild.name}')
        logger.info(f'Connected to guild: {guild.name}')

    if not setup_pool(): 
        logger.error(f"Failed to initialize database pools.")
        return 
    
    if menu_timer is None:
        menu_timer = MenuTimer(bot)
        menu_timer.update_timer_task.start()

    # Restore persistent views for existing button messages
    await restore_button_views()
        
    print(f'Bot started as {bot.user}')
    logger.info(f'Bot started as {bot.user}')
    
    logger.info(f"Number of guilds: {len(bot.guilds)}")
    for guild in bot.guilds:
        logger.info(f'Connected to guild: {guild.name}')
        guild_id = guild.id
        game_session = get_game_session_by_guild_id(guild_id)
        logger.info(f"Game session: {game_session}")
        channel = bot.get_channel(game_session['button_channel_id'])
        await start_boot_game(bot, guild_id, game_session['button_channel_id'], menu_timer)
        
        if game_session:
            await setup_roles(guild_id, bot)
            
    logger.info(f'Bot ready!')  
    await fix_missing_users(bot=bot)
        
async def close_bot():
    close_disconnect_database()
    await bot.close()
    exit(0)

@bot.event
async def on_disconnect():
    logger.info(f'Bot disconnected')
    asyncio.create_task(close_bot())
    # Signal handler for termination (When the user presses Ctrl+C, SIGINT is sent)
    def terminate_handler(signal, frame): asyncio.create_task(close_bot())

    # Signal handler for SIGINT
    signal.signal(signal.SIGINT, terminate_handler)

bot.run(config['discord_token'])