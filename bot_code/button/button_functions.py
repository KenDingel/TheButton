# Button Functions
import traceback
import asyncio
import datetime
from datetime import timezone
import random

# Nextcord
import nextcord
from nextcord.ext import tasks, commands
import weakref 

# Local imports
from utils.utils import logger, lock, COLOR_STATES, paused_games, get_color_name, get_color_emoji, get_color_state, generate_timer_image
from game.game_cache import game_cache, button_message_cache
from database.database import execute_query, get_game_session_by_id, game_sessions_dict, update_local_game_sessions
from text.full_text import generate_explaination_text
from game.end_game import get_end_game_embed
from button.button_utils import get_button_message, Failed_Interactions
from button.button_view import ButtonView

async def setup_roles(guild_id, bot):
    guild = bot.get_guild(guild_id)
    for color_name, color_value in zip(['Red', 'Orange', 'Yellow', 'Green', 'Blue', 'Purple'], COLOR_STATES):
        role = nextcord.utils.get(guild.roles, name=color_name)
        if role is None: role = await guild.create_role(name=color_name, color=nextcord.Color.from_rgb(*color_value))
        else: await role.edit(color=nextcord.Color.from_rgb(*color_value))
    logger.info(f"In {guild.name}, roles have been set up.")

async def create_button_message(game_id, bot, force_new=False):
    """
    Create a new button message or find existing one
    
    Args:
        game_id: The game session ID
        bot: The Discord bot instance
        force_new: Whether to force create a new message (default: False)
    """
    logger.info(f'Creating/finding button message for game {game_id}...')
    try:
        game_session_config = await get_game_session_by_id(game_id)
        if game_session_config is None:
            logger.error(f'No game session found for game {game_id}')
            game_session = update_local_game_sessions()
            logger.info(f'Updated game sessions: {game_session}')
            game_sessions = game_sessions_dict(game_session)
            logger.info(f'Game sessions dict: {game_sessions}')
            game_session_config = game_sessions.get(game_id)
            if game_session_config is None:
                logger.error(f'No game session found for game {game_id} after update')
                return
            else:
                logger.info(f'Game session config: {game_session_config}')
        else:
            logger.info(f'Game session config: {game_session_config}')
            
        logger.info(f'Game session config: {game_session_config}')
        button_channel = bot.get_channel(game_session_config['button_channel_id'])

        if not force_new:
            async for message in button_channel.history(limit=15):
                if message.author == bot.user and message.embeds:
                    logger.info(f'Found existing button message for game {game_id}')
                    # Add the view back to the existing message
                    view = ButtonView(game_session_config['timer_duration'], bot, game_id)
                    message_id = message.id
                    bot.add_view(view, message_id=message_id)
                    button_message_cache.update_message_cache(message, game_id)
                    return message

        # If no message found or forcing new, create new message
        cooldown_hours = game_session_config['cooldown_duration']
        embed = nextcord.Embed(
            title='🚨 THE BUTTON! 🚨', 
            description=f'**Keep the button alive!**\nEach adventurer must wait **{cooldown_hours} hours** between clicks to regain their strength!'
        )
        
        if force_new:
            # Only clear old messages if forcing new
            async for message in button_channel.history(limit=15):
                if message.author == bot.user and message.embeds:
                    # If embed title includes "🚨" then delete
                    if '🚨' in message.embeds[0].title:
                        await message.delete()
        
        if not "Prepare yourselves for The Button Game" in [msg.content async for msg in button_channel.history(limit=5)]:
            await button_channel.send(generate_explaination_text(game_session_config['timer_duration']))
        
        view = ButtonView(game_session_config['timer_duration'], bot, game_id)
        message = await button_channel.send(embed=embed, view=view)
        message_id = message.id
        button_message_cache.update_message_cache(message, game_id)
        return message
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f'Error creating button message: {e}, {tb}')
        return None

