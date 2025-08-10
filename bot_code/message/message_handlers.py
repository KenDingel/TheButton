# message_handlers.py
import datetime
from datetime import timezone
import traceback
from typing import Dict, List, Tuple, Optional
import nextcord
import random
import asyncio
import logging
import giphy_client
from giphy_client.rest import ApiException

# Local imports
from database.database import (
    get_game_session_by_guild_id, 
    create_game_session, 
    update_or_create_game_session, 
    get_game_session_by_id, 
    get_all_game_channels, 
    execute_query, 
    game_sessions_dict, 
    update_local_game_sessions, 
    insert_first_click,
    get_or_create_guild_icon,
    update_guild_icon,
    check_button_clicks
)
from utils.utils import config, logger, lock, config, format_time, get_color_emoji, get_color_state, get_color_name, GUILD_EMOJIS, paused_games
from utils.chart_generator import ChartGenerator
from utils.stats_helpers import (
    get_nearby_ranks,
    format_game_duration,
    calculate_time_to_next_rank,
    get_duration_emoji
)
from text.full_text import LORE_TEXT
from button.button_functions import setup_roles, create_button_message
from game.game_cache import game_cache
import io
from game.character_handler import CharacterHandler
from message.voice_generator import generate_audio

import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as mpatches

# Declare global variables at module level before use
paused_games = []
leaderboard_commands = ['skibidi', 'gyatt', 'rizz', 'ohio', 'duke', 'dennis', 'livvydunne', 'babygronk', 'sussy', 'imposter', 'pibby', 'glitch', 'sigma', 'alpha', 'omega', 'male', 'grindset', 'goon', 'cave', 'freddy', 'fazbear', 'colleen', 'ballinger', 'smurf', 'cat', 'vs', 'strawberry', 'elephant', 'blud', 'dawg', 'shmlawg', 'ishowspeed', 'a', 'whole', 'bunch', 'of', 'turbulence', 'ambatukam', 'bro', 'really', 'thinks', 'he\'s', 'carti', 'literally', 'hitting', 'the', 'griddy', 'the', 'ocky', 'way', 'kai', 'cenat', 'fanum', 'tax', 'garten', 'of', 'banban', 'no', 'in', 'class', 'not', 'the', 'mosquito', 'again', 'bussing', 'axel', 'in', 'harlem', 'whopper', 'whopper', 'whopper', 'whopper', '1', '2', 'buckle', 'my', 'shoe', 'goofy', 'ahh', 'aiden', 'ross', 'sin', 'city', 'monday', 'left', 'me', 'broken', 'quirked', 'up', 'white', 'boy', 'busting']
leaderboard_commands_2 = ['it', 'down', 'sexual', 'style', 'goated', 'with', 'the', 'sauce', 'john', 'pork', 'grimace', 'shake', 'kiki', 'do', 'you', 'love', 'me', 'huggy', 'wuggy', 'nathaniel', 'b', 'lightskin', 'stare', 'biggest', 'bird', 'omar', 'the', 'referee', 'amogus', 'uncanny', 'wholesome', 'reddit', 'chungus', 'keanu', 'reeves', 'pizza', 'tower', 'zesty', 'poggers', 'kumalala', 'savesta', 'quandale', 'dingle', 'glizzy', 'rose', 'toy', 'ankha', 'zone', 'thug', 'shaker', 'morbin', 'time', 'dj', 'khaled', 'sisyphus', 'oceangate', 'shadow', 'wizard', 'money', 'gang', 'ayo', 'the', 'pizza', 'here', 'pluh', 'nair', 'butthole', 'waxing', 't-pose', 'ugandan', 'knuckles', 'family', 'guy', 'funny', 'moments', 'compilation', 'with', 'subway', 'surfers', 'gameplay', 'at', 'the', 'bottom', 'nickeh30', 'ratio', 'uwu', 'delulu', 'opium', 'bird', 'cg5', 'mewing', 'fortnitebattlepass', 'gta6', 'backrooms', 'gigachad', 'based', 'cringe', 'kino', 'redpilled', 'chat', 'i', 'love', 'lean', 'looksmaxxing', 'gassy', 'social', 'credit', 'bing', 'chilling', 'xbox', 'live', 'mrbeast', 'ice', 'spice', 'gooning', 'andy', 'leyley', 'metalpipefalling', 'l', 'w']

brain_rot_phrases = [
    'skibidi toilet', 'sigma male', 'alpha male', 'omega male', 'hitting the griddy',
    'garten of banban', 'kai cenat', 'fanum tax', 'sin city', 'quirked up white boy',
    'goated with the sauce', 'grimace shake', 'john pork', 'nathaniel b', 'lightskin stare',
    'kumalala savesta', 'quandale dingle', 'shadow wizard money gang', 'ayo the pizza here',
    'family guy funny moments', 'ugandan knuckles', 'bing chilling', 'ice spice', 'pluh',
    'busting it down sexual style', 'goofy ahh', 'andrew tate', 'freddy fazbear',
    'colleen ballinger', 'ishowspeed', 'a whole bunch of turbulence',
    'bro really thinks he\'s carti', 'literally hitting the griddy',
    'the ocky way', 'no in class', 'not the mosquito again',
    'bussing axel in harlem', 'whopper whopper whopper whopper',
    '1 2 buckle my shoe', 'monday left me broken'
]

try:
    giphy_api = giphy_client.DefaultApi()
except Exception as e:
    logger.error(f"Failed to initialize Giphy API: {e}\n{traceback.format_exc()}")
    giphy_api = None

COLOR_MAP = {
    'Purple': '#6A4C93',
    'Blue': '#3B83BD',
    'Green': '#4CAF50',
    'Yellow': '#FFC107',
    'Orange': '#FF9800',
    'Red': '#F44336',
    'Unknown': '#CCCCCC'
}

EMOJI_COLOR_MAP = {
    '🟣': 'Purple',
    '🔵': 'Blue',
    '🟢': 'Green',
    '🟡': 'Yellow',
    '🟠': 'Orange',
    '🔴': 'Red'
}

