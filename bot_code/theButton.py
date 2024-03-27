# The button.py
import os
import asyncio
import datetime
from datetime import timezone
import traceback
import signal

import nextcord
from nextcord import Guild
from nextcord.ext import commands, tasks

from bot_code.utils.utils import *
from bot_code.database.database import *
from bot_code.game.end_game import get_end_game_embed
from bot_code.text.full_text import *
from bot_code.game.game_cache import *
from bot_code.message.message_handlers import handle_message
from bot_code.button.button_functions import *
from bot_code.user.user_manager import user_manager

intents = nextcord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

menu_timer = None

@bot.event
async def on_message(message):
    await handle_message(message, bot, logger=logger, menu_timer=menu_timer)
    
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
    if event == "on_message":
        print(f"Unhandled message: {args[0]}")
        logger.error(f"Unhandled message: {args[0]}")

    if isinstance(args[0], nextcord.HTTPException):
        if args[0].status == 429:
            retry_after = args[0].response.headers["Retry-After"]
            print(f"Rate limited. Retrying in {retry_after} seconds.")
            logger.warning(f"Rate limited. Retrying in {retry_after} seconds.")
            await asyncio.sleep(float(retry_after))
            await asyncio.sleep(float(retry_after))
            return
    raise

@bot.event
async def on_ready():
    global menu_timer
    print(f"Starting bot... ")
    
    if not setup_pool(): 
        logger.error(f"Failed to initialize database pools.")
        return 
    
    if menu_timer is None:
        menu_timer = MenuTimer(bot)
        
    print(f'Bot started as {bot.user}')
    logger.info(f'Bot started as {bot.user}')
    
    logger.info(f"Number of guilds: {len(bot.guilds)}")
    for guild in bot.guilds:
        logger.info(f'Connected to guild: {guild.name}')
        guild_id = guild.id
        game_session = get_game_session_by_guild_id(guild_id)
        if game_session:
            await setup_roles(guild_id, bot)
            game_channel = bot.get_channel(game_session['button_channel_id'])
            if game_channel:
                await game_channel.send("sb")
                logger.info(f"Button start message sent to channel {game_channel.name}")
            else:
                logger.error(f"Button channel not found for game session {game_session['game_id']}")
        else:
            logger.info(f"No game session found for guild {guild.id}")
            
    logger.info(f'Bot ready!')  
    await fix_missing_users(bot=bot)
        
@bot.event
async def on_disconnect():
    logger.info(f'Bot disconnected')
    close_disconnect_database()
    
    
async def close_bot():
    close_disconnect_database()
    await bot.close()
    exit(0)

async def terminate_handler(signal, frame):
    await asyncio.get_event_loop().run(close_bot())

signal.signal(signal.SIGINT, terminate_handler)

bot.run(config['discord_token'])