# button/button_functions.py
def calculate_time_to_next_color(timer_value, timer_duration):
    """
    Calculate time remaining until the next color change.
    Args:
        timer_value (float): Current time remaining in seconds
        timer_duration (float): Total timer duration for the game session
    Returns:
        tuple: (seconds_to_next_color, next_color_name)
    """
    percentage = (timer_value / timer_duration) * 100
    thresholds = [
        (83.3333333333, "Purple"),
        (66.6666666666, "Blue"),
        (50.00, "Green"),
        (33.3333333333, "Yellow"),
        (16.6666666666, "Orange"),
        (0.00, "Red")
    ]
    # Find the current threshold and next threshold
    current_color = None
    next_threshold = None
    next_color = None
    for i, (threshold, color) in enumerate(thresholds):
        if percentage >= threshold:
            current_color = color
            # If there's a next threshold (not the last one)
            if i + 1 < len(thresholds):
                next_threshold = thresholds[i + 1][0]
                next_color = thresholds[i + 1][1]
            break
    if next_threshold is None:
        return 0, "Red"  # Already at the last color
    # Calculate seconds until next color
    current_seconds = timer_value
    seconds_at_next_threshold = (next_threshold / 100) * timer_duration
    # The key fix: We need to subtract current timer from next threshold point
    # not the other way around, since we're counting down toward the threshold
    seconds_to_next = seconds_at_next_threshold - current_seconds
    # Ensure we return a non-negative value
    return max(0, seconds_to_next), next_color