def format_time(seconds):
    """Format seconds into HH:MM:SS format."""
    hours, remainder = divmod(int(seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"

async def send_gif(channel, keywords: list) -> bool:
    """
    Send a GIF to the specified channel based on keywords
    Args:
        channel: Discord channel to send the GIF to
        keywords: List of keywords to search for
    Returns:
        bool: True if GIF was sent successfully, False otherwise
    """
    try:
        # Initialize API instance with key from config
        api_instance = giphy_client.DefaultApi()
        search_string = ' '.join(keywords)
        search_string = f"{search_string}"
        
        # Use the API key from config
        response = api_instance.gifs_search_get(
            api_key=config['giphy_api_key'],  # Using config here
            q=search_string,
            limit=20,
            rating='r'
        )
        
        if response.data:
            gif = random.choice(response.data)
            await channel.send(gif.images.original.url)
            logger.info(f"Successfully sent GIF for keywords: {search_string}")
            return True
            
    except ApiException as e:
        logger.error(f"Giphy API error: {e}\n{traceback.format_exc()}")
    except Exception as e:
        logger.error(f"Error sending GIF: {e}\n{traceback.format_exc()}")
    
    return False


def is_brain_rot(message_text = ""): 
    """
    Check if a message contains "brain rot" phrases that should trigger random commands.
    
    Args:
        message_text (str): The message text to check
        
    Returns:
        int: A random number between 1-9 if brain rot detected, 0 otherwise
            1: myrank/rank command
            2: showclicks command
            3: leaderboard1/l1 command
            4: buttonrank/br command
            5: check command
            6: leaderboard2/l2 command
            7: playercharts/statsp command
            8: gamecharts/statsg command
            9: timeline/clicktimeline command
    """
    global leaderboard_commands, leaderboard_commands_2, brain_rot_phrases
    
    # Convert to lowercase for case-insensitive matching
    message_text_lower = message_text.lower()
    
    # Check for exact word match first (existing functionality)
    if message_text_lower in leaderboard_commands or message_text_lower in leaderboard_commands_2:
        # random int between 1 and 9
        random_return = random.randint(1, 9)
        return random_return
    
    # Check for phrase matches
    for phrase in brain_rot_phrases:
        if phrase in message_text_lower:
            # random int between 1 and 9
            random_return = random.randint(1, 9)
            return random_return
            
    return 0

logger = logging.getLogger(__name__)

def is_brain_rot(message_text = ""): 
    global leaderboard_commands, leaderboard_commands_2, brain_rot_phrases
    
    # Convert to lowercase for case-insensitive matching
    message_text_lower = message_text.lower()
    
    # Check for exact word match first (existing functionality)
    if message_text_lower in leaderboard_commands or message_text_lower in leaderboard_commands_2:
        # random int between 1 and 9
        random_return = random.randint(1, 9)
        return random_return
    
    # Check for phrase matches
    for phrase in brain_rot_phrases:
        if phrase in message_text_lower:
            # random int between 1 and 9
            random_return = random.randint(1, 9)
            return random_return
            
    return 0

async def handle_bot_mention(message, bot):
    """
    Handle when the bot is mentioned or replied to in chat.
    Generates a response and potentially sends a GIF based on the current game state.
    """
    try:
        # Check if message is in a valid game channel
        channel_name = message.channel.name
        is_button_chat = "button" in channel_name and "chat" in channel_name
        if not is_button_chat:
            return

        await message.add_reaction('⌛')

        # Get game session and current state
        game_session = await get_game_session_by_guild_id(message.guild.id)
        if not game_session:
            return

        # Get current timer value and color
        query = '''
            SELECT timer_value, click_time
            FROM button_clicks 
            WHERE game_id = %s
            ORDER BY click_time DESC
            LIMIT 1
        '''
        result = execute_query(query, (game_session['game_id'],))
        if not result or not result[0]:
            current_timer = game_session['timer_duration']
            current_color = "Purple"  # Default state
        else:
            timer_value, last_click = result[0]
            current_time = datetime.datetime.now(timezone.utc)
            elapsed_time = (current_time - last_click.replace(tzinfo=timezone.utc)).total_seconds()
            current_timer = max(0, float(timer_value) - elapsed_time)
            current_color = get_color_name(current_timer, game_session['timer_duration'])

        # Get chat history
        message_history = await get_message_history(message.channel)
        
        # Get user's display name
        display_name = message.author.display_name or message.author.name
        
        # Generate response
        handler = CharacterHandler.get_instance()
        response, gif_keywords = await handler.generate_chat_response(
            message_history=message_history,
            current_color=current_color,
            timer_value=current_timer,
            message_content=message.content,
            mentioned_by=display_name
        )
        
        if response:
            # Send the text response
            await message.reply(f"{response}")
            
            # Determine if we should send a GIF based on color and random chance
            should_send_gif = random.random() < 0.05  # 50% base chance
            if current_color in ['Red', 'Orange']:
                should_send_gif = random.random() < 0.9  # 70% chance for red/orange states
            elif current_color in ['Yellow']:
                should_send_gif = random.random() < 0.7  # 60% chance for yellow state
            
            # Send GIF if conditions are met
            if should_send_gif and gif_keywords:
                try:
                    await send_gif(message.channel, gif_keywords)
                except Exception as e:
                    logger.error(f'Error sending GIF: {e}\n{traceback.format_exc()}')
                    # Don't raise the error - GIF sending is non-critical

            # Send audio clip with ElevenLabs_TTS
            try:
                if should_send_gif:
                    audio_path = generate_audio(response)
                    if audio_path:
                        await message.channel.send(file=nextcord.File(audio_path))
                    else:
                        logger.error("Failed to generate audio.")
            except Exception as e:
                logger.error(f'Error sending TTS audio: {e}\n{traceback.format_exc()}')

        await message.remove_reaction('⌛', bot.user)
        
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f'Error handling bot mention: {e}\n{tb}')
        try:
            await message.remove_reaction('⌛', bot.user)
        except:
            pass


# Handle message function
# This function is responsible for handling messages in the game channels.
# Command List: <command_name>: <command_in_discord> **<description>**
# - startbutton: sb **Starts the button game**
# - myrank: rank **Check your personal stats**
# - leaderboard: scores, scoreboard, top **Check the top 10 clickers**
# - check **Check if you have a click ready**
async def handle_message(message, bot, menu_timer):
    global paused_games, lock, logger
    channel_name = message.channel.name
    is_button_chat = ("button-chat" in channel_name) or "button-game" in channel_name or "ʙᴜᴛᴛᴏɴ" in channel_name
    if message.author == bot.user and message.content.lower() != "sb": return

    # FILTER USERS BY ID: BAN LIST
    if message.author.id in [116341342430298115]: return

    if not isinstance(message.channel, nextcord.DMChannel) and not is_button_chat:
        return

    # Handle bot mentions and replies
    if bot.user in message.mentions or (message.reference and message.reference.resolved and message.reference.resolved.author == bot.user):
        await message.add_reaction('⏳')
        await handle_bot_mention(message, bot)
        await message.remove_reaction('⏳', bot.user)
        return
    
    try:
        logger.info(f"Message received in {message.guild.name}: {message.content}")
    except:
        logger.info(f"Message received in DM: {message.content}")
    try:
        
        if message.content.lower() == 'startbutton' or message.content.lower() == 'sb':
            logger.info(f"Starting button game in {message.guild.name}")
            # Check if the user has admin permissions or is the bot
            if (message.author.guild_permissions.administrator or message.author.id == 692926265405079632) or message.author == bot.user:
                #await message.channel.purge(limit=10, check=lambda m: m.author == bot.user)
                
                async for m in message.channel.history(limit=5):
                    if m.author == bot.user and (m.content.lower() == "sb" or m.content.lower() == "startbutton"):
                        try: await m.delete()
                        except: pass
                        
                game_session = await get_game_session_by_guild_id(message.guild.id)
                if game_session:
                    await create_button_message(game_session['game_id'], bot)
                    logger.info(f"Button game already started in {message.guild.name}")
                else:
                    logger.info(f"Starting button game in {message.guild.name}")
                    start_time = datetime.datetime.now(timezone.utc)
                    timer_duration = message.content.split(" ")[1] if len(message.content.split(" ")) > 2 else config['timer_duration']
                    cooldown_duration = message.content.split(" ")[2] if len(message.content.split(" ")) > 2 else config['cooldown_duration']
                    chat_channel_id = message.content.split(" ")[3] if len(message.content.split(" ")) > 3 else message.channel.id
                    
                    admin_role_id = 0
                    try:
                        admin_role = nextcord.utils.get(message.guild.roles, name='Button Master')
                        if not admin_role: admin_role = await message.guild.create_role(name='Button Master')
                        if not admin_role in message.author.roles: await message.author.add_roles(admin_role)
                        admin_role_id = admin_role.id
                    except Exception as e:
                        tb = traceback.format_exc()
                        logger.error(f'Error adding role: {e}, {tb}')
                        logger.info('Skipping role addition...')
                    
                    game_id = create_game_session(admin_role_id, message.guild.id, message.channel.id, chat_channel_id, start_time, timer_duration, cooldown_duration)
                    
                    game_session = await get_game_session_by_id(game_id)
                    game_sessions_as_dict = await game_sessions_dict()
                    if game_sessions_as_dict:
                        game_sessions_as_dict[game_id] = game_session
                    else:
                        game_sessions_as_dict = {game_id: game_session}

                    update_local_game_sessions()
                    
                    if game_id in paused_games: 
                        try:
                            paused_games.remove(game_id)
                            logger.info(f'Game session {game_id} removed from paused games.')
                        except Exception as e:
                            tb = traceback.format_exc()
                            logger.error(f'Error removing game session from paused games: {e}, {tb}')
                            pass
                    
                    await setup_roles(message.guild.id, bot)
                    update_local_game_sessions()
                    await create_button_message(game_id, bot)
                
                if menu_timer and not menu_timer.update_timer_task.is_running():
                    logger.info('Starting update timer task...')
                    menu_timer.update_timer_task.start()
                elif not menu_timer:
                    logger.error('Menu timer not found.')
        
            else: await message.channel.send('You do not have permission to start the button game.')
                
            try: await message.delete()
            except: pass

        elif message.content.lower() == 'insert_first_click': #insert_first_click from database
            try:
                user_id = message.author.id
                game_session = await get_game_session_by_guild_id(message.guild.id)
                username = message.author.display_name if message.author.display_name else message.author.name
                now = 43200
                result = insert_first_click(game_session['game_id'], user_id, username, now)
                if result:
                    logger.info(f'First click inserted for {username}')
                    await message.channel.send(f'First click inserted for {username}')
                else:
                    logger.error('Failed to insert first click.')
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error inserting first click: {e}, {tb}')
        
        elif message.content.lower().startswith(('myrank', 'rank', 'urrank')) or (is_brain_rot(message.content.lower()) == 1):
            await message.add_reaction('⏳')
            game_session = await get_game_session_by_guild_id(message.guild.id)
            if not game_session:
                await message.channel.send('No active game session found in this server!')
                return

            # Determine target user
            target_user_id = message.author.id
            is_other_user = False
            
            # Check if this is a urrank command or if additional arguments are provided
            command_parts = message.content.lower().split()
            if len(command_parts) > 1:
                # Check for user mention
                if len(message.mentions) > 0:
                    target_user_id = message.mentions[0].id
                    is_other_user = True
                # Handle the existing ID extraction from message content
                elif command_parts[0] != 'urrank' and command_parts[1].startswith('<@') and command_parts[1].endswith('>'):
                    try:
                        target_user_id = int(command_parts[1][2:-1].replace('!', ''))
                        is_other_user = True
                    except ValueError:
                        await message.channel.send('Invalid user mention format!')
                        await message.remove_reaction('⏳', bot.user)
                        return

            try:
                # Get user's clicks for current game session
                query = '''
                    SELECT 
                        bc.timer_value,
                        bc.click_time,
                        (
                            SELECT COUNT(DISTINCT u2.user_id)
                            FROM button_clicks bc2 
                            JOIN users u2 ON bc2.user_id = u2.user_id 
                            WHERE bc2.game_id = %s 
                            AND u2.total_clicks > (
                                SELECT COUNT(*) 
                                FROM button_clicks bc3 
                                WHERE bc3.user_id = %s 
                                AND bc3.game_id = %s
                            )
                        ) + 1 AS user_rank,
                        (
                            SELECT COUNT(DISTINCT user_id) 
                            FROM button_clicks 
                            WHERE game_id = %s
                        ) AS total_players
                    FROM button_clicks bc
                    WHERE bc.game_id = %s 
                    AND bc.user_id = %s
                    ORDER BY bc.click_time
                '''
                params = (game_session['game_id'], target_user_id, game_session['game_id'], 
                        game_session['game_id'], game_session['game_id'], target_user_id)
                logger.info(f"Executing user rank query with params: {params}")
                success = execute_query(query, params)
                if not success: 
                    logger.error('Error retrieving user rank data')
                    await message.channel.send('An error occurred while retrieving rank data!')
                    await message.remove_reaction('⏳', bot.user)
                    await message.add_reaction('❌')
                    return

                clicks = success

                def Counter(emojis):
                    counts = {}
                    for emoji in emojis:
                        if emoji in counts:
                            counts[emoji] += 1
                        else:
                            counts[emoji] = 1
                    return counts

                if clicks:
                    color_emojis = [get_color_emoji(timer_value, game_session['timer_duration']) for timer_value, _, _, _ in clicks]
                    color_counts = Counter(color_emojis)
                    # Fix: Calculate time claimed as the elapsed time from max timer, not remaining time
                    total_claimed_time = sum(max(0, game_session['timer_duration'] - timer_value) for timer_value, _, _, _ in clicks)
                    rank = clicks[0][2]  # Get rank from first row
                    total_players = clicks[0][3]  # Get total players from first row

                    if not is_other_user:
                        user_name = message.author.display_name if message.author.display_name else message.author.name
                    else:
                        target_user = await bot.fetch_user(target_user_id)
                        if target_user is None:
                            await message.channel.send('Unable to find that user!')
                            await message.remove_reaction('⏳', bot.user)
                            return
                        user_name = target_user.display_name if hasattr(target_user, 'display_name') else target_user.name
                    
                    # Create main embed with summary information
                    embed = nextcord.Embed(title=f'Heroic Journey of {user_name}')
                    
                    # Color summary
                    color_summary = ', '.join(f'{emoji} x{count}' for emoji, count in color_counts.items())
                    embed.add_field(name='🎨 Color Summary', value=color_summary, inline=False)
                    embed.add_field(name='⏱☘ Total Time Claimed*', value=format_time(total_claimed_time), inline=False)
                    
                    # Split emoji sequence if it's too long
                    max_emojis_per_embed = 200  # Adjust as needed
                    
                    if len(color_emojis) <= max_emojis_per_embed:
                        # If we can fit all emojis in one embed
                        emoji_sequence = ' '.join(color_emojis)
                        embed.add_field(name='🎚 Click History', value=emoji_sequence, inline=False)
                        await message.channel.send(embed=embed)
                    else:
                        # Send main embed without emoji sequence first
                        footer_text = "Total time claimed represents the amount of time "
                        footer_text += "you've" if not is_other_user else "they've"
                        footer_text += " prevented the clock from reaching zero."
                        embed.set_footer(text=footer_text)
                        await message.channel.send(embed=embed)
                        
                        # Then send emoji sequence in multiple embeds
                        for i in range(0, len(color_emojis), max_emojis_per_embed):
                            chunk = color_emojis[i:i+max_emojis_per_embed]
                            emoji_sequence = ' '.join(chunk)
                            
                            history_embed = nextcord.Embed(
                                title=f'Click History {i//max_emojis_per_embed + 1}/{(len(color_emojis) + max_emojis_per_embed - 1)//max_emojis_per_embed}',
                                color=embed.color
                            )
                            history_embed.add_field(name='Clicks', value=emoji_sequence, inline=False)
                            
                            await message.channel.send(embed=history_embed)
                else:
                    msg = 'Alas, noble warrior, '
                    if not is_other_user:
                        msg += 'your journey has yet to begin. Step forth and make your mark upon the button!'
                    else:
                        msg += 'their journey has yet to begin. They must step forth and make their mark upon the button!'
                    await message.channel.send(msg)

            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error retrieving user rank: {e}\n{tb}')
                msg = 'An error occurred while retrieving '
                msg += 'your' if not is_other_user else 'the user\'s'
                msg += ' rank. The button spirits are displeased!'
                await message.channel.send(msg)
            finally:
                try:
                    await message.remove_reaction('⏳', bot.user)
                except:
                    pass

        elif message.content.lower() == 'whoready':
            await message.add_reaction('⏳')
            try:
                # Get the game session for this guild
                game_session = await get_game_session_by_guild_id(message.guild.id)
                if not game_session:
                    await message.channel.send('No active game session found in this server!')
                    await message.remove_reaction('⏳', bot.user)
                    return
        
                cooldown_duration = float(game_session['cooldown_duration'])
                cooldown_seconds = int(cooldown_duration * 3600)
                now_utc = datetime.datetime.now(datetime.timezone.utc)
        
                # Get the last 10 unique users who clicked this button in this game
                query = '''
                    SELECT bc.user_id, MAX(bc.click_time) as last_click_time
                    FROM button_clicks bc
                    WHERE bc.game_id = %s
                    GROUP BY bc.user_id
                    ORDER BY last_click_time DESC
                    LIMIT 10
                '''
                params = (game_session['game_id'],)
                last_10 = execute_query(query, params)
        
                if not last_10:
                    await message.channel.send('No clicks found for this game session!')
                    await message.remove_reaction('⏳', bot.user)
                    return
        
                ready_users = []
                for user_id, last_click_time in last_10:
                    time_since_last_click = (now_utc - last_click_time.replace(tzinfo=datetime.timezone.utc)).total_seconds()
                    if time_since_last_click >= cooldown_seconds:
                        try:
                            user = await bot.fetch_user(user_id)
                            user_name = user.display_name if hasattr(user, 'display_name') else user.name
                        except:
                            user_name = f"User {user_id}"
                        ready_users.append((user_name, last_click_time))
        
                if not ready_users:
                    await message.channel.send('No one among the last 10 clickers is currently ready to click!')
                    await message.remove_reaction('⏳', bot.user)
                    return
        
                details = [f"{idx+1}. {user_name} (last clicked <t:{int(last_click_time.timestamp())}:R>)"
                           for idx, (user_name, last_click_time) in enumerate(ready_users)]
        
                embed = nextcord.Embed(
                    title="Who is Ready? (Among Last 10 Clickers)",
                    description="Here are the last 10 unique players who are ready to click:\n\n" + "\n".join(details),
                    color=nextcord.Color.green()
                )
                await message.channel.send(embed=embed)
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error checking ready players: {e}, {tb}')
                await message.channel.send('An error occurred while checking who is ready.')
            finally:
                await message.remove_reaction('⏳', bot.user)

        
        elif message.content.lower() == 'checkothers' or message.content.lower() == 'cooldowns':
            await message.add_reaction('⏳')
            try:
                # Get the game session for this guild
                game_session = await get_game_session_by_guild_id(message.guild.id)
                if not game_session:
                    await message.channel.send('No active game session found in this server!')
                    await message.remove_reaction('⏳', bot.user)
                    return

                cooldown_duration = float(game_session['cooldown_duration'])
                cooldown_seconds = int(cooldown_duration * 3600)
                now_utc = datetime.datetime.now(datetime.timezone.utc)

                # Get the last 10 unique users who clicked this button in this game
                query = '''
                    SELECT bc.user_id, MAX(bc.click_time) as last_click_time
                    FROM button_clicks bc
                    WHERE bc.game_id = %s
                    GROUP BY bc.user_id
                    ORDER BY last_click_time DESC
                    LIMIT 10
                '''
                params = (game_session['game_id'],)
                last_10 = execute_query(query, params)

                if not last_10:
                    await message.channel.send('No clicks found for this game session!')
                    await message.remove_reaction('⏳', bot.user)
                    return

                ready_count = 0
                details = []
                for user_id, last_click_time in last_10:
                    # Calculate time since last click
                    time_since_last_click = (now_utc - last_click_time.replace(tzinfo=datetime.timezone.utc)).total_seconds()
                    if time_since_last_click >= cooldown_seconds:
                        ready_count += 1
                        status = "✅ Ready"
                    else:
                        status = f"❌ {int((cooldown_seconds - time_since_last_click)//60)} min left"
                    # Optionally, get user name
                    try:
                        user = await bot.fetch_user(user_id)
                        user_name = user.display_name if hasattr(user, 'display_name') else user.name
                    except:
                        user_name = f"User {user_id}"
                    details.append(f"{user_name}: {status}")

                embed = nextcord.Embed(
                    title="Last 10 Unique Players - Ready Status",
                    description=f"Out of the last 10 unique players who clicked the button:\n"
                                f"**{ready_count}** have a click ready!\n\n" +
                                "\n".join(details)
                )
                await message.channel.send(embed=embed)
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error checking last 10 players cooldown: {e}, {tb}')
                await message.channel.send('An error occurred while checking the last 10 players.')
            finally:
                await message.remove_reaction('⏳', bot.user)

        elif message.content.lower().startswith('goonboard') or message.content.lower().startswith('clickquest') :
            await message.add_reaction('⏳')
            try:
                # Parse command arguments
                args = message.content.lower().split()
                
                # Default to current month if no month specified
                target_year = datetime.datetime.now(timezone.utc).year
                target_month = datetime.datetime.now(timezone.utc).month
                
                # Parse month argument if provided
                if len(args) > 1:
                    month_arg = args[1]
                    
                    # Handle different date formats: "2023-01" or "January" or "jan"
                    if '-' in month_arg:
                        try:
                            # Format: YYYY-MM
                            year_str, month_str = month_arg.split('-')
                            target_year = int(year_str)
                            target_month = int(month_str)
                        except ValueError:
                            await message.channel.send('Invalid date format. Use YYYY-MM (e.g., 2023-01) or month name (e.g., January)')
                            await message.remove_reaction('⏳', bot.user)
                            return
                    else:
                        # Format: Month name
                        month_names = {
                            'january': 1, 'jan': 1,
                            'february': 2, 'feb': 2,
                            'march': 3, 'mar': 3,
                            'april': 4, 'apr': 4,
                            'may': 5,
                            'june': 6, 'jun': 6,
                            'july': 7, 'jul': 7,
                            'august': 8, 'aug': 8,
                            'september': 9, 'sep': 9, 'sept': 9,
                            'october': 10, 'oct': 10,
                            'november': 11, 'nov': 11,
                            'december': 12, 'dec': 12
                        }
                        
                        if month_arg in month_names:
                            target_month = month_names[month_arg]
                            
                            # If month without year, use current year or previous year if the specified month is in the future
                            current_month = datetime.datetime.now(timezone.utc).month
                            if target_month > current_month:
                                target_year = datetime.datetime.now(timezone.utc).year - 1
                        else:
                            await message.channel.send('Invalid month name. Use full month name or abbreviation (e.g., January or Jan)')
                            await message.remove_reaction('⏳', bot.user)
                            return
                
                # Dictionary of previous monthly winners (user_id: month_won)
                previous_winners = {
                    213676416049348608: "December 2024",  # Silver
                    1125418575230947429: "May 2024",  # MightyNut
                    298320373542420482: "June 2024",  # Honeybee
                }
                
                # Get all game sessions for the guild
                game_sessions_query = '''
                    SELECT id 
                    FROM game_sessions 
                    WHERE guild_id = %s
                '''
                game_sessions = execute_query(game_sessions_query, (message.guild.id,))
                
                if not game_sessions:
                    await message.channel.send('No game sessions found for this server!')
                    await message.remove_reaction('⏳', bot.user)
                    return
                    
                # Extract game IDs
                game_ids = [gs[0] for gs in game_sessions]
                game_ids_placeholders = ', '.join(['%s'] * len(game_ids))
                
                # Query for monthly time claimed data with color distribution (NO EXCLUSIONS)
                query = f'''
                    SELECT 
                        u.user_name,
                        u.user_id,
                        SUM(GREATEST(0, gs.timer_duration - bc.timer_value)) AS time_claimed,
                        COUNT(*) AS total_clicks,
                        SUM(CASE WHEN ROUND((bc.timer_value / gs.timer_duration) * 100, 2) >= 83.33 THEN 1 ELSE 0 END) AS purple_clicks,
                        SUM(CASE WHEN ROUND((bc.timer_value / gs.timer_duration) * 100, 2) >= 66.67 AND ROUND((bc.timer_value / gs.timer_duration) * 100, 2) < 83.33 THEN 1 ELSE 0 END) AS blue_clicks,
                        SUM(CASE WHEN ROUND((bc.timer_value / gs.timer_duration) * 100, 2) >= 50.00 AND ROUND((bc.timer_value / gs.timer_duration) * 100, 2) < 66.67 THEN 1 ELSE 0 END) AS green_clicks,
                        SUM(CASE WHEN ROUND((bc.timer_value / gs.timer_duration) * 100, 2) >= 33.33 AND ROUND((bc.timer_value / gs.timer_duration) * 100, 2) < 50.00 THEN 1 ELSE 0 END) AS yellow_clicks,
                        SUM(CASE WHEN ROUND((bc.timer_value / gs.timer_duration) * 100, 2) >= 16.67 AND ROUND((bc.timer_value / gs.timer_duration) * 100, 2) < 33.33 THEN 1 ELSE 0 END) AS orange_clicks,
                        SUM(CASE WHEN ROUND((bc.timer_value / gs.timer_duration) * 100, 2) < 16.67 THEN 1 ELSE 0 END) AS red_clicks
                    FROM button_clicks bc
                    JOIN game_sessions gs ON bc.game_id = gs.id
                    JOIN users u ON bc.user_id = u.user_id
                    WHERE bc.game_id IN ({game_ids_placeholders})
                    AND YEAR(bc.click_time) = %s 
                    AND MONTH(bc.click_time) = %s
                    GROUP BY u.user_name, u.user_id
                    ORDER BY time_claimed DESC
                    LIMIT 20
                '''
                
                # Create parameters list with game IDs, year, month (no excluded users)
                params = game_ids + [target_year, target_month]
                
                time_claimed_data = execute_query(query, params)
                
                if not time_claimed_data:
                    month_name = datetime.date(target_year, target_month, 1).strftime('%B %Y')
                    await message.channel.send(f'No click data found for {month_name}!')
                    await message.remove_reaction('⏳', bot.user)
                    return
                    
                # Calculate total time claimed for the month
                total_time_claimed = sum(data[2] for data in time_claimed_data)
                month_name = datetime.date(target_year, target_month, 1).strftime('%B %Y')
        
                # Create embed with clearer explanation
                if message.guild.id == 1081299949792272388:
                    embed = nextcord.Embed(
                        title=f'🎁 VRC+ Giveaway: {month_name}',
                        description=(
                            f"**Time Claimed Quest!**\n" 
                            f"Compete for VRC+ by having the most time saved from the clock hitting zero by clicking (shown as **hours : minutes : seconds**).\n"
                            f"*Example: If a 12-hour timer shows 04:00:00 when you click, you've claimed 8 hours!*\n\n"
                            f"🏆 **Previous winners are shown but ineligible for new prizes**\n"
                            f"*Total time claimed during {month_name}: **{format_time(total_time_claimed)}** by ALL players*"
                        )
                    )
                else:
                    embed = nextcord.Embed(
                        title=f'Time Claimed Quest! {month_name}',
                        description=(
                            f"Compete to see who can claim the most time from the clock hitting zero by clicking (shown as **hours : minutes : seconds**).\n"
                            f"*Example: If a 12-hour timer shows 04:00:00 when you click, you've claimed 8 hours!*\n\n"
                            f"🏆 **Previous top performers are shown for reference**\n"
                            f"*Total time claimed during {month_name}: **{format_time(total_time_claimed)}** by ALL players*"
                        )
                    )
                
                # Set month-themed color
                month_colors = {
                    1: (65, 105, 225),   # January - Blue
                    2: (255, 105, 180),  # February - Pink
                    3: (50, 205, 50),    # March - Green
                    4: (218, 165, 32),   # April - Goldenrod
                    5: (138, 43, 226),   # May - Purple
                    6: (255, 215, 0),    # June - Gold
                    7: (255, 69, 0),     # July - Red-Orange
                    8: (0, 191, 255),    # August - Sky Blue
                    9: (210, 105, 30),   # September - Brown
                    10: (255, 140, 0),   # October - Orange
                    11: (139, 69, 19),   # November - Brown
                    12: (220, 20, 60)    # December - Red
                }
                
                if target_month in month_colors:
                    embed.color = nextcord.Color.from_rgb(*month_colors[target_month])
                
                # Helper function to get display name
                def get_display_name(username, user_id):
                    try:
                        # First try to get member object
                        member = message.guild.get_member(user_id)
                        if member:
                            return member.display_name or member.name.replace(".", "")
                        return username.replace(".", "")
                    except Exception as e:
                        logger.warning(f"Error getting display name for {username} ({user_id}): {e}")
                        return username.replace(".", "")
                
                # Helper functions for winner tracking
                def is_previous_winner(user_id):
                    return user_id in previous_winners
                
                def get_winner_status(user_id):
                    if user_id in previous_winners:
                        return f" 🏆 (Won {previous_winners[user_id]})"
                    return ""
                    
                # Format leaderboard entries with winner status
                leaderboard_text = ""
                eligible_rank = 1
                overall_rank = 1
                
                for username, user_id, time_claimed, total_clicks, purple_clicks, blue_clicks, green_clicks, yellow_clicks, orange_clicks, red_clicks in time_claimed_data:
                    # Get display name for the user
                    display_name = get_display_name(username, user_id)
                    
                    # Format color summary with only non-zero counts
                    color_parts = []
                    if purple_clicks > 0: color_parts.append(f"🟣 x{purple_clicks}")
                    if blue_clicks > 0: color_parts.append(f"🔵 x{blue_clicks}")
                    if green_clicks > 0: color_parts.append(f"🟢 x{green_clicks}")
                    if yellow_clicks > 0: color_parts.append(f"🟡 x{yellow_clicks}")
                    if orange_clicks > 0: color_parts.append(f"🟠 x{orange_clicks}")
                    if red_clicks > 0: color_parts.append(f"🔴 x{red_clicks}")
                    
                    color_summary = ", ".join(color_parts)
                    
                    # Check if user is a previous winner
                    winner_status = get_winner_status(user_id)
                    is_winner = is_previous_winner(user_id)
                    
                    # Format the rank display
                    if is_winner:
                        rank_display = f"#{overall_rank} (Prev. Winner)"
                        user_entry = f"~~{rank_display}. {display_name}~~ - {format_time(time_claimed)}{winner_status} | ({color_summary})\n"
                    else:
                        rank_display = f"#{eligible_rank}"
                        user_entry = f"{rank_display}. {display_name} - {format_time(time_claimed)} | ({color_summary})\n"
                        eligible_rank += 1
                    
                    leaderboard_text += user_entry
                    overall_rank += 1
                
                # Add leaderboard to embed
                embed.add_field(
                    name="Leaderboard",
                    value=leaderboard_text,
                    inline=False
                )
                
                # Add footer with command help
                guild_id = message.guild.id
                footer_text="Use 'goonboard [month-year]' to view other months. Example: 'goonboard january' or 'goonboard 2023-02'"
                if guild_id != 1081299949792272388:
                    footer_text = "Use 'clickquest [month-year]' to view other months. Example: 'clickquest january' or 'clickquest 2023-02'"
        
                embed.set_footer(text=footer_text)
                
                # Send the embed
                await message.channel.send(embed=embed)
                
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error retrieving monthly time claimed data: {e}\n{tb}')
                await message.channel.send('An error occurred while retrieving the monthly leaderboard!')
            finally:
                await message.remove_reaction('⏳', bot.user)

        elif message.content.lower() == 'showclicks' or is_brain_rot(message.content.lower()) == 2:
            await message.add_reaction('🔄')
            try:
                game_session = await get_game_session_by_guild_id(message.guild.id)
                if not game_session:
                    await message.channel.send('No active game session found in this server!')
                    return

                # Get all clicks for the current game session ordered by click time (oldest first)
                query = '''
                    SELECT timer_value 
                    FROM button_clicks 
                    WHERE game_id = %s 
                    ORDER BY click_time ASC
                '''
                params = (game_session['game_id'],)
                success = execute_query(query, params)
                
                if not success:
                    logger.error('Failed to retrieve click data')
                    await message.channel.send('An error occurred while retrieving click data!')
                    await message.remove_reaction('🔄', bot.user)
                    return

                clicks = success
                if not clicks:
                    await message.channel.send('No clicks found for this game session!')
                    await message.remove_reaction('🔄', bot.user)
                    return

                # Convert timer values to emojis
                click_emojis = [get_color_emoji(click[0], game_session['timer_duration']) for click in clicks]
                
                # Count occurrences of each emoji for the summary
                emoji_counts = {
                    '🟣': click_emojis.count('🟣'),  # Purple
                    '🔵': click_emojis.count('🔵'),  # Blue
                    '🟢': click_emojis.count('🟢'),  # Green
                    '🟡': click_emojis.count('🟡'),  # Yellow
                    '🟠': click_emojis.count('🟠'),  # Orange
                    '🔴': click_emojis.count('🔴')   # Red
                }

                # Send summary first
                summary_embed = nextcord.Embed(
                    title=f'Click Summary for Game #{game_session["game_id"]}',
                    description='\n'.join([f'{emoji}: {count}' for emoji, count in emoji_counts.items() if count > 0]) +
                              f'\n\nTotal Clicks: {len(click_emojis)}'
                )
                await message.channel.send(embed=summary_embed)

                # Create rows of 10 emojis each
                rows = []
                for i in range(0, len(click_emojis), 10):
                    rows.append(''.join(click_emojis[i:i+10]))

                # Send rows in chunks of 15 rows per embed
                MAX_ROWS_PER_EMBED = 15
                current_page = 1
                total_pages = (len(rows) + MAX_ROWS_PER_EMBED - 1) // MAX_ROWS_PER_EMBED

                for i in range(0, len(rows), MAX_ROWS_PER_EMBED):
                    chunk = rows[i:i+MAX_ROWS_PER_EMBED]
                    embed = nextcord.Embed(
                        title=f'All Clicks (Page {current_page}/{total_pages})',
                        description='\n'.join(chunk)
                    )
                    await message.channel.send(embed=embed)
                    current_page += 1
                    # Add a small delay to avoid rate limiting
                    await asyncio.sleep(0.5)

            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error showing clicks: {e}\n{tb}')
                await message.channel.send('An error occurred while showing clicks!')
            finally:
                await message.remove_reaction('🔄', bot.user)
        
        elif message.content.lower().startswith('edging'):
            await message.add_reaction('⏳')
            game_session = await get_game_session_by_guild_id(message.guild.id)
            if not game_session:
                await message.channel.send('No active game session found in this server!')
                return

            try:
                # Calculate the time window (5 minutes, or 1/6 of the total time if less than 30 minutes)
                five_minutes_in_seconds = 300
                boundary_threshold_seconds = min(five_minutes_in_seconds, game_session['timer_duration'] / 36)  # 1/6 of each color segment
                
                # Convert time window to percentage of total timer
                boundary_threshold_percent = (boundary_threshold_seconds / game_session['timer_duration']) * 100
                
                # Query to find clicks near color transitions
                query = '''
                    WITH click_percentages AS (
                        SELECT 
                            u.user_name,
                            bc.timer_value,
                            bc.click_time,
                            ROUND((bc.timer_value / %s) * 100, 2) as percentage,
                            ABS(ROUND((bc.timer_value / %s) * 100, 2) - 16.67) as dist_to_red,
                            ABS(ROUND((bc.timer_value / %s) * 100, 2) - 33.33) as dist_to_orange,
                            ABS(ROUND((bc.timer_value / %s) * 100, 2) - 50.00) as dist_to_yellow,
                            ABS(ROUND((bc.timer_value / %s) * 100, 2) - 66.67) as dist_to_green,
                            ABS(ROUND((bc.timer_value / %s) * 100, 2) - 83.33) as dist_to_blue
                        FROM button_clicks bc
                        JOIN users u ON bc.user_id = u.user_id
                        WHERE bc.game_id = %s
                    )
                    SELECT 
                        user_name,
                        timer_value,
                        click_time,
                        percentage,
                        CASE
                            WHEN dist_to_red <= %s THEN CONCAT('🟠↔️🔴 (', ROUND(dist_to_red, 3), '%%)')
                            WHEN dist_to_orange <= %s THEN CONCAT('🟡↔️🟠 (', ROUND(dist_to_orange, 3), '%%)')
                            WHEN dist_to_yellow <= %s THEN CONCAT('🟢↔️🟡 (', ROUND(dist_to_yellow, 3), '%%)')
                            WHEN dist_to_green <= %s THEN CONCAT('🔵↔️🟢 (', ROUND(dist_to_green, 3), '%%)')
                            WHEN dist_to_blue <= %s THEN CONCAT('🟣↔️🔵 (', ROUND(dist_to_blue, 3), '%%)')
                        END as edge_info,
                        LEAST(
                            dist_to_red,
                            dist_to_orange,
                            dist_to_yellow,
                            dist_to_green,
                            dist_to_blue
                        ) as min_distance
                    FROM click_percentages
                    WHERE 
                        dist_to_red <= %s OR
                        dist_to_orange <= %s OR
                        dist_to_yellow <= %s OR
                        dist_to_green <= %s OR
                        dist_to_blue <= %s
                    ORDER BY min_distance ASC
                    LIMIT 10
                '''
                params = (
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['game_id'],
                    boundary_threshold_percent,
                    boundary_threshold_percent,
                    boundary_threshold_percent,
                    boundary_threshold_percent,
                    boundary_threshold_percent,
                    boundary_threshold_percent,
                    boundary_threshold_percent,
                    boundary_threshold_percent
                )
                
                logger.info(f"Executing edge stats query with boundary threshold of {boundary_threshold_seconds} seconds ({boundary_threshold_percent}%)")
                results = execute_query(query, params)
                
                # Fix: Check if results is a valid iterable before assigning to edge_stats
                if results is not None and not isinstance(results, bool):
                    edge_stats = results
                else:
                    logger.warning(f"Query returned non-iterable result: {results}")
                    edge_stats = []  # Use empty list as fallback
                
                # Create main embed with introduction
                main_embed = nextcord.Embed(
                    title='🎯 Living on the Edge 🎯',
                    description=f"Game #{game_session['game_id']}'s closest calls - clicks within {format_time(boundary_threshold_seconds)} of a color transition!"
                )
                
                # If we have valid edge stats, populate the embed
                if edge_stats and len(edge_stats) > 0:
                    # Set color based on the closest edge
                    color = get_color_state(edge_stats[0][1], game_session['timer_duration'])
                    main_embed.color = nextcord.Color.from_rgb(*color)
                    
                    await message.channel.send(embed=main_embed)
                    
                    # Split results into chunks of 5 for better readability
                    chunk_size = 5
                    for i in range(0, len(edge_stats), chunk_size):
                        chunk = edge_stats[i:i+chunk_size]
                        
                        edge_details = ""
                        for user_name, timer_value, click_time, percentage, edge_info, _ in chunk:
                            time_str = format_time(timer_value)
                            edge_details += f"**{user_name}**\n"
                            edge_details += f"Time: {time_str} ({percentage}%)\n"
                            edge_details += f"Edge: {edge_info}\n"
                            edge_details += f"Clicked <t:{int(click_time.timestamp())}:R>\n"
                            edge_details += "─────────────\n"
                        
                        # Create separate embed for each chunk
                        chunk_embed = nextcord.Embed(
                            title=f'🎭 Edge Masters (#{i//chunk_size + 1}) 🎭',
                            color=main_embed.color
                        )
                        chunk_embed.add_field(
                            name='Close Calls',
                            value=edge_details,
                            inline=False
                        )
                        
                        await message.channel.send(embed=chunk_embed)
                else:
                    # If no edge stats, just send a single embed
                    main_embed.add_field(
                        name='🎭 Edge Masters 🎭',
                        value=f"No one has clicked within {format_time(boundary_threshold_seconds)} of a color transition yet!",
                        inline=False
                    )
                    main_embed.color = nextcord.Color.from_rgb(106, 76, 147)
                    
                    await message.channel.send(embed=main_embed)

            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error retrieving edge stats: {e}, {tb}')
                await message.channel.send('An error occurred while calculating edge stats. The measurements are unclear!')
            finally:
                await message.remove_reaction('⏳', bot.user)


        elif (message.content.lower().startswith('l1') and len(message.content.lower()) == 2) or ('leaderboard1' in message.content.lower() and len(message.content.split()) <= 2 and message.content.split()[0].lower() == 'leaderboard1') or (is_brain_rot(message.content.lower()) == 3):
            await message.add_reaction('⚡')
            game_session = await get_game_session_by_guild_id(message.guild.id)
            if not game_session:
                await message.channel.send('No active game session found in this server!')
                return
            
            click_count = check_button_clicks(game_session['game_id'])
            if click_count == 0:
                logger.warning(f"No button clicks found for game {game_session['game_id']} - this may explain empty leaderboard")
            
            try:
                # Query to get collective time claimed for each color tier
                query = '''
                    SELECT 
                        CASE
                            WHEN ROUND((bc.timer_value / %s) * 100, 2) <= 16.67 THEN 'Red'
                            WHEN ROUND((bc.timer_value / %s) * 100, 2) <= 33.33 THEN 'Orange'
                            WHEN ROUND((bc.timer_value / %s) * 100, 2) <= 50.00 THEN 'Yellow'
                            WHEN ROUND((bc.timer_value / %s) * 100, 2) <= 66.67 THEN 'Green'
                            WHEN ROUND((bc.timer_value / %s) * 100, 2) <= 83.33 THEN 'Blue'
                            ELSE 'Purple'
                        END as tier_name,
                        COUNT(*) as click_count,
                        SUM(GREATEST(0, %s - bc.timer_value)) as total_time_claimed,
                        COUNT(DISTINCT bc.user_id) as unique_clickers,
                        SUM(GREATEST(0, %s - bc.timer_value)) / COUNT(*) as avg_claimed_per_click,
                        SUM(GREATEST(0, %s - bc.timer_value)) / COUNT(DISTINCT bc.user_id) as avg_claimed_per_user
                    FROM button_clicks bc
                    WHERE bc.game_id = %s
                    GROUP BY 
                        CASE
                            WHEN ROUND((bc.timer_value / %s) * 100, 2) <= 16.67 THEN 'Red'
                            WHEN ROUND((bc.timer_value / %s) * 100, 2) <= 33.33 THEN 'Orange'
                            WHEN ROUND((bc.timer_value / %s) * 100, 2) <= 50.00 THEN 'Yellow'
                            WHEN ROUND((bc.timer_value / %s) * 100, 2) <= 66.67 THEN 'Green'
                            WHEN ROUND((bc.timer_value / %s) * 100, 2) <= 83.33 THEN 'Blue'
                            ELSE 'Purple'
                        END
                    ORDER BY MIN(ROUND((bc.timer_value / %s) * 100, 2)) ASC
                '''
                params = (
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],  # For total_time_claimed
                    game_session['timer_duration'],  # For avg_claimed_per_click
                    game_session['timer_duration'],  # For avg_claimed_per_user
                    game_session['game_id'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration']
                )
                
                logger.info(f"Executing tier stats query: {query}")
                logger.info(f"With params: {params}")
                results = execute_query(query, params)
                tier_stats = results if results else []

                # Add emoji mapping
                emoji_map = {
                    'Red': '🔴',
                    'Orange': '🟠',
                    'Yellow': '🟡',
                    'Green': '🟢',
                    'Blue': '🔵',
                    'Purple': '🟣'
                }

                # Calculate totals
                total_time_claimed = sum(tier[2] if tier[2] else 0 for tier in tier_stats)
                total_heroes = max((tier[3] for tier in tier_stats), default=0)
                total_clicks = sum(tier[1] if tier[1] else 0 for tier in tier_stats)

                # Create single consolidated embed
                main_embed = nextcord.Embed(
                    title='🏛️ Time Guardians\' Chronicle 🏛️',
                    description=f"Game #{game_session['game_id']} collective achievements:",
                    color=nextcord.Color.from_rgb(106, 76, 147)
                )

                # Add summary stats
                summary = f"**⏱️ Total Time Claimed: {format_time(total_time_claimed)}**\n"
                summary += f"**👥 Total Heroes: {total_heroes}** | **🖱️ Total Clicks: {total_clicks}**\n\n"
                
                # Add tier details in compact format
                tier_details = ""
                for tier in tier_stats:
                    tier_name, clicks, time_claimed, unique_clickers, avg_per_click, avg_per_user = tier
                    emoji = emoji_map.get(tier_name, '')
                    time_claimed_formatted = format_time(time_claimed) if time_claimed else "0:00:00"
                    click_pct = round(clicks/total_clicks*100 if total_clicks else 0, 1)
                    
                    tier_details += f"{emoji} **{tier_name}**: {clicks} clicks ({click_pct}%) • {time_claimed_formatted} claimed • {unique_clickers} heroes\n"
                
                # Check if content fits within character limit (leaving room for footer)
                full_content = summary + tier_details
                if len(main_embed.title) + len(main_embed.description) + len(full_content) > 3200:
                    # Truncate tiers if needed (show top 4 tiers)
                    tier_details = ""
                    shown_tiers = 0
                    for tier in tier_stats:
                        if shown_tiers >= 4:
                            remaining = len(tier_stats) - shown_tiers
                            tier_details += f"... and {remaining} more tiers"
                            break
                        
                        tier_name, clicks, time_claimed, unique_clickers, avg_per_click, avg_per_user = tier
                        emoji = emoji_map.get(tier_name, '')
                        time_claimed_formatted = format_time(time_claimed) if time_claimed else "0:00:00"
                        click_pct = round(clicks/total_clicks*100 if total_clicks else 0, 1)
                        
                        tier_details += f"{emoji} **{tier_name}**: {clicks} clicks ({click_pct}%) • {time_claimed_formatted} • {unique_clickers} heroes\n"
                        shown_tiers += 1

                main_embed.add_field(
                    name='📊 Team Statistics',
                    value=summary + tier_details if tier_details else "No time claimed yet - let's begin our journey together!",
                    inline=False
                )

                main_embed.set_footer(text="Time claimed = difference between timer max and remaining time when clicked")
                await message.channel.send(embed=main_embed)

            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error retrieving leaderboard: {e}, {tb}')
                await message.channel.send('An error occurred while retrieving the leaderboard. The button archives are in disarray!')
            finally:
                await message.remove_reaction('⚡', bot.user)
        
        
        elif (message.content.lower().startswith('l2') and len(message.content.lower()) == 2) or ('leaderboard2' in message.content.lower() and len(message.content.split()) <= 2 and message.content.split()[0].lower() == 'leaderboard2') or (is_brain_rot(message.content.lower()) == 6):
            await message.add_reaction('⚡')
            game_session = await get_game_session_by_guild_id(message.guild.id)
            if not game_session:
                await message.channel.send('No active game session found in this server!')
                return

            num_entries = 5
            if len(message.content.split()) > 1:
                try:
                    num_entries = int(message.content.split(" ")[1])
                    num_entries = min(num_entries, 15)  # Cap at 15 for space
                except ValueError:
                    pass

            try:
                # Get most clicks (MMR-based ranking)
                query = '''
                    SELECT 
                        u.user_name,
                        COUNT(*) AS total_clicks,
                        GROUP_CONCAT(
                            CASE
                                WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 83.33 THEN '🟣'
                                WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 66.67 THEN '🔵'
                                WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 50.00 THEN '🟢'
                                WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 33.33 THEN '🟡'
                                WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 16.67 THEN '🟠'
                                ELSE '🔴'
                            END
                            ORDER BY bc.timer_value
                            SEPARATOR ''
                        ) AS color_sequence,
                        SUM(
                            POWER(2, 5 - FLOOR((bc.timer_value / %s) * 100 / 16.66667)) * 
                            (1 + 
                                CASE 
                                    WHEN (bc.timer_value / %s) * 100 < 33.33 
                                    THEN 1 - (MOD((bc.timer_value / %s) * 100, 16.66667) / 16.66667)
                                    ELSE 1 - ABS(0.5 - (MOD((bc.timer_value / %s) * 100, 16.66667) / 16.66667))
                                END
                            ) * (%s / 43200)
                        ) AS mmr_score
                    FROM button_clicks bc
                    JOIN users u ON bc.user_id = u.user_id
                    WHERE bc.game_id = %s
                    GROUP BY u.user_id
                    ORDER BY mmr_score DESC, total_clicks DESC
                    LIMIT %s
                '''
                params = tuple([game_session['timer_duration']] * 10 + [game_session['game_id'], num_entries])
                most_clicks = execute_query(query, params)

                # Get lowest individual clicks
                query = '''
                    SELECT 
                        u.user_name, 
                        bc.timer_value,
                        CASE
                            WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 83.33 THEN '🟣'
                            WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 66.67 THEN '🔵'
                            WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 50.00 THEN '🟢'
                            WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 33.33 THEN '🟡'
                            WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 16.67 THEN '🟠'
                            ELSE '🔴'
                        END as color_emoji
                    FROM button_clicks bc
                    JOIN users u ON bc.user_id = u.user_id
                    WHERE bc.game_id = %s
                    ORDER BY bc.timer_value
                    LIMIT %s
                '''
                params = tuple([game_session['timer_duration']] * 5 + [game_session['game_id'], num_entries])
                lowest_individual_clicks = execute_query(query, params)

                # Get most time claimed
                query = '''
                    SELECT
                        u.user_name,
                        SUM(
                            CASE 
                                WHEN bc.timer_value <= %s THEN %s - bc.timer_value
                                ELSE 0
                            END
                        ) AS total_time_claimed
                    FROM button_clicks bc
                    JOIN users u ON bc.user_id = u.user_id
                    WHERE bc.game_id = %s
                    GROUP BY u.user_id
                    ORDER BY total_time_claimed DESC
                    LIMIT %s
                '''
                params = (game_session['timer_duration'], game_session['timer_duration'], game_session['game_id'], num_entries)
                most_time_claimed = execute_query(query, params)

                # Helper function to get display name
                def get_display_name(username):
                    try:
                        member = message.guild.get_member_named(username)
                        if member:
                            return member.nick or member.display_name or member.name.replace(".", "")
                        return username.replace(".", "")
                    except:
                        return username.replace(".", "")

                # Create consolidated embed
                embed_color = nextcord.Color.from_rgb(106, 76, 147)
                if lowest_individual_clicks:
                    color = get_color_state(lowest_individual_clicks[0][1], game_session['timer_duration'])
                    embed_color = nextcord.Color.from_rgb(*color)

                main_embed = nextcord.Embed(
                    title='🏆 Player Leaderboards 🏆',
                    description=f"Top {num_entries} heroes of Game #{game_session['game_id']}",
                    color=embed_color
                )

                # Mightiest Clickers (compact format)
                if most_clicks:
                    clickers_text = ""
                    shown_count = 0
                    for user, clicks, seq, mmr_score in most_clicks:
                        if shown_count >= num_entries or len(clickers_text) > 800:  # Character limit check
                            remaining = len(most_clicks) - shown_count
                            if remaining > 0:
                                clickers_text += f"... and {remaining} more"
                            break
                        
                        display_name = get_display_name(user)
                        # Compress color sequence to counts
                        color_counts = []
                        for emoji in ["🟣", "🔵", "🟢", "🟡", "🟠", "🔴"]:
                            count = seq.count(emoji)
                            if count > 0:
                                color_counts.append(f"{emoji}×{count}")
                        
                        color_summary = " ".join(color_counts) if color_counts else "No colors"
                        clickers_text += f"**{display_name}**: {clicks} clicks (MMR: {mmr_score:.1f})\n{color_summary}\n\n"
                        shown_count += 1
                    
                    main_embed.add_field(
                        name='⚔️ Mightiest Clickers',
                        value=clickers_text if clickers_text else 'No data available',
                        inline=False
                    )

                # Swiftest Clicks (compact format)
                if lowest_individual_clicks:
                    swift_text = ""
                    shown_count = 0
                    for user, click_time, color_emoji in lowest_individual_clicks:
                        if shown_count >= num_entries or len(swift_text) > 600:
                            remaining = len(lowest_individual_clicks) - shown_count
                            if remaining > 0:
                                swift_text += f"... and {remaining} more"
                            break
                        
                        display_name = get_display_name(user)
                        swift_text += f"{color_emoji} **{display_name}**: {format_time(click_time)}\n"
                        shown_count += 1
                    
                    main_embed.add_field(
                        name='⚡ Swiftest Clicks',
                        value=swift_text if swift_text else 'No data available',
                        inline=True
                    )

                # Temporal Titans (compact format)
                if most_time_claimed:
                    time_text = ""
                    shown_count = 0
                    for username, time_claimed in most_time_claimed:
                        if shown_count >= num_entries or len(time_text) > 600:
                            remaining = len(most_time_claimed) - shown_count
                            if remaining > 0:
                                time_text += f"... and {remaining} more"
                            break
                        
                        display_name = get_display_name(username)
                        time_text += f"**{display_name}**: {format_time(time_claimed)}\n"
                        shown_count += 1
                    
                    main_embed.add_field(
                        name='⏰ Temporal Titans',
                        value=time_text if time_text else 'No data available',
                        inline=True
                    )

                await message.channel.send(embed=main_embed)

            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error retrieving player leaderboard: {e}, {tb}')
                await message.channel.send('An error occurred while retrieving the player leaderboard. The chronicles are incomplete!')
            finally:
                await message.remove_reaction('⚡', bot.user)
        
        elif message.content.lower() == 'buttonrank' or message.content.lower() == 'br' or is_brain_rot(message.content.lower()) == 4:
            await message.add_reaction('🎯')
            try:
                game_session = await get_game_session_by_guild_id(message.guild.id)
                if not game_session:
                    await message.channel.send('No active game session found in this server!')
                    return

                # Get guild icon first
                guild_icon = get_or_create_guild_icon(message.guild.id)
                
                # Get all game stats - Split the query into smaller parts for better reliability
                # First get basic game stats
                basic_query = '''
                SELECT 
                    gs.id as game_id,
                    gs.guild_id,
                    gs.start_time,
                    COALESCE(gs.end_time, UTC_TIMESTAMP()) as end_time,
                    COUNT(DISTINCT bc.user_id) as total_players,
                    COUNT(bc.id) as total_clicks,
                    TIMESTAMPDIFF(SECOND, gs.start_time, 
                        COALESCE(gs.end_time, UTC_TIMESTAMP())) as duration_seconds,
                    CASE WHEN gs.end_time IS NULL THEN 1 ELSE 0 END as is_active
                FROM game_sessions gs
                LEFT JOIN button_clicks bc ON gs.id = bc.game_id
                GROUP BY gs.id, gs.guild_id, gs.start_time, gs.end_time
                ORDER BY duration_seconds DESC
                '''
                
                # Execute the first part of the query
                results = execute_query(basic_query)
                
                # Check if the query results are valid
                if not results or isinstance(results, bool):
                    logger.error(f"Failed to retrieve game stats. Query returned: {results}")
                    
                    # Fallback: Get basic info for the current game only
                    fallback_query = '''
                    SELECT 
                        gs.id as game_id,
                        gs.guild_id,
                        gs.start_time,
                        COALESCE(gs.end_time, UTC_TIMESTAMP()) as end_time,
                        TIMESTAMPDIFF(SECOND, gs.start_time, COALESCE(gs.end_time, UTC_TIMESTAMP())) as duration_seconds,
                        CASE WHEN gs.end_time IS NULL THEN 1 ELSE 0 END as is_active
                    FROM game_sessions gs
                    WHERE gs.id = %s
                    '''
                    
                    fallback_results = execute_query(fallback_query, (game_session['game_id'],))
                    
                    if fallback_results and not isinstance(fallback_results, bool):
                        # Create a simplified structure for just the current game with default values
                        game_stats = [{
                            'game_id': fallback_results[0][0],
                            'guild_id': fallback_results[0][1],
                            'start_time': fallback_results[0][2],
                            'end_time': fallback_results[0][3],
                            'total_players': 0,  # Default
                            'total_clicks': 0,   # Default 
                            'duration_seconds': fallback_results[0][4],
                            'is_active': fallback_results[0][5],
                            'duration_rank': 1,  # Default
                            'clicks_rank': 1     # Default
                        }]
                    else:
                        await message.channel.send('Error retrieving game rankings! No data available.')
                        await message.remove_reaction('🎯', bot.user)
                        return
                else:
                    # Process normal results
                    game_stats = []
                    rank = 1
                    for row in results:
                        game_stats.append({
                            'game_id': row[0],
                            'guild_id': row[1],
                            'start_time': row[2],
                            'end_time': row[3],
                            'total_players': row[4],
                            'total_clicks': row[5],
                            'duration_seconds': row[6],
                            'is_active': row[7],
                            'duration_rank': rank,
                            'clicks_rank': 1  # We'll calculate this separately if needed
                        })
                        rank += 1
                        
                # Find current game's stats
                current_game = next((g for g in game_stats if g['game_id'] == game_session['game_id']), None)
                if not current_game:
                    # Create a basic entry for the current game
                    current_game = {
                        'game_id': game_session['game_id'],
                        'guild_id': game_session['guild_id'],
                        'start_time': game_session['start_time'],
                        'end_time': None,
                        'total_players': 0,
                        'total_clicks': 0,
                        'duration_seconds': (datetime.datetime.now(timezone.utc) - 
                                        game_session['start_time'].replace(tzinfo=timezone.utc)).total_seconds(),
                        'is_active': True,
                        'duration_rank': len(game_stats) + 1,
                        'clicks_rank': 1
                    }
                    game_stats.append(current_game)

                # Get nearby games
                try:
                    nearby_games = get_nearby_ranks(game_stats, current_game['game_id'])
                    if not nearby_games:
                        nearby_games = [current_game]
                except Exception as e:
                    logger.error(f"Error getting nearby ranks: {e}")
                    nearby_games = [current_game]

                # Create embed
                embed = nextcord.Embed(
                    title=f"{guild_icon} Button Game Legacy {guild_icon}",
                    description=(
                        "Behold, brave adventurers, the chronicles of our realms' buttons! "
                        "Each game stands as a testament to the dedication and valor of its defenders.\n\n"
                        "__Your story continues to unfold...__"
                    ),
                    color=nextcord.Color.from_rgb(106, 76, 147)  # Default color
                )

                # Current Game Status
                duration_str, days = format_game_duration(current_game['duration_seconds'])
                status_text = (
                    f"Your button has stayed alive for **{duration_str}**\n"
                    f"Currently holding position **#{current_game['duration_rank']}** among all buttons\n"
                    f"Protected by **{current_game['total_players']} warriors** with "
                    f"**{current_game['total_clicks']} valiant clicks**\n"
                    f"Click Ranking: **#{current_game['clicks_rank']}**\n\n"
                    f"Status: {'🔥 **ACTIVE**' if current_game['is_active'] else '⚰️ **FALLEN**'}"
                )
                embed.add_field(name="📜 Your Button's Tale", value=status_text, inline=False)

                # Next Target (if active)
                if current_game['duration_rank'] > 1 and current_game['is_active']:
                    next_game = next((g for g in game_stats if g['duration_rank'] == current_game['duration_rank'] - 1), None)
                    if next_game:
                        try:
                            time_needed = calculate_time_to_next_rank(
                                current_game['duration_seconds'],
                                next_game['duration_seconds']
                            )
                            chase_text = (
                                f"Ahead lies Game #{next_game['game_id']}, "
                                f"which endured for {format_game_duration(next_game['duration_seconds'])[0]}\n"
                                f"To surpass their legend, you must survive for {time_needed} more"
                            )
                            embed.add_field(name="🎯 Your Next Challenge", value=chase_text, inline=False)
                        except Exception as e:
                            logger.error(f"Error calculating time to next rank: {e}")
                            # Skip this field if calculation fails

                # Nearby Rankings
                rankings_text = []
                for game in nearby_games:
                    try:
                        duration_str, days = format_game_duration(game['duration_seconds'])
                        
                        # Handle potential errors with guild icon retrieval
                        try:
                            game_guild_icon = get_or_create_guild_icon(game['guild_id'])
                        except Exception as e:
                            logger.warning(f"Error getting guild icon for {game['guild_id']}: {e}")
                            game_guild_icon = "🏆"  # Fallback icon
                        
                        if game['game_id'] == current_game['game_id']:
                            rankings_text.append(
                                f"▼▼▼ YOUR CURRENT GAME ▼▼▼\n"
                                f"➡️ **#{game['duration_rank']} - Game {game['game_id']}** {game_guild_icon}\n"
                                f"   ⏳ {duration_str} | 👥 {game['total_players']} warriors\n"
                                f"   🎯 {game['total_clicks']} clicks\n"
                                f"   {('🔥 Still fighting!' if game['is_active'] else '⚰️ Fallen')}\n"
                                f"▲▲▲ YOUR CURRENT GAME ▲▲▲\n"
                            )
                        else:
                            rankings_text.append(
                                f"#{game['duration_rank']} - Game {game['game_id']} {game_guild_icon}\n"
                                f"⏳ {duration_str} | 👥 {game['total_players']} warriors\n"
                                f"🎯 {game['total_clicks']} clicks\n"
                                f"{('🔥 Still fighting!' if game['is_active'] else '⚰️ Fallen')}\n"
                            )
                    except Exception as e:
                        logger.error(f"Error formatting ranking for game {game['game_id']}: {e}")
                        continue  # Skip this game if formatting fails

                if rankings_text:
                    embed.add_field(
                        name="📊 The Chronicles",
                        value="\n".join(rankings_text),
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="📊 The Chronicles",
                        value="No other games found in the rankings.",
                        inline=False
                    )

                # Footer with commands help
                embed.set_footer(text="Use !seticon <emoji> to change your realm's icon | br or buttonrank to view rankings")
                
                await message.channel.send(embed=embed)
                
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error retrieving button rankings: {e}\n{tb}')
                await message.channel.send('An error occurred while retrieving the rankings!')
            finally:
                await message.remove_reaction('🎯', bot.user)
        elif message.content.lower().startswith('!seticon '):
            if not message.author.guild_permissions.administrator:
                await message.channel.send("Only realm administrators can change the icon!")
                return
                
            new_icon = message.content[9:].strip()
            if update_guild_icon(message.guild.id, new_icon):
                await message.channel.send(f"Your realm's icon has been updated to {new_icon}!")
            else:
                available_icons = " ".join(GUILD_EMOJIS)
                await message.channel.send(f"Invalid icon! Please choose from: {available_icons}")

        elif message.content.lower().startswith('clicklist'):
            await message.add_reaction('⏳')
            try:
                # Parse command arguments
                args = message.content.lower().split()
                limit = 25  # Default limit
                is_global = False
                
                # Process arguments
                for arg in args[1:]:
                    if arg.isdigit():
                        limit = min(int(arg), 100)  # Cap at 100 entries
                    elif arg == 'global':
                        is_global = True

                game_session = await get_game_session_by_guild_id(message.guild.id)
                if not game_session and not is_global:
                    await message.channel.send('No active game session found in this server!')
                    return

                # Construct the SQL query based on whether it's global or server-specific
                if is_global:
                    query = '''
                        SELECT 
                            bc.timer_value,
                            bc.click_time,
                            u.user_name,
                            gs.guild_id,
                            gs.id as game_session_id
                        FROM button_clicks bc
                        JOIN users u ON bc.user_id = u.user_id
                        JOIN game_sessions gs ON bc.game_id = gs.id
                        ORDER BY bc.timer_value ASC
                        LIMIT %s
                    '''
                    params = (limit,)
                else:
                    query = '''
                        SELECT 
                            bc.timer_value,
                            bc.click_time,
                            u.user_name,
                            gs.guild_id,
                            gs.id as game_session_id
                        FROM button_clicks bc
                        JOIN users u ON bc.user_id = u.user_id
                        JOIN game_sessions gs ON bc.game_id = gs.id
                        WHERE bc.game_id = %s
                        ORDER BY bc.timer_value ASC
                        LIMIT %s
                    '''
                    params = (game_session['game_id'], limit)

                results = execute_query(query, params)
                
                if not results:
                    await message.channel.send('No clicks found!')
                    await message.remove_reaction('⏳', bot.user)
                    return

                # Create embed
                title = f"🎯 The Button - {'Global ' if is_global else ''}Lowest {limit} Clicks"
                embed = nextcord.Embed(title=title)
                
                # Process results in chunks to respect Discord's field length limits
                current_field = ""
                field_count = 1
                
                for timer_value, click_time, user_name, guild_id, game_session_id in results:
                    # Get color emoji based on timer value
                    color_emoji = get_color_emoji(timer_value)
                    
                    # Format the click entry
                    entry = f"{color_emoji} **{user_name}** - {format_time(timer_value)} - "
                    entry += f"<t:{int(click_time.timestamp())}:R>\n"
                    
                    if is_global:
                        guild = bot.get_guild(guild_id)
                        guild_name = guild.name if guild else f"Unknown Server ({guild_id})"
                        entry += f"Server: {guild_name}\n"
                    
                    entry += "\n"  # Add spacing between entries
                    
                    # Check if adding this entry would exceed Discord's field limit
                    if len(current_field) + len(entry) > 1024:
                        embed.add_field(
                            name=f"Clicks (Part {field_count})", 
                            value=current_field, 
                            inline=False
                        )
                        current_field = entry
                        field_count += 1
                    else:
                        current_field += entry

                # Add the last field if there's any content
                if current_field:
                    embed.add_field(
                        name=f"Clicks {f'(Part {field_count})' if field_count > 1 else ''}", 
                        value=current_field, 
                        inline=False
                    )

                await message.channel.send(embed=embed)

            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error retrieving click list: {e}\n{tb}')
                await message.channel.send('An error occurred while retrieving the click list!')
            finally:
                await message.remove_reaction('⏳', bot.user)

        elif message.content.lower() == 'help':
            embed = nextcord.Embed(
                title='📚 Button Game Commands',
                description='Here are all the available commands for the Button Game:',
                color=nextcord.Color.from_rgb(106, 76, 147)
            )

            # Personal Stats & Checks
            embed.add_field(
                name='🧑‍💼 Personal Stats & Checks',
                value=(
                    '`myrank`, `rank`, `urrank [@user]` — View your or another user\'s stats and click history\n'
                    '`check` — Check if you have a click ready\n'
                    '`checkothers`, `cooldowns` — See cooldown status of the last 10 clickers\n'
                    '`whoready` — See which of the last 10 clickers are ready\n'
                    '`playercharts`, `statsp [@user]` — View graphical charts of your (or another\'s) stats\n'
                    '`mycard` — Get your player card link'
                ),
                inline=False
            )

            # Game Stats & Leaderboards
            embed.add_field(
                name='🏆 Game Stats & Leaderboards',
                value=(
                    '`leaderboard1`, `l1` — View time claimed by color tiers\n'
                    '`leaderboard2`, `l2 [N]` — Top players by MMR, fastest, and most time claimed\n'
                    '`clickquest`, `goonboard [month|YYYY-MM]` — Monthly time claimed leaderboard\n'
                    '`showclicks` — Display all clicks as color emojis\n'
                    '`clicklist [N] [global]` — View the lowest click times (optionally global)\n'
                    '`edging` — Find clicks closest to color transitions\n'
                    '`buttonrank`, `br` — View this button\'s rank compared to others\n'
                    '`gamecharts`, `statsg [game_id]` — View graphical stats for a game\n'
                    '`timeline`, `clicktimeline [game_id]` — Timeline of all clicks for a game\n'
                    '`listgames` — List all button games in this server'
                ),
                inline=False
            )

            # Game Management & Admin
            embed.add_field(
                name='⚙️ Game Management & Admin',
                value=(
                    '`startbutton`, `sb` — Start the button game (admin only)\n'
                    '`force_update_button` — Force recreate the button message (admin only)\n'
                    '`!seticon <emoji>` — Change your server\'s button rank icon (admin only)\n'
                    '`i would like a new button pretty please!` — Create a new button game (admin only)\n'
                    '`insert_first_click` — Insert a first click for the current game (debug/admin)'
                ),
                inline=False
            )

            # Lore & Miscellaneous
            embed.add_field(
                name='📜 Lore & Miscellaneous',
                value=(
                    '`lore` — Read the lore of the button\n'
                    '`help` — Show this help message'
                ),
                inline=False
            )

            embed.set_footer(text='May your clicks be swift and true, adventurer!')
            await message.channel.send(embed=embed)

        elif message.content.lower() == 'check' or (is_brain_rot(message.content.lower()) == 5):
            await message.add_reaction('⏳')
            user_check_id = message.author.id
            try:
                # Get the game session to access the cooldown duration
                game_session = await get_game_session_by_guild_id(message.guild.id)
                if not game_session:
                    await message.channel.send('No active game session found in this server!')
                    await message.remove_reaction('⏳', bot.user)
                    return
        
                cooldown_duration = float(game_session['cooldown_duration'])
        
                # Get the user's last click time in this game
                query = '''
                    SELECT MAX(click_time)
                    FROM button_clicks
                    WHERE user_id = %s AND game_id = %s
                '''
                params = (user_check_id, game_session['game_id'])
                last_click_result = execute_query(query, params)
            
                now_utc = datetime.datetime.now(datetime.timezone.utc)
        
                if not last_click_result or not last_click_result[0] or last_click_result[0][0] is None:
                    # No clicks yet, user can click
                    response = (
                        f"✅ Ah, my brave adventurer! Your spirit is ready, and the button awaits your valiant click. "
                        f"Go forth and claim your glory!\n\n"
                        f"Cooldown: **{int(cooldown_duration)} hour{'s' if float(cooldown_duration) != 1 else ''}**"
                    )
                else:
                    last_click_time = last_click_result[0][0]
                    # Calculate time since last click
                    time_since_last_click = (now_utc - last_click_time.replace(tzinfo=datetime.timezone.utc)).total_seconds()
                    cooldown_seconds = int(cooldown_duration * 3600)
                    time_left = cooldown_seconds - int(time_since_last_click)
                    if time_left <= 0:
                        response = (
                            f"✅ Ah, my brave adventurer! Your spirit is ready, and the button awaits your valiant click. "
                            f"Go forth and claim your glory!\n\n"
                            f"Cooldown: **{int(cooldown_duration)} hour{'s' if float(cooldown_duration) != 1 else ''}**"
                        )
                    else:
                        hours = time_left // 3600
                        minutes = (time_left % 3600) // 60
                        seconds = time_left % 60
                        time_left_str = f"{hours} hour{'s' if hours != 1 else ''} {minutes} minute{'s' if minutes != 1 else ''} {seconds} second{'s' if seconds != 1 else ''}"
                        response = (
                            f"❌ Alas, noble warrior, you must rest and gather your strength. "
                            f"The button shall beckon you again when the time is right.\n\n"
                            f"Time left: **{time_left_str}**\n"
                            f"Cooldown: **{int(cooldown_duration)} hour{'s' if float(cooldown_duration) != 1 else ''}**"
                        )
        
                embed = nextcord.Embed(description=response)
                await message.channel.send(embed=embed)
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error checking user cooldown: {e}, {tb}')
                await message.channel.send('Alas noble warrior, an error occurred while checking your cooldown. The button spirits are in disarray!')
            finally:
                await message.remove_reaction('⏳', bot.user)

        

        elif message.content.lower() == 'force_update_button':
            if message.author.id != 692926265405079632:
                if not message.author.guild_permissions.administrator:
                    await message.channel.send('You need administrator permissions to use this command.')
                    return
            try:
                game_session = await get_game_session_by_guild_id(message.guild.id)
                if not game_session:
                    await message.channel.send('No active game session found in this server!')
                    return
                
                # Clear the button message cache for this game
                #button_message_cache.messages.pop(game_session['game_id'], None)
                
                # Create new button message with forced new creation
                new_message = await create_button_message(game_session['game_id'], bot, force_new=True)
                
                if new_message:
                    await message.channel.send('Button message has been reset successfully!', delete_after=5)
                else:
                    await message.channel.send('Failed to reset button message. Please try again.')
                
                try:
                    await message.delete()
                except:
                    pass
                    
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error resetting button message: {e}\n{tb}')
                await message.channel.send('An error occurred while resetting the button message.')

        elif message.content.lower() == 'ended':
            try:
                query = '''
                    SELECT 
                        u.user_name,
                        COUNT(*) AS total_clicks,
                        MIN(bc.timer_value) AS lowest_click_time,
                        GROUP_CONCAT(
                            CASE
                                WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 83.33 THEN '🟣'
                                WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 66.67 THEN '🔵'
                                WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 50.00 THEN '🟢'
                                WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 33.33 THEN '🟡'
                                WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 16.67 THEN '🟠'
                                ELSE '🔴'
                            END
                            ORDER BY bc.timer_value
                            SEPARATOR ''
                        ) AS color_sequence
                    FROM button_clicks bc
                    JOIN users u ON bc.user_id = u.user_id
                    GROUP BY u.user_id
                    ORDER BY lowest_click_time
                '''
                params = (game_session['timer_duration'],) * 5  # For each CASE condition
                success = execute_query(query, params)
                all_users_data = success
                
                embed = nextcord.Embed(
                    title='🎉 The Button Game Has Ended! 🎉',
                    description='Here are the final results of all the brave adventurers who participated in this epic journey!'
                )
                
                max_field_length = 1024
                field_count = 1
                all_users_value = ""
                
                for user, clicks, lowest_time, seq in all_users_data:
                    user_data = f'{user.replace(".", "")}: {clicks} clicks, Lowest: {format_time(lowest_time)} {" ".join(emoji + "x" + str(seq.count(emoji)) for emoji in ["🟣", "🔵", "🟢", "🟡", "🟠", "🔴"] if emoji in seq)}\n'
                    
                    if len(all_users_value) + len(user_data) > max_field_length:
                        embed.add_field(name=f'🏅 Adventurers of the Button (Part {field_count}) 🏅', value=all_users_value, inline=False)
                        all_users_value = ""
                        field_count += 1
                    
                    all_users_value += user_data
                
                if all_users_value: embed.add_field(name=f'🏅 Adventurers of the Button (Part {field_count}) 🏅', value=all_users_value, inline=False)
                
                if not all_users_data: embed.add_field(name='🏅 Adventurers of the Button 🏅', value='No data available', inline=False)
                
                if all_users_data: color = get_color_state(all_users_data[0][2]); embed.color = nextcord.Color.from_rgb(*color)
                else: embed.color = nextcord.Color.from_rgb(106, 76, 147)  # Default color if no data available

                await message.channel.send(embed=embed)
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error retrieving end game data: {e}, {tb}')
                await message.channel.send('An error occurred while retrieving the end game data. The button spirits are in turmoil!')

        elif message.content.lower() == 'lore':
            try:
                embed = nextcord.Embed(title="📜 __The Lore of The Button__ 📜", description=LORE_TEXT)
                embed.set_footer(text="⚡ *May your clicks be swift and true, adventurer!* ⚡")
                await message.channel.send(embed=embed)
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error retrieving lore: {e}, {tb}')
                await message.channel.send('❌ **An error occurred while retrieving the lore.** *The ancient archives seem to be temporarily sealed!* ❌')

        elif message.content.lower() == 'mycard':
            user_id = message.author.id
            card_url = f"https://www.thebuttongame.click/player_card.php?user_id={user_id}"
            await message.channel.send(f"📜 Behold, brave adventurer! Your personal chronicle awaits inspection: {card_url}")

        elif 'i would like a new button pretty please!' in message.content.lower():
            """
            Command to create a new game session, insert the first click, and create the button message.
            This combines multiple steps into a single streamlined command.
            """
            # Check admin permissions
            if message.author.guild_permissions.administrator or message.author.id == 692926265405079632:
                await message.add_reaction('⏳')
                try:
                    # Parse command for chat channel ID
                    command_parts = message.content.lower().split()
                    chat_channel_id = None
                    for part in command_parts:
                        if part.isdigit() and len(part) > 10:  # Discord IDs are long numbers
                            chat_channel_id = int(part)
                            break
                    
                    if not chat_channel_id:
                        chat_channel_id = message.channel.id
                        
                    # Create a new game session
                    start_time = datetime.datetime.now(timezone.utc)
                    timer_duration = config['timer_duration']
                    cooldown_duration = config['cooldown_duration']
                    
                    await message.channel.send('🎮 **INITIALIZING NEW BUTTON GAME...**')
                    
                    # Set up admin role
                    admin_role_id = 0
                    try:
                        admin_role = nextcord.utils.get(message.guild.roles, name='Button Master')
                        if not admin_role: 
                            admin_role = await message.guild.create_role(name='Button Master')
                        if not admin_role in message.author.roles: 
                            await message.author.add_roles(admin_role)
                        admin_role_id = admin_role.id
                    except Exception as e:
                        logger.warning(f'Could not create or assign Button Master role: {e}')
                        # Continue without roles if permissions are insufficient
                    
                    # Create game session with force_create=True
                    logger.info(f"Creating new game session for guild {message.guild.id}, channel {message.channel.id}, chat {chat_channel_id}")
                    game_id = create_game_session(admin_role_id, message.guild.id, message.channel.id, 
                                                chat_channel_id, start_time, timer_duration, cooldown_duration)
                    
                    if not game_id:
                        #await message.channel.send('❌ Failed to create game session. Please try again.')
                        logger.error('Failed to create game session.')
                        await message.remove_reaction('⏳', bot.user)
                        return
                        
                    logger.info(f"Game session created with ID: {game_id}")
                    
                    # Update local game sessions
                    update_local_game_sessions()
                    
                    # Get the newly created game session
                    game_session = await get_game_session_by_id(game_id)
                    if not game_session:
                        #await message.channel.send('❌ Game session created but could not be retrieved. Please try again.')
                        logger.error(f'Game session {game_id} could not be retrieved after creation.')
                        await message.remove_reaction('⏳', bot.user)
                        return
                        
                    # Insert first click - important to use the retrieved game_id, not 0
                    user_name = message.author.display_name if message.author.display_name else message.author.name

                    # Setup roles if we have permissions
                    try:
                        await setup_roles(message.guild.id, bot)
                    except Exception as e:
                        logger.warning(f"Could not set up roles: {e}")
                        # Continue without roles
                    
                    # Create button message
                    try:
                        logger.info(f"Creating button message for game {game_id}")
                        button_message = await create_button_message(game_id, bot, force_new=True)
                        
                        if button_message:
                            await message.channel.send(f'🎉 **SUCCESS!** New button game created with Game ID: {game_id}')
                            
                            # Add game to menu timer
                            if menu_timer:
                                menu_timer.add_game(str(game_id))
                                
                                # Start timer task if not running
                                if not menu_timer.update_timer_task.is_running():
                                    logger.info('Starting update timer task...')
                                    menu_timer.update_timer_task.start()
                            
                            # Remove from paused games if it's there
                            if game_id in paused_games:
                                try:
                                    paused_games.remove(game_id)
                                    logger.info(f'Game session {game_id} removed from paused games.')
                                except Exception as e:
                                    logger.warning(f'Error removing game session from paused games: {e}')
                        else:
                            # await message.channel.send('⚠️ Game created but button message could not be displayed properly. Try using "force_update_button" command.')
                            logger.error(f'Button message creation failed for game {game_id}')
                    except Exception as e:
                        tb = traceback.format_exc()
                        logger.error(f'Error creating button message: {e}\n{tb}')
                        # await message.channel.send(f'⚠️ Game created but button message could not be displayed: {e}')

                    logger.info(f"Inserting first click for game {game_id}, user {message.author.id}, name {user_name}")
                    
                    # Insert first click using properly retrieved game_id
                    try:
                        query = """
                            INSERT INTO button_clicks 
                            (game_id, user_id, click_time, timer_value) 
                            VALUES (%s, %s, UTC_TIMESTAMP(), %s)
                        """
                        params = (game_id, message.author.id, timer_duration)
                        success = execute_query(query, params, commit=True)
                        if not success:
                            logger.error(f'Failed to insert first click for game {game_id}')
                            # await message.channel.send('❌ Game created but first click could not be inserted. Try using "insert_first_click" command.')
                    except Exception as e:
                        tb = traceback.format_exc()
                        logger.error(f'Error inserting first click: {e}\n{tb}')
                        # await message.channel.send(f'❌ Game created but first click could not be inserted: {e}')
                except Exception as e:
                    tb = traceback.format_exc()
                    logger.error(f'Error creating new button game: {e}\n{tb}')
                    # await message.channel.send(f'❌ An error occurred: {e}')
                finally:
                    await message.remove_reaction('⏳', bot.user)
            else:
                await message.channel.send('❌ **You do not have the necessary permissions to use this command.**')

        # elif 'i would like a new button pretty please!' in message.content.lower():
        #     """
        #     Command to add a new game session to the database. This will add a new game session with default settings.
        #     Regardless of the current state of the game, this command will create a new game session.
        #     """
        #     #Check admin
        #     if message.author.guild_permissions.administrator or message.author.id == 692926265405079632:
        #         await message.channel.send('🎉 **ON IT BOSS...**')
        #     else:
        #         await message.channel.send('🚫 **You do not have the necessary permissions to use this command.**')
        #         return

        #     try:
        #         # Create a new game session
        #         start_time = datetime.datetime.now(timezone.utc)
        #         timer_duration = config['timer_duration']
        #         cooldown_duration = config['cooldown_duration']
        #         chat_channel_id = int(message.content.lower().split()[-1])
        #         game_id = update_or_create_game_session(0, message.guild.id, message.channel.id, chat_channel_id, start_time, timer_duration, cooldown_duration, True)
                                
        #         game_session = await get_game_session_by_id(game_id)
        #         sessions_dict = await game_sessions_dict()  # Fix: Add await here
        #         if sessions_dict:
        #             sessions_dict[game_id] = game_session
        #         else:
        #             sessions_dict = {game_id: game_session}
                
        #         update_local_game_sessions()
        #         await message.channel.send(f'HUZZAH!! A new game session has been created! Game ID: {game_id}')
        #     except Exception as e:
        #         tb = traceback.format_exc()
        #         logger.error(f'Error adding new game session: {e}, {tb}')
        #         await message.channel.send('An error occurred while adding a new game session.')

        elif message.content.lower() in ['playercharts', 'statsp'] or is_brain_rot(message.content.lower()) == 7:
            await message.add_reaction('⏳')
            try:
                game_session = await get_game_session_by_guild_id(message.guild.id)
                if not game_session:
                    await message.channel.send('No active game session found in this server!')
                    await message.remove_reaction('⏳', bot.user)
                    return

                # Determine target user
                target_user_id = message.author.id
                is_other_user = False
                
                # Check if additional arguments are provided
                command_parts = message.content.lower().split()
                if len(command_parts) > 1:
                    # Check for user mention
                    if len(message.mentions) > 0:
                        target_user_id = message.mentions[0].id
                        is_other_user = True
                    # Handle the existing ID extraction from message content
                    elif command_parts[1].startswith('<@') and command_parts[1].endswith('>'):
                        try:
                            target_user_id = int(command_parts[1][2:-1].replace('!', ''))
                            is_other_user = True
                        except ValueError:
                            await message.channel.send('Invalid user mention format!')
                            await message.remove_reaction('⏳', bot.user)
                            return

                # Get user display name
                if not is_other_user:
                    user_name = message.author.display_name if message.author.display_name else message.author.name
                else:
                    target_user = await bot.fetch_user(target_user_id)
                    if target_user is None:
                        await message.channel.send('Unable to find that user!')
                        await message.remove_reaction('⏳', bot.user)
                        return
                    user_name = target_user.display_name if hasattr(target_user, 'display_name') else target_user.name

                # Get user's clicks for current game session
                query = '''
                    SELECT 
                        bc.timer_value,
                        bc.click_time,
                        (
                            SELECT COUNT(DISTINCT u2.user_id)
                            FROM button_clicks bc2 
                            JOIN users u2 ON bc2.user_id = u2.user_id 
                            WHERE bc2.game_id = %s 
                            AND u2.total_clicks > (
                                SELECT COUNT(*) 
                                FROM button_clicks bc3 
                                WHERE bc3.user_id = %s 
                                AND bc3.game_id = %s
                            )
                        ) + 1 AS user_rank,
                        (
                            SELECT COUNT(DISTINCT user_id) 
                            FROM button_clicks 
                            WHERE game_id = %s
                        ) AS total_players
                    FROM button_clicks bc
                    WHERE bc.game_id = %s 
                    AND bc.user_id = %s
                    ORDER BY bc.click_time
                '''
                params = (game_session['game_id'], target_user_id, game_session['game_id'], 
                        game_session['game_id'], game_session['game_id'], target_user_id)
                logger.info(f"Executing user stats query for player charts with params: {params}")
                
                success = execute_query(query, params)
                if not success or len(success) == 0: 
                    await message.channel.send('No click data found for this user!')
                    await message.remove_reaction('⏳', bot.user)
                    return
                    
                clicks = success
                
                # Process click data
                color_emojis = [get_color_emoji(timer_value, game_session['timer_duration']) for timer_value, _, _, _ in clicks]
                
                # Count colors
                color_counts = {}
                for emoji in color_emojis:
                    color_name = None
                    if emoji == '🟣': color_name = 'Purple'
                    elif emoji == '🔵': color_name = 'Blue'
                    elif emoji == '🟢': color_name = 'Green'
                    elif emoji == '🟡': color_name = 'Yellow'
                    elif emoji == '🟠': color_name = 'Orange'
                    elif emoji == '🔴': color_name = 'Red'
                    
                    if color_name:
                        if color_name in color_counts:
                            color_counts[color_name] += 1
                        else:
                            color_counts[color_name] = 1
                
                # Calculate stats
                total_clicks = len(clicks)
                total_claimed_time = sum(game_session['timer_duration'] - timer_value for timer_value, _, _, _ in clicks)
                rank = clicks[0][2]  # Get rank from first row
                total_players = clicks[0][3]  # Get total players from first row
                
                # Get lowest click time
                lowest_click = min(clicks, key=lambda x: x[0])
                lowest_click_time = lowest_click[0]
                
                # Format click history
                click_history = [(timer_value, click_time, get_color_emoji(timer_value, game_session['timer_duration'])) 
                                for timer_value, click_time, _, _ in clicks]
                
                # Generate the chart
                chart_generator = ChartGenerator()
                img_data = chart_generator.generate_player_charts(
                    username=user_name,
                    rank=rank,
                    total_players=total_players,
                    total_clicks=total_clicks,
                    time_claimed=total_claimed_time,
                    color_counts=color_counts,
                    lowest_click_time=lowest_click_time,
                    click_history=click_history,
                    timer_duration=game_session['timer_duration']
                )
                
                # Send the chart
                await message.channel.send(
                    f"📊 Button charts for {user_name}:",
                    file=nextcord.File(fp=img_data, filename=f"{user_name.replace(' ', '_')}_stats.png")
                )
                
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error generating player charts: {e}\n{tb}')
                await message.channel.send('An error occurred while generating the charts. The button spirits are in disarray!')
            finally:
                await message.remove_reaction('⏳', bot.user)

        elif message.content.lower().startswith(('gamecharts', 'statsg')) or is_brain_rot(message.content.lower()) == 8:
            await message.add_reaction('⏳')
            try:
                # Parse command to check for game ID
                command_parts = message.content.lower().split()
                specified_game_id = None
                
                # Check if a game ID was specified
                if len(command_parts) > 1:
                    try:
                        specified_game_id = int(command_parts[1])
                        logger.info(f"Specific game ID requested: {specified_game_id}")
                    except ValueError:
                        pass  # Not a number, so not a game ID
                
                # Get current game session for this server
                current_game_session = await get_game_session_by_guild_id(message.guild.id)
                if not current_game_session and not specified_game_id:
                    await message.channel.send('No active game session found in this server!')
                    await message.remove_reaction('⏳', bot.user)
                    return
                
                # If a specific game ID was provided, check if it belongs to this server
                if specified_game_id:
                    # Query to verify the game belongs to this server
                    verify_query = '''
                        SELECT id FROM game_sessions 
                        WHERE id = %s AND guild_id = %s
                    '''
                    verify_params = (specified_game_id, message.guild.id)
                    verify_result = execute_query(verify_query, verify_params)
                    
                    if not verify_result:
                        await message.channel.send('Game not found or does not belong to this server!')
                        await message.remove_reaction('⏳', bot.user)
                        return
                    
                    # Get the specified game details
                    game_session = await get_game_session_by_id(specified_game_id)
                    if not game_session:
                        await message.channel.send(f'Unable to find game with ID {specified_game_id}!')
                        await message.remove_reaction('⏳', bot.user)
                        return
                else:
                    # Use current game
                    game_session = current_game_session

                # Get game start time and calculate elapsed time
                game_start_time = game_session['start_time']
                if game_session['end_time']:
                    # For completed games, use the actual end time
                    end_time = game_session['end_time']
                    if end_time.tzinfo is None:
                        end_time = end_time.replace(tzinfo=timezone.utc)
                    time_elapsed = (end_time - game_start_time.replace(tzinfo=timezone.utc)).total_seconds()
                else:
                    # For active games, use current time
                    current_time = datetime.datetime.now(timezone.utc)
                    time_elapsed = (current_time - game_start_time.replace(tzinfo=timezone.utc)).total_seconds()
                
                # Query for tier stats
                tier_query = '''
                    SELECT 
                        CASE
                            WHEN ROUND((bc.timer_value / %s) * 100, 2) <= 16.67 THEN 'Red'
                            WHEN ROUND((bc.timer_value / %s) * 100, 2) <= 33.33 THEN 'Orange'
                            WHEN ROUND((bc.timer_value / %s) * 100, 2) <= 50.00 THEN 'Yellow'
                            WHEN ROUND((bc.timer_value / %s) * 100, 2) <= 66.67 THEN 'Green'
                            WHEN ROUND((bc.timer_value / %s) * 100, 2) <= 83.33 THEN 'Blue'
                            ELSE 'Purple'
                        END as tier_name,
                        COUNT(*) as click_count,
                        SUM(GREATEST(0, %s - bc.timer_value)) as total_time_claimed,
                        COUNT(DISTINCT bc.user_id) as unique_clickers,
                        SUM(GREATEST(0, %s - bc.timer_value)) / COUNT(*) as avg_claimed_per_click,
                        SUM(GREATEST(0, %s - bc.timer_value)) / COUNT(DISTINCT bc.user_id) as avg_claimed_per_user
                    FROM button_clicks bc
                    JOIN users u ON bc.user_id = u.user_id
                    WHERE bc.game_id = %s
                    AND bc.timer_value <= %s  -- Filter out clicks greater than timer_duration
                    AND u.user_name != 'HOTFIX'  -- Filter out HOTFIX user
                    AND u.user_name IS NOT NULL  -- Ensure username is not null
                    GROUP BY 
                        CASE
                            WHEN ROUND((bc.timer_value / %s) * 100, 2) <= 16.67 THEN 'Red'
                            WHEN ROUND((bc.timer_value / %s) * 100, 2) <= 33.33 THEN 'Orange'
                            WHEN ROUND((bc.timer_value / %s) * 100, 2) <= 50.00 THEN 'Yellow'
                            WHEN ROUND((bc.timer_value / %s) * 100, 2) <= 66.67 THEN 'Green'
                            WHEN ROUND((bc.timer_value / %s) * 100, 2) <= 83.33 THEN 'Blue'
                            ELSE 'Purple'
                        END
                    ORDER BY MIN(ROUND((bc.timer_value / %s) * 100, 2)) ASC
                '''
                
                tier_params = (
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['game_id'],
                    game_session['timer_duration'],  # New parameter for filtering timer_value
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration']
                )
                
                logger.info(f"Executing tier stats query for game charts")
                tier_stats = execute_query(tier_query, tier_params)
                
                # Query for player activity by hour and day
                activity_query = '''
                    SELECT 
                        HOUR(bc.click_time) as hour_of_day,
                        WEEKDAY(bc.click_time) as day_of_week,
                        COUNT(*) as click_count
                    FROM button_clicks bc
                    JOIN users u ON bc.user_id = u.user_id
                    WHERE bc.game_id = %s
                    AND bc.timer_value <= %s
                    AND u.user_name != 'HOTFIX'
                    AND u.user_name IS NOT NULL
                    GROUP BY HOUR(bc.click_time), WEEKDAY(bc.click_time)
                '''

                activity_params = (game_session['game_id'], game_session['timer_duration'])
                logger.info(f"Executing activity query for game charts")
                player_activity = execute_query(activity_query, activity_params)
                
                # Query for top players
                top_players_query = '''
                    SELECT
                        u.user_name,
                        SUM(GREATEST(0, %s - bc.timer_value)) AS total_time_claimed,
                        MIN(bc.timer_value) as lowest_click,
                        CASE
                            WHEN ROUND((MIN(bc.timer_value) / %s) * 100, 2) <= 16.67 THEN '🔴'
                            WHEN ROUND((MIN(bc.timer_value) / %s) * 100, 2) <= 33.33 THEN '🟠'
                            WHEN ROUND((MIN(bc.timer_value) / %s) * 100, 2) <= 50.00 THEN '🟡'
                            WHEN ROUND((MIN(bc.timer_value) / %s) * 100, 2) <= 66.67 THEN '🟢'
                            WHEN ROUND((MIN(bc.timer_value) / %s) * 100, 2) <= 83.33 THEN '🔵'
                            ELSE '🟣'
                        END as lowest_color
                    FROM button_clicks bc
                    JOIN users u ON bc.user_id = u.user_id
                    WHERE bc.game_id = %s
                    AND bc.timer_value <= %s
                    AND u.user_name != 'HOTFIX'
                    AND u.user_name IS NOT NULL
                    GROUP BY u.user_id, u.user_name
                    ORDER BY total_time_claimed DESC
                    LIMIT 10
                '''

                top_players_params = (
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['game_id'],
                    game_session['timer_duration']  # New parameter for filtering timer_value
                )
                
                logger.info(f"Executing top players query for game charts")
                top_players = execute_query(top_players_query, top_players_params)
                
                # Count total clicks and players
                query = '''
                    SELECT 
                        COUNT(*) as total_clicks,
                        COUNT(DISTINCT bc.user_id) as total_players
                    FROM button_clicks bc
                    JOIN users u ON bc.user_id = u.user_id
                    WHERE bc.game_id = %s
                    AND bc.timer_value <= %s
                    AND u.user_name != 'HOTFIX'
                    AND u.user_name IS NOT NULL
                '''
                params = (game_session['game_id'], game_session['timer_duration'])
                totals_result = execute_query(query, params)
                
                if totals_result and len(totals_result) > 0:
                    total_clicks = totals_result[0][0]
                    total_players = totals_result[0][1]
                else:
                    total_clicks = 0
                    total_players = 0
                
                # Convert any Decimal values to float in top_players data 
                if top_players:
                    top_players = [
                        (username, float(time_claimed), float(lowest_click), color) 
                        for username, time_claimed, lowest_click, color in top_players
                    ]

                # Similarly for tier_stats data
                if tier_stats:
                    tier_stats = [
                        (tier_name, click_count, float(time_claimed), unique_clickers, 
                        float(avg_per_click) if avg_per_click else 0, 
                        float(avg_per_user) if avg_per_user else 0)
                        for tier_name, click_count, time_claimed, unique_clickers, avg_per_click, avg_per_user in tier_stats
                    ]

                # Generate the chart
                chart_generator = ChartGenerator()
                img_data = chart_generator.generate_game_charts(
                    game_id=game_session['game_id'],
                    total_clicks=total_clicks,
                    total_players=total_players,
                    time_elapsed=time_elapsed,
                    timer_duration=game_session['timer_duration'],
                    tier_stats=tier_stats,
                    player_activity_data=player_activity,
                    top_players_data=top_players
                )
                
                # Add game status to the message
                status = "🔥 ACTIVE" if not game_session['end_time'] else "⚰️ ENDED"
                duration_str = format_time(time_elapsed)
                
                # Send the chart
                await message.channel.send(
                    f"📊 Game statistics for Game #{game_session['game_id']} ({status}, {duration_str}):",
                    file=nextcord.File(fp=img_data, filename=f"game_{game_session['game_id']}_stats.png")
                )
                
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error generating game charts: {e}\n{tb}')
                await message.channel.send('An error occurred while generating the game charts. The button spirits are in disarray!')
            finally:
                await message.remove_reaction('⏳', bot.user)

        elif message.content.lower().startswith(('timeline', 'clicktimeline')) or is_brain_rot(message.content.lower()) == 9:
            await message.add_reaction('⏳')
            try:
                # Parse command to check for game ID
                command_parts = message.content.lower().split()
                specified_game_id = None
                
                # Check if a game ID was specified
                if len(command_parts) > 1:
                    try:
                        specified_game_id = int(command_parts[1])
                        logger.info(f"Specific game ID requested for timeline: {specified_game_id}")
                    except ValueError:
                        pass  # Not a number, so not a game ID
                
                # Get current game session for this server
                current_game_session = await get_game_session_by_guild_id(message.guild.id)
                if not current_game_session and not specified_game_id:
                    await message.channel.send('No active game session found in this server!')
                    await message.remove_reaction('⏳', bot.user)
                    return
                
                # If a specific game ID was provided, check if it belongs to this server
                if specified_game_id:
                    # Query to verify the game belongs to this server
                    verify_query = '''
                        SELECT id FROM game_sessions 
                        WHERE id = %s AND guild_id = %s
                    '''
                    verify_params = (specified_game_id, message.guild.id)
                    verify_result = execute_query(verify_query, verify_params)
                    
                    if not verify_result:
                        await message.channel.send('Game not found or does not belong to this server!')
                        await message.remove_reaction('⏳', bot.user)
                        return
                    
                    # Get the specified game details
                    game_session = await get_game_session_by_id(specified_game_id)
                    if not game_session:
                        await message.channel.send(f'Unable to find game with ID {specified_game_id}!')
                        await message.remove_reaction('⏳', bot.user)
                        return
                else:
                    # Use current game
                    game_session = current_game_session

                # Query all clicks for the game, sorted by time
                query = '''
                    SELECT 
                        bc.timer_value,
                        bc.click_time,
                        u.user_name,
                        CASE
                            WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 83.33 THEN '🟣'
                            WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 66.67 THEN '🔵'
                            WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 50.00 THEN '🟢'
                            WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 33.33 THEN '🟡'
                            WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 16.67 THEN '🟠'
                            ELSE '🔴'
                        END as color_emoji
                    FROM button_clicks bc
                    JOIN users u ON bc.user_id = u.user_id
                    WHERE bc.game_id = %s
                    AND bc.timer_value <= %s  -- Filter out clicks greater than timer_duration
                    AND u.user_name != 'HOTFIX'  -- Filter out HOTFIX user
                    AND u.user_name IS NOT NULL  -- Ensure username is not null
                    ORDER BY bc.click_time
                '''

                params = (
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['game_id'],
                    game_session['timer_duration']
                )
                
                logger.info(f"Executing click timeline query for game #{game_session['game_id']}")
                clicks = execute_query(query, params)
                
                if not clicks or len(clicks) == 0:
                    await message.channel.send(f'No click data found for game #{game_session["game_id"]}!')
                    await message.remove_reaction('⏳', bot.user)
                    return
                    
                # Convert decimal values to float
                clicks = [
                    (float(timer_value), click_time, username, color_emoji)
                    for timer_value, click_time, username, color_emoji in clicks
                ]
                
                # Create a specialized timeline chart
                fig, ax = plt.subplots(figsize=(12, 8), dpi=100)
                
                # Set dark background style
                plt.style.use('dark_background')
                
                # Extract data for plotting
                times = [click_time for _, click_time, _, _ in clicks]
                values = [timer_value for timer_value, _, _, _ in clicks]
                usernames = [username for _, _, username, _ in clicks]
                colors = [ChartGenerator()._emoji_to_color(emoji) for _, _, _, emoji in clicks]
                
                # Create the scatter plot
                scatter = ax.scatter(times, values, c=colors, s=60, alpha=0.8, edgecolors='white')
                
                # Add game status to the title
                status = "ACTIVE" if not game_session['end_time'] else "ENDED"
                
                # Configure axes
                ax.set_title(f'Complete Click Timeline for Game #{game_session["game_id"]} ({status})', fontsize=16)
                ax.set_xlabel('Date and Time', fontsize=12)
                ax.set_ylabel('Timer Value (seconds)', fontsize=12)
                
                # Configure date formatting
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M'))
                plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
                
                # Add color bands to show thresholds
                thresholds = [
                    (0, 16.67, COLOR_MAP['Red']),
                    (16.67, 33.33, COLOR_MAP['Orange']),
                    (33.33, 50.00, COLOR_MAP['Yellow']),
                    (50.00, 66.67, COLOR_MAP['Green']),
                    (66.67, 83.33, COLOR_MAP['Blue']),
                    (83.33, 100, COLOR_MAP['Purple'])
                ]
                
                # Get x-axis limits
                date_range = max(times) - min(times)
                padding = date_range * 0.05
                x_min = min(times) - padding
                x_max = max(times) + padding
                
                # Add colored bands
                for lower_pct, upper_pct, color in thresholds:
                    lower_y = (lower_pct / 100) * game_session['timer_duration']
                    upper_y = (upper_pct / 100) * game_session['timer_duration']
                    ax.fill_between([x_min, x_max], lower_y, upper_y, color=color, alpha=0.1)
                
                # Add grid
                ax.grid(True, alpha=0.3)
                
                # Create legend for color thresholds
                import matplotlib.patches as mpatches
                legend_patches = []
                for color_name, hex_color in COLOR_MAP.items():
                    if color_name != 'Unknown':
                        patch = mpatches.Patch(color=hex_color, label=color_name)
                        legend_patches.append(patch)
                
                ax.legend(handles=legend_patches, loc='upper right')
                
                # Add annotation for hovering (for future interactive use)
                annot = ax.annotate("", xy=(0,0), xytext=(20,20), textcoords="offset points",
                                    bbox=dict(boxstyle="round", fc="w"),
                                    arrowprops=dict(arrowstyle="->"))
                annot.set_visible(False)
                
                # Add text labels for lowest click points in each color
                color_lowest = {}
                for i, (timer_value, click_time, username, emoji) in enumerate(clicks):
                    color_name = EMOJI_COLOR_MAP.get(emoji, 'Unknown')
                    if color_name not in color_lowest or timer_value < color_lowest[color_name][0]:
                        color_lowest[color_name] = (timer_value, click_time, username, i)
                
                for color_name, (timer_value, click_time, username, idx) in color_lowest.items():
                    ax.annotate(f"{username}: {format_time(timer_value)}",
                                (click_time, timer_value),
                                xytext=(10, 10),
                                textcoords="offset points",
                                arrowprops=dict(arrowstyle="->", color='white', alpha=0.6),
                                bbox=dict(boxstyle="round,pad=0.3", fc='black', alpha=0.7))
                
                # Add total click count and date range info
                game_start = min(times)
                game_end = max(times)
                duration = (game_end - game_start).total_seconds()
                
                info_text = (f"Total Clicks: {len(clicks)}\n"
                            f"Time Span: {format_time(duration)}\n"
                            f"First Click: {game_start.strftime('%Y-%m-%d %H:%M')}\n"
                            f"Latest Click: {game_end.strftime('%Y-%m-%d %H:%M')}")
                
                # Add info box
                props = dict(boxstyle='round', facecolor='#333333', alpha=0.6)
                ax.text(0.02, 0.98, info_text, transform=ax.transAxes,
                    fontsize=10, verticalalignment='top', bbox=props)
                
                # Adjust layout
                plt.tight_layout()
                
                # Convert to BytesIO for Discord
                buffer = io.BytesIO()
                fig.savefig(buffer, format='png', bbox_inches='tight')
                plt.close(fig)
                buffer.seek(0)
                
                # Send the timeline chart
                await message.channel.send(
                    f"⏰ Click timeline for Game #{game_session['game_id']}:",
                    file=nextcord.File(fp=buffer, filename=f"game_{game_session['game_id']}_timeline.png")
                )
                
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error generating click timeline: {e}\n{tb}')
                await message.channel.send('An error occurred while generating the timeline. The flow of time is disturbed!')
            finally:
                await message.remove_reaction('⏳', bot.user)
        
        elif message.content.lower() == 'listgames':
            await message.add_reaction('⏳')
            try:
                # Query all games for this server, including ended ones
                query = '''
                    SELECT 
                        gs.id,
                        gs.start_time, 
                        COALESCE(gs.end_time, UTC_TIMESTAMP()) as end_time,
                        COUNT(DISTINCT bc.user_id) as total_players,
                        COUNT(bc.id) as total_clicks,
                        TIMESTAMPDIFF(SECOND, gs.start_time, COALESCE(gs.end_time, UTC_TIMESTAMP())) as duration_seconds,
                        CASE WHEN gs.end_time IS NULL THEN 1 ELSE 0 END as is_active
                    FROM game_sessions gs
                    LEFT JOIN button_clicks bc ON gs.id = bc.game_id
                    WHERE gs.guild_id = %s
                    GROUP BY gs.id, gs.start_time, gs.end_time
                    ORDER BY gs.start_time DESC
                '''
                params = (message.guild.id,)
                results = execute_query(query, params)
                
                if not results:
                    await message.channel.send('No games found for this server!')
                    await message.remove_reaction('⏳', bot.user)
                    return
                    
                # Create embed
                embed = nextcord.Embed(
                    title=f'Button Games in {message.guild.name}',
                    description=f'Use `gamecharts [game_id]` or `timeline [game_id]` to view specific games.'
                )
                
                # Process results in chunks for multiple embeds if needed
                MAX_GAMES_PER_EMBED = 10
                current_page = 1
                total_pages = (len(results) + MAX_GAMES_PER_EMBED - 1) // MAX_GAMES_PER_EMBED
                
                for i in range(0, len(results), MAX_GAMES_PER_EMBED):
                    chunk = results[i:i+MAX_GAMES_PER_EMBED]
                    
                    game_list = ""
                    for game_id, start_time, end_time, total_players, total_clicks, duration_seconds, is_active in chunk:
                        duration_str, _ = format_game_duration(duration_seconds)
                        status = "🔥 ACTIVE" if is_active else "⚰️ ENDED"
                        started = start_time.strftime("%Y-%m-%d")
                        
                        game_list += f"**Game #{game_id}** - {status}\n"
                        game_list += f"Started: {started}\n"
                        game_list += f"Duration: {duration_str}\n"
                        game_list += f"Players: {total_players}, Clicks: {total_clicks}\n"
                        game_list += "─────────────\n"
                    
                    # Create embed for this page
                    page_embed = nextcord.Embed(
                        title=f'Button Games (Page {current_page}/{total_pages})',
                        description=game_list,
                        color=nextcord.Color.from_rgb(106, 76, 147)
                    )
                    
                    await message.channel.send(embed=page_embed)
                    current_page += 1
                    
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error listing games: {e}\n{tb}')
                await message.channel.send('An error occurred while listing games!')
            finally:
                await message.remove_reaction('⏳', bot.user)
                
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f'Error processing message: {e}, {tb}')

# Removed for boot performance 5-11-2025
# async def start_boot_game(bot, button_guild_id, message_button_channel, menu_timer):
#     global paused_games, lock, logger
#     logger.info(f"Starting boot game for guild {button_guild_id}")
    
#     game_session = await get_game_session_by_guild_id(button_guild_id)
#     guild = bot.get_guild(button_guild_id)
    
#     if not game_session:
#         logger.info(f"No existing game session found for {button_guild_id}, creating new one")
#         start_time = datetime.datetime.now(timezone.utc)
#         timer_duration = config['timer_duration']
#         cooldown_duration = config['cooldown_duration']
#         chat_channel_id = message_button_channel
        
#         admin_role_id = 0
#         try:
#             admin_role = nextcord.utils.get(guild.roles, name='Button Master')
#             if not admin_role:
#                 admin_role = await guild.create_role(name='Button Master')
#             admin_role_id = admin_role.id
#         except Exception as e:
#             tb = traceback.format_exc()
#             logger.error(f'Error adding role: {e}, {tb}')
#             logger.info('Skipping role addition...')
            
#         game_id = update_or_create_game_session(admin_role_id, guild.id, message_button_channel, chat_channel_id, start_time, timer_duration, cooldown_duration)
        
#         game_session = await get_game_session_by_id(game_id)
#         game_sessions_as_dict = game_sessions_dict()
#         if game_sessions_as_dict:
#             game_sessions_as_dict[game_id] = game_session
#         else:
#             game_sessions_as_dict = {game_id: game_session}