# Menu Timer class 
# This class uses Nextcord's View class to create a timer that updates every 10 seconds.
# The loop utilizes tasks from Nextcord's ext module to update the timer.
# Handles game mechanics, cache, and button message updates.
class MenuTimer(nextcord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.lock = asyncio.Lock()
        self.active_game_ids = []
        self.button_message_cache = {}  # Cache button messages
        self.last_embed_cache = {}      # Cache last embed content
        self.initialized = False

    async def get_cached_button_message(self, game_id):
        """Get button message from cache or fetch it"""
        if game_id not in self.button_message_cache:
            button_message = await get_button_message(game_id, self.bot)
            if button_message:
                self.button_message_cache[game_id] = button_message
            return button_message
        return self.button_message_cache[game_id]

    def clear_message_cache(self, game_id):
        """Clear cached message if it becomes invalid"""
        if game_id in self.button_message_cache:
            del self.button_message_cache[game_id]
        if game_id in self.last_embed_cache:
            del self.last_embed_cache[game_id]

    def add_game(self, game_id):
        """Add a game to be tracked, ensuring no duplicates"""
        game_id = str(game_id)  # Ensure consistent type
        if game_id not in self.active_game_ids:
            self.active_game_ids.append(game_id)
            logger.info(f"Added game {game_id} to timer tracking")

    async def start(self):
        """Safely initialize and start the timer"""
        if not self.initialized:
            try:
                await self.bot.wait_until_ready()
                self.update_timer_task.start()
                self.initialized = True
                logger.info("MenuTimer started successfully")
            except Exception as e:
                logger.error(f"Failed to start MenuTimer: {e}")
                raise

    def stop(self):
        """Safely stop the timer"""
        try:
            if self.update_timer_task.is_running():
                self.update_timer_task.cancel()
            self.initialized = False
            logger.info("MenuTimer stopped successfully")
        except Exception as e:
            logger.error(f"Error stopping MenuTimer: {e}")
            raise
            
    def add_game(self, game_id):
        """Add a game to be tracked"""
        if game_id not in self.active_game_ids:
            self.active_game_ids.append(game_id)
            
    def remove_game(self, game_id):
        """Remove a game from tracking"""
        if game_id in self.active_game_ids:
            self.active_game_ids.remove(game_id)
        if game_id in self._game_sessions_cache:
            del self._game_sessions_cache[game_id]

    def _should_update_sessions_dict(self):
        """Check if sessions dict cache needs updating"""
        if not self._last_dict_update:
            return True
        return (datetime.datetime.now(timezone.utc) - self._last_dict_update) > datetime.timedelta(seconds=30)

    async def get_game_session(self, game_id):
        """Get game session with improved caching"""
        try:
            game_id = str(game_id)
            now = datetime.datetime.now(timezone.utc)
            
            # Check memory cache first
            cache_entry = self._game_sessions_cache.get(game_id)
            if cache_entry and (now - cache_entry['timestamp']) < datetime.timedelta(minutes=5):
                return cache_entry['session']
            
            # Use cached sessions dict if available and recent
            if not self._should_update_sessions_dict() and self._sessions_dict_cache:
                game_session = self._sessions_dict_cache.get(game_id)
                if game_session:
                    self._game_sessions_cache[game_id] = {
                        'session': game_session,
                        'timestamp': now
                    }
                    return game_session

            # Add small delay before database query
            await asyncio.sleep(0.25)
            
            # Get from database and update cache
            game_session = await get_game_session_by_id(game_id)
            if game_session:
                self._game_sessions_cache[game_id] = {
                    'session': game_session,
                    'timestamp': now
                }
                return game_session
            
            return None
            
        except Exception as e:
            logger.error(f'Error getting game session for game {game_id}: {e}')
            return None

    @tasks.loop(seconds=5)
    async def update_timer_task(self):
        """Update all active games simultaneously (optimized)"""
        if not self.active_game_ids:
            return
            
        try:
            # Pre-filter active games to avoid unnecessary work
            active_games = [game_id for game_id in self.active_game_ids 
                        if game_id not in paused_games]
            
            if not active_games:
                return
            
            # Fire all updates simultaneously
            update_tasks = [self.update_single_game(game_id) for game_id in active_games]
            await asyncio.gather(*update_tasks, return_exceptions=True)
            
        except Exception as e:
            logger.error(f'Error in update_timer_task: {e}')

    async def update_single_game(self, game_id):
        try:
            game_session = await get_game_session_by_id(game_id)
            if not game_session:
                if not self.initialized:
                    return
                logger.error(f'No game session found for game {game_id}, removing from active games')
                self.remove_game(game_id)
                return
            global paused_games
            if paused_games is None:
                paused_games = []
            if game_id in paused_games:
                return
            
            # Use cached button message instead of fetching every time
            button_message = await self.get_cached_button_message(game_id)
            if not button_message:
                logger.error(f'Could not get button message for game {game_id}')
                Failed_Interactions.increment()
                return
            
            # Update the timer for the button game
            try:
                game_id = str(game_id)
                cache_data = game_cache.get_game_cache(game_id)
                last_update_time = None
                
                # Check if we have cached data
                if cache_data:
                    latest_click_time_overall = cache_data['latest_click_time']
                    total_clicks = cache_data['total_clicks']
                    last_update_time = cache_data['last_update_time']
                    total_players = cache_data['total_players']
                    user_name = cache_data['latest_player_name']
                    last_timer_value = cache_data['last_timer_value']
                else:
                    logger.info(f'Cache miss for game {game_id}')
                    # Query database
                    query = f'''
                        SELECT users.user_name, button_clicks.click_time, button_clicks.timer_value,
                            (SELECT COUNT(*) FROM button_clicks WHERE game_id = {game_id}) AS total_clicks,
                            (SELECT COUNT(DISTINCT user_id) FROM button_clicks WHERE game_id = {game_id}) AS total_players
                        FROM button_clicks
                        INNER JOIN users ON button_clicks.user_id = users.user_id
                        WHERE button_clicks.game_id = {game_id}
                        ORDER BY button_clicks.id DESC
                        LIMIT 1
                    '''
                    params = ()
                    result = execute_query(query, params, is_timer=True)
                    
                    # Handle case when no clicks exist yet
                    if not result or len(result) == 0: 
                        logger.info(f'No clicks found for game {game_id}, using initial state')
                        # Use initial state based on game session
                        user_name = "Game Initialized"
                        latest_click_time_overall = game_session['start_time']
                        last_timer_value = game_session['timer_duration']
                        total_clicks = 0
                        total_players = 0
                        last_update_time = datetime.datetime.now(timezone.utc)
                        # Update cache with initial values
                        game_cache.update_game_cache(game_id, latest_click_time_overall, 
                                                    total_clicks, total_players, 
                                                    user_name, last_timer_value)
                    else:
                        # Process normal result with existing clicks
                        result = result[0]
                        user_name, latest_click_time_overall, last_timer_value, total_clicks, total_players = result
                        latest_click_time_overall = latest_click_time_overall.replace(tzinfo=timezone.utc) if latest_click_time_overall.tzinfo is None else latest_click_time_overall
                        last_update_time = datetime.datetime.now(timezone.utc)
                        game_cache.update_game_cache(game_id, latest_click_time_overall, total_clicks, total_players, user_name, last_timer_value)
                
                # Calculate elapsed time and current timer value
                # Ensure both datetime objects are timezone-aware
                now = datetime.datetime.now(timezone.utc)
                if latest_click_time_overall.tzinfo is None:
                    latest_click_time_overall = latest_click_time_overall.replace(tzinfo=timezone.utc)
                elapsed_time = (now - latest_click_time_overall).total_seconds()
                timer_value = max(game_session['timer_duration'] - elapsed_time, 0)
                
                # Clear cache if last update was too long ago
                if last_update_time is None or not last_update_time: 
                    last_update_time = datetime.datetime.now(timezone.utc)
                if datetime.datetime.now(timezone.utc) - last_update_time > datetime.timedelta(hours=0.25):
                    logger.info(f'Clearing cache for game {game_id}, since last update was more than 15 minutes ago...')
                    game_cache.clear_game_cache(game_id)
                
                # Only update if embed content actually changed
                embed_key = f"{int(timer_value)}_{total_clicks}_{user_name}_{int(latest_click_time_overall.timestamp())}"
                if game_id in self.last_embed_cache and self.last_embed_cache[game_id] == embed_key:
                    return  # Skip update if nothing changed
                
                # Prepare the latest user info for the embed
                color_name = get_color_name(last_timer_value, game_session['timer_duration'])
                color_emoji = get_color_emoji(last_timer_value, game_session['timer_duration'])
                hours_remaining = int(last_timer_value) // 3600
                minutes_remaining = int(last_timer_value) % 3600 // 60
                seconds_remaining = int(int(last_timer_value) % 60)
                formatted_timer_value = f'{hours_remaining:02d}:{minutes_remaining:02d}:{seconds_remaining:02d}'
                
                # Format latest click info depending on whether we have any clicks
                if total_clicks != None and total_clicks > 0:
                    formatted_time = f'<t:{int(latest_click_time_overall.timestamp())}:R>'
                    latest_user_info = f'{formatted_time} {user_name} clicked {color_emoji} {color_name} with {formatted_timer_value} left on the clock!'
                else:
                    latest_user_info = f'No clicks yet! Be the first to click and claim your color!'
                
                # Handle game end condition
                if timer_value <= 0:
                    # Update end_time in database based on last click
                    update_query = """
                        UPDATE game_sessions gs
                        INNER JOIN (
                            SELECT game_id, click_time, timer_value
                            FROM button_clicks
                            WHERE game_id = %s
                            ORDER BY click_time DESC
                            LIMIT 1
                        ) last_click ON gs.id = last_click.game_id
                        SET gs.end_time = DATE_ADD(last_click.click_time, 
                            INTERVAL last_click.timer_value SECOND)
                        WHERE gs.id = %s
                    """
                    try:
                        execute_query(update_query, (game_id, game_id), commit=True)
                        logger.info(f'Updated end_time for game {game_id}')
                    except Exception as e:
                        logger.error(f'Error updating end_time for game {game_id}: {e}')
                    
                    guild_id = game_session['guild_id']
                    guild = self.bot.get_guild(guild_id)
                    embed, file = get_end_game_embed(game_id, guild)

                    try:
                        await button_message.edit(embed=embed, file=file)
                        self.clear_message_cache(game_id)  # Clear cache when game ends
                        logger.info(f'Game {game_id} Ended!')
                    except nextcord.NotFound:
                        logger.error(f'Message was deleted when trying to end game {game_id}')
                        self.clear_message_cache(game_id)
                    return

                # Update the embed with current game state
                embed = nextcord.Embed(title='🚨 THE BUTTON! 🚨', description='**Keep the button alive!**')
                embed.clear_fields()
                
                # Get elapsed time since game start
                start_time = game_session['start_time'].replace(tzinfo=timezone.utc)
                elapsed_time = datetime.datetime.now(timezone.utc) - start_time
                elapsed_days = elapsed_time.days
                elapsed_hours = elapsed_time.seconds // 3600
                elapsed_minutes = (elapsed_time.seconds % 3600) // 60
                elapsed_seconds = elapsed_time.seconds % 60
                elapsed_seconds = round(elapsed_seconds, 2)
                elapsed_time_str = f'{elapsed_days} days, {elapsed_hours} hours, {elapsed_minutes} minutes, {elapsed_seconds} seconds'
                
                # Add fields to embed
                if total_clicks > 0:
                    embed.add_field(
                        name='🗺️ The Saga Unfolds',
                        value=f'Valiant clickers in the pursuit of glory, have kept the button alive for...\n**{elapsed_time_str}**!\n**{total_clicks} clicks** have been made by **{total_players} adventurers**! 🛡️🗡️🏰',
                        inline=False
                    )
                else:
                    embed.add_field(
                        name='🗺️ The Adventure Begins',
                        value=f'The button has been active for **{elapsed_time_str}**!\nNo brave soul has clicked it yet. Will you be the first to claim your glory?',
                        inline=False
                    )
                    
                embed.add_field(name='🎉 Latest Heroic Click', value=latest_user_info, inline=False)
                embed.description = f'__The game ends when the timer hits 0__.\nClick the button to reset the clock and keep the game going!\n\nWill you join the ranks of the brave and keep the button alive? 🛡️🗡️'
                embed.set_footer(text=f'The Button Game by K3N; Inspired by Josh Wardle\nLive Stats: https://thebuttongame.click/')
                
                # Generate and add timer image
                file_buffer = generate_timer_image(timer_value, game_session['timer_duration'])
                if file_buffer:
                    embed.set_image(url=f'attachment://{file_buffer.filename}')
                else:
                    logger.error(f'Failed to generate timer image for game {game_id}')
                
                # Set embed color
                pastel_color = get_color_state(timer_value, game_session['timer_duration'])
                embed.color = nextcord.Color.from_rgb(*pastel_color)
                
                # Update the message
                try:
                    async with lock:
                        button_view = ButtonView(timer_value, self.bot, game_id)
                        if file_buffer:
                            await button_message.edit(embed=embed, file=file_buffer, view=button_view)
                        else:
                            await button_message.edit(embed=embed, view=button_view)
                        
                        # Cache the embed key to avoid redundant updates
                        self.last_embed_cache[game_id] = embed_key
                        
                except nextcord.NotFound:
                    logger.warning(f'Message was deleted, clearing cache for game {game_id}')
                    self.clear_message_cache(game_id)
                    return
                except Exception as e:
                    logger.error(f'Error updating button message: {str(e)}')
                    Failed_Interactions.increment()
                    return
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error updating timer: {e}\n{tb}')
                Failed_Interactions.increment()
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f'Error processing game {game_id}: {e}\n{tb}')

    @update_timer_task.before_loop
    async def before_update_timer(self):
        await self.bot.wait_until_ready()

    async def on_timeout(self):
        self.update_timer_task.cancel()