#         update_local_game_sessions()
        
#         if game_id in paused_games: 
#             try:
#                 paused_games.remove(game_id)
#                 logger.info(f'Game session {game_id} removed from paused games.')
#             except Exception as e:
#                 tb = traceback.format_exc()
#                 logger.error(f'Error removing game session from paused games: {e}, {tb}')
        
#         await setup_roles(guild.id, bot)
#         update_local_game_sessions()
#         await create_button_message(game_id, bot)
        
#     if menu_timer and not menu_timer.update_timer_task.is_running():
#         logger.info('Starting update timer task...')
#         menu_timer.update_timer_task.start()

# async def start_boot_game(bot, button_guild_id, message_button_channel, menu_timer):
#     global paused_games, lock, logger
#     logger.info(f"Starting boot game for guild {button_guild_id}")
    
#     # Get game session directly from the global cache instead of querying again
#     sessions_dict = await game_sessions_dict()
    
#     # Find the game session for this guild
#     game_session = None
#     for session_id, session_data in sessions_dict.items():
#         if isinstance(session_data, dict) and session_data.get('guild_id') == button_guild_id:
#             game_session = session_data
#             break
    
#     # If no session found, create one
#     if not game_session:
#         logger.info(f"No existing game session found for {button_guild_id}, creating new one")
#         guild = bot.get_guild(button_guild_id)
#         start_time = datetime.datetime.now(timezone.utc)
#         timer_duration = config['timer_duration']
#         cooldown_duration = config['cooldown_duration']
#         chat_channel_id = message_button_channel
        
#         # Set up admin role
#         admin_role_id = 0
#         try:
#             admin_role = nextcord.utils.get(guild.roles, name='Button Master')
#             if not admin_role:
#                 admin_role = await guild.create_role(name='Button Master')
#             admin_role_id = admin_role.id
#         except Exception as e:
#             tb = traceback.format_exc()
#             logger.error(f'Error adding role: {e}, {tb}')
#             logger.info('Skipping role addition...')
            
#         # Create game session
#         game_id = update_or_create_game_session(admin_role_id, guild.id, message_button_channel, 
#                                               chat_channel_id, start_time, timer_duration, cooldown_duration)
        
#         # Update local cache with new session
#         update_local_game_sessions()
        
#         # Get updated game session
#         game_session = await get_game_session_by_id(game_id)
        
#         # Remove from paused games if needed
#         if game_id in paused_games:
#             try:
#                 paused_games.remove(game_id)
#                 logger.info(f'Game session {game_id} removed from paused games.')
#             except Exception as e:
#                 tb = traceback.format_exc()
#                 logger.error(f'Error removing game session from paused games: {e}, {tb}')
    
#     # Create button message
#     if game_session:
#         # Only create button message if there's a game session
#         try:
#             await create_button_message(game_session['game_id'], bot)
#         except Exception as e:
#             logger.error(f"Error creating button message: {e}")
    
#     # Ensure timer task is running
#     if menu_timer and not menu_timer.update_timer_task.is_running():
#         logger.info('Starting update timer task...')
#         menu_timer.update_timer_task.start()

async def start_boot_game(bot, button_guild_id, message_button_channel, menu_timer):
    # global lock and logger are still needed, but not paused_games since it's declared at module level
    global lock, logger
    logger.info(f"Starting boot game for guild {button_guild_id}")
    
    # Rest of the function implementation remains the same
    # Get game session directly from the global cache instead of querying again
    sessions_dict = await game_sessions_dict()
    
    # Find the game session for this guild
    game_session = None
    for session_id, session_data in sessions_dict.items():
        if isinstance(session_data, dict) and session_data.get('guild_id') == button_guild_id:
            game_session = session_data
            break
            
    # If no session found, create one
    if not game_session:
        logger.info(f"No existing game session found for {button_guild_id}, creating new one")
        guild = bot.get_guild(button_guild_id)
        start_time = datetime.datetime.now(timezone.utc)
        timer_duration = config['timer_duration']
        cooldown_duration = config['cooldown_duration']
        chat_channel_id = message_button_channel
        
        # Set up admin role
        admin_role_id = 0
        try:
            admin_role = nextcord.utils.get(guild.roles, name='Button Master')
            if not admin_role:
                admin_role = await guild.create_role(name='Button Master')
            admin_role_id = admin_role.id
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f'Error adding role: {e}, {tb}')
            logger.info('Skipping role addition...')
            
        # Create game session
        game_id = update_or_create_game_session(admin_role_id, guild.id, message_button_channel, 
                                              chat_channel_id, start_time, timer_duration, cooldown_duration)
                                              
        # Update local cache with new session
        update_local_game_sessions()
        
        # Get updated game session
        game_session = await get_game_session_by_id(game_id)
        
        # Remove from paused games if needed
        if game_id in paused_games:
            try:
                paused_games.remove(game_id)
                logger.info(f'Game session {game_id} removed from paused games.')
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error removing game session from paused games: {e}, {tb}')
    
    # Create button message
    if game_session:
        # Only create button message if there's a game session
        try:
            await create_button_message(game_session['game_id'], bot)
        except Exception as e:
            logger.error(f"Error creating button message: {e}")
            
    # Ensure timer task is running
    if menu_timer and not menu_timer.update_timer_task.is_running():
        logger.info('Starting update timer task...')
        menu_timer.update_timer_task.start()

def calculate_mmr(timer_value, timer_duration):
    """
    Calculate MMR for a click based on:
    1. Color bracket (16.66% intervals)
    2. Precise timing within bracket
    3. Scaled against timer_duration
    
    Args:
        timer_value (int): Time remaining when button was clicked
        timer_duration (int): Total duration of timer (cooldown)
    
    Returns:
        float: Calculated MMR value
    """
    percentage = (timer_value / timer_duration) * 100
    bracket_size = 16.66667  # Each color represents 16.66667% of the timer
    
    # Determine which bracket (0-5, where 0 is red and 5 is purple)
    bracket = min(5, int(percentage / bracket_size))
    
    # Calculate position within bracket (0.0 to 1.0)
    bracket_position = (percentage % bracket_size) / bracket_size
    
    # Base points exponentially increase as brackets get rarer
    # Red (0) = 32, Orange (1) = 16, Yellow (2) = 8, Green (3) = 4, Blue (4) = 2, Purple (5) = 1
    base_points = 2 ** (5 - bracket)
    
    # Position multiplier: rewards riskier timing within each bracket
    # For red/orange (rarest), rewards getting closer to zero
    # For other colors, rewards consistency in hitting the bracket
    if bracket <= 1:  # Red or Orange
        position_multiplier = 1 - bracket_position
    else:
        position_multiplier = 1 - abs(0.5 - bracket_position)
    
    # Scale final score by timer_duration to account for game difficulty
    time_scale = timer_duration / 43200  # Normalize to 12-hour standard
    
    mmr = base_points * (1 + position_multiplier) * time_scale
    
    return mmr