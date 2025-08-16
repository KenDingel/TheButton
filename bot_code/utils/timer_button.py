# Timer Button
import nextcord
import datetime
import asyncio
import traceback
import random
import json
from datetime import timezone
import pytz
from collections import defaultdict, deque
import time
import giphy_client
from giphy_client.rest import ApiException

# Local imports
from utils.utils import logger, lock, get_color_state, get_color_name, get_color_emoji, config
from user.user_manager import user_manager
from button.button_utils import get_button_message, Failed_Interactions
from game.game_cache import game_cache
from database.database import execute_query, get_game_session_by_guild_id, get_game_session_by_id
from game.character_handler import CharacterHandler
from redis_lib.redis_cache import game_state_cache
from redis_lib.redis_locks import RedisLock
from redis_lib.redis_queues import push_click_to_queue, push_user_update

try:
    giphy_api = giphy_client.DefaultApi()
except Exception as e:
    logger.error(f"Failed to initialize Giphy API: {e}\n{traceback.format_exc()}")
    giphy_api = None

HARDCODED_GIFS = {
    "celebration": [
        "",
    ],
    "colors": {
        "Purple": [
            "media.tenor.com/P6m9avOoaxYAAAPo/courage-cowardly.mp4",
            "https://media.tenor.com/gYw4XiQtMsUAAAPo/really-bruh.mp4",

            ],
        "Blue": [
            "https://media.tenor.com/29H5BxhNQgMAAAPo/qsad.mp4",
            "https://media.tenor.com/qSpB-PVAotYAAAPo/miku-hatsune-miku.mp4",
            "https://media.tenor.com/2c_Uopgq-SIAAAPo/hatsune-miku-meme.mp4"
            ],
        "Green": [
            "https://media.tenor.com/Wu6sjfktzC8AAAPo/squid-edward-erm-what-the-sigma.mp4"
                  ],
        "Yellow": [
            "http://media.tenor.com/vymg4htMUa8AAAPo/thanos-memoji.mp4"
            ],
        "Orange": [
            "https://media.tenor.com/v-or238Ds04AAAPo/woody-toystory.mp4"
            ],
        "Red": [
            "https://media.tenor.com/zaCKRWdzLMsAAAPo/huhh.mp4",
            "https://media.tenor.com/eGSEW2tVd4QAAAPo/japanese-guy-japan.mp4",
            "http://media.tenor.com/qhI_SO98l6MAAAPo/screaming-cat-browthy.mp4"
            ]
    }
}

async def send_gif_enhanced(channel, keywords: list, color: str = None, timing: str = None) -> bool:
    """
    Send a GIF to the specified channel with enhanced selection (keywords vs hardcoded)
    Args:
        channel: Discord channel to send the GIF to
        keywords: List of keywords to search for
        color: Current button color for context
        timing: Timing context (early_click, late_click)
    Returns:
        bool: True if GIF was sent successfully, False otherwise
    """
    try:
        # Randomly choose between keyword search and hardcoded URLs
        use_hardcoded = False #random.random() < 0.5  # 50% chance
        
        if use_hardcoded:
            # Try to get context-specific hardcoded GIF
            gif_url = None
            if color and color in HARDCODED_GIFS["colors"]:
                gif_url = random.choice(HARDCODED_GIFS["colors"][color])
            else:
                gif_url = random.choice(HARDCODED_GIFS["celebration"])
            
            await channel.send(gif_url)
            logger.info(f"Successfully sent hardcoded GIF for {color}/{timing}")
            return True
        else:
            # Use existing keyword search
            api_instance = giphy_client.DefaultApi()
            search_string = ' '.join(keywords)
            
            response = api_instance.gifs_search_get(
                api_key=config['giphy_api_key'],
                q=search_string,
                limit=20,
                rating='r'
            )
            if response.data:
                gif = random.choice(response.data)
                await channel.send(gif.images.original.url)
                logger.info(f"Successfully sent keyword GIF for: {search_string}")
                return True
    except ApiException as e:
        logger.error(f"Giphy API error: {e}\n{traceback.format_exc()}")
    except Exception as e:
        logger.error(f"Error sending GIF: {e}\n{traceback.format_exc()}")
    return False

async def gather_comprehensive_context(game_id: int, user_id: int, current_timer_value: float, 
                                     timer_duration: int, color: str, bot) -> dict:
    """
    Gather comprehensive context data for LLM including player stats, game state, social dynamics, etc.
    Args:
        game_id: Current game ID
        user_id: User who clicked the button
        current_timer_value: Current timer value in seconds
        timer_duration: Total timer duration
        color: Current button color
        bot: Discord bot instance
    Returns:
        dict: Comprehensive context data
    """
    try:
        context = {
            "player_stats": {},
            "game_context": {},
            "recent_clicks": [],
            "social_context": {},
            "chat_context": []
        }
        
        # Get player stats
        player_query = '''
            SELECT 
                COUNT(*) as total_clicks,
                MIN(bc.timer_value) as best_click,
                SUM(CASE WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 83.33 THEN 1 ELSE 0 END) AS purple_clicks,
                SUM(CASE WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 66.67 AND ROUND((bc.timer_value / %s) * 100, 2) < 83.33 THEN 1 ELSE 0 END) AS blue_clicks,
                SUM(CASE WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 50.00 AND ROUND((bc.timer_value / %s) * 100, 2) < 66.67 THEN 1 ELSE 0 END) AS green_clicks,
                SUM(CASE WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 33.33 AND ROUND((bc.timer_value / %s) * 100, 2) < 50.00 THEN 1 ELSE 0 END) AS yellow_clicks,
                SUM(CASE WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 16.67 AND ROUND((bc.timer_value / %s) * 100, 2) < 33.33 THEN 1 ELSE 0 END) AS orange_clicks,
                SUM(CASE WHEN ROUND((bc.timer_value / %s) * 100, 2) < 16.67 THEN 1 ELSE 0 END) AS red_clicks,
                (
                    SELECT COUNT(DISTINCT u2.user_id) + 1
                    FROM button_clicks bc2 
                    JOIN users u2 ON bc2.user_id = u2.user_id 
                    WHERE bc2.game_id = %s 
                    AND (
                        SELECT COUNT(*) FROM button_clicks bc3 WHERE bc3.user_id = u2.user_id AND bc3.game_id = %s
                    ) > (
                        SELECT COUNT(*) FROM button_clicks bc4 WHERE bc4.user_id = %s AND bc4.game_id = %s
                    )
                ) as rank_position
            FROM button_clicks bc
            WHERE bc.game_id = %s AND bc.user_id = %s
        '''
        player_params = (timer_duration,) * 10 + (game_id, game_id, user_id, game_id, game_id, user_id)
        player_result = execute_query(player_query, player_params)
        
        if player_result and player_result[0]:
            stats = player_result[0]
            # Convert all Decimal objects to float/int for JSON serialization
            context["player_stats"] = {
                "total_clicks": int(stats[0]) + 1,  # +1 for current click
                "best_click": {
                    "timer_value": float(stats[1]) if stats[1] is not None else float(current_timer_value), 
                    "color": color
                },
                "color_distribution": {
                    "Purple": int(stats[2]) if stats[2] is not None else 0,
                    "Blue": int(stats[3]) if stats[3] is not None else 0,
                    "Green": int(stats[4]) if stats[4] is not None else 0,
                    "Yellow": int(stats[5]) if stats[5] is not None else 0,
                    "Orange": int(stats[6]) if stats[6] is not None else 0,
                    "Red": int(stats[7]) if stats[7] is not None else 0
                },
                "rank_position": int(stats[8]) if stats[8] is not None else 1
            }
        else:
            # Fallback if no player data found
            context["player_stats"] = {
                "total_clicks": 1,
                "best_click": {"timer_value": float(current_timer_value), "color": color},
                "color_distribution": {"Purple": 0, "Blue": 0, "Green": 0, "Yellow": 0, "Orange": 0, "Red": 0},
                "rank_position": 1
            }
        
        # Get game context
        game_start_query = 'SELECT start_time FROM game_sessions WHERE id = %s'
        game_start_result = execute_query(game_start_query, (game_id,))
        if game_start_result and game_start_result[0]:
            start_time = game_start_result[0][0].replace(tzinfo=timezone.utc)
            current_time = datetime.datetime.now(timezone.utc)
            duration_seconds = (current_time - start_time).total_seconds()
            
            # Convert to EST for US context
            try:
                import pytz
                est = pytz.timezone('US/Eastern')
                current_est = current_time.astimezone(est)
                time_str = current_est.strftime("%I:%M %p EST")
            except:
                # Fallback if pytz not available
                time_str = current_time.strftime("%I:%M %p UTC")
            
            context["game_context"] = {
                "duration_seconds": float(duration_seconds),
                "duration_formatted": f"{int(duration_seconds//86400)} days, {int((duration_seconds%86400)//3600)} hours",
                "timer_duration": int(timer_duration),
                "color_interval_hours": float(timer_duration / 21600),  # 6 color segments
                "current_time_est": time_str,
                "current_timer_value": float(current_timer_value),
                "timer_percentage": float((current_timer_value / timer_duration) * 100)
            }
        
        # Get recent clicks (last 200)
        recent_clicks_query = '''
            SELECT u.user_name, bc.timer_value, bc.click_time,
                CASE
                    WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 83.33 THEN 'Purple'
                    WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 66.67 THEN 'Blue'
                    WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 50.00 THEN 'Green'
                    WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 33.33 THEN 'Yellow'
                    WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 16.67 THEN 'Orange'
                    ELSE 'Red'
                END as color
            FROM button_clicks bc
            JOIN users u ON bc.user_id = u.user_id
            WHERE bc.game_id = %s
            ORDER BY bc.click_time DESC
            LIMIT 200
        '''
        recent_params = (timer_duration,) * 5 + (game_id,)
        recent_result = execute_query(recent_clicks_query, recent_params)
        
        if recent_result:
            context["recent_clicks"] = []
            for i, click in enumerate(recent_result):
                click_data = {
                    "player": str(click[0]) if click[0] else "Unknown",
                    "timer_value": float(click[1]) if click[1] is not None else 0.0,
                    "timestamp": click[2].isoformat() if click[2] else "",
                    "color": str(click[3]) if click[3] else "Unknown"
                }
                # Add gap to previous click
                if i < len(recent_result) - 1:
                    prev_click_time = recent_result[i + 1][2]
                    if prev_click_time and click[2]:
                        gap_seconds = (click[2] - prev_click_time).total_seconds()
                        click_data["gap_to_previous"] = float(gap_seconds)
                
                context["recent_clicks"].append(click_data)
        
        # Get social context
        if recent_result and len(recent_result) > 1:
            previous_clicker = str(recent_result[1][0]) if recent_result[1][0] else "Unknown"
            if recent_result[0][2]:
                gap_seconds = (datetime.datetime.now(timezone.utc) - recent_result[0][2].replace(tzinfo=timezone.utc)).total_seconds()
                context["social_context"] = {
                    "previous_clicker": previous_clicker,
                    "gap_since_last": float(gap_seconds)
                }
        
        # Get chat context - placeholder for now
        context["chat_context"] = []
        
        return context
        
    except Exception as e:
        logger.error(f"Error gathering comprehensive context: {e}\n{traceback.format_exc()}")
        # Return safe fallback context
        return {
            "player_stats": {
                "total_clicks": 1,
                "best_click": {"timer_value": float(current_timer_value), "color": color},
                "color_distribution": {"Purple": 0, "Blue": 0, "Green": 0, "Yellow": 0, "Orange": 0, "Red": 0},
                "rank_position": 1
            },
            "game_context": {
                "duration_seconds": 0.0,
                "duration_formatted": "0 days, 0 hours",
                "timer_duration": int(timer_duration),
                "color_interval_hours": 2.0,
                "current_time_est": "Unknown",
                "current_timer_value": float(current_timer_value),
                "timer_percentage": float((current_timer_value / timer_duration) * 100)
            },
            "recent_clicks": [],
            "social_context": {},
            "chat_context": []
        }

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
        
        # Use the API key from config
        response = api_instance.gifs_search_get(
            api_key=config['giphy_api_key'],  # Using config here
            q=search_string,
            limit=5,
            rating='g'
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


# TimerButton class for the button with Nextcord UI
# This class creates a button that resets the timer when clicked.
# The callback method handles button clicks, updating the timer and database.
# Features double-click prevention that requires X different users to click before repeat clicks.
# Checks cooldowns and prevents users from clicking within the cooldown period.
# Updates user's color rank and adds roles based on timer value.
# Sends announcement messages to the game chat channel when clicked.
class TimerButton(nextcord.ui.Button):
    _cooldown_cache = defaultdict(float)  # Existing cache for performance
    _cache_cleanup_threshold = 1000  # Existing threshold
    _cooldown_messages = {}  # {user_id: (message, timestamp)}
    _MESSAGE_CACHE_DURATION = 300  # 5 minutes in seconds

    @classmethod
    def _get_cached_cooldown_message(cls, user_id):
        """Get cached cooldown message if it exists and is not expired"""
        if user_id in cls._cooldown_messages:
            message, timestamp = cls._cooldown_messages[user_id]
            if time.time() - timestamp < cls._MESSAGE_CACHE_DURATION:
                return message
        return None

    @classmethod
    async def _check_double_click_prevention(cls, guild_id, user_id):
        """
        Check if user can click based on double-click prevention rules using database
        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID attempting to click
        Returns:
            bool: True if user can click, False if prevented
        """
        try:
            # Get the sequential click requirement for this guild
            sequential_requirement = await cls._get_sequential_click_requirement(guild_id)
            
            if sequential_requirement <= 0:
                logger.info(f"Double-click prevention disabled for guild {guild_id} (requirement: {sequential_requirement})")
                return True

            # Get this user's most recent click time for this guild's game
            user_last_click_query = '''
                SELECT MAX(bc.click_time)
                FROM button_clicks bc
                INNER JOIN game_sessions gs ON bc.game_id = gs.id
                WHERE bc.user_id = %s 
                AND gs.guild_id = %s 
                AND gs.end_time IS NULL
            '''
            user_result = execute_query(user_last_click_query, (user_id, guild_id))
            
            # If user has never clicked, allow the click
            if not user_result or not user_result[0] or user_result[0][0] is None:
                logger.info(f"Double-click prevention: User {user_id} has no previous clicks, allowing")
                return True
                
            user_last_click_time = user_result[0][0]
            
            # Count distinct users who clicked after this user's last click
            distinct_users_query = '''
                SELECT COUNT(DISTINCT bc.user_id)
                FROM button_clicks bc
                INNER JOIN game_sessions gs ON bc.game_id = gs.id
                WHERE gs.guild_id = %s 
                AND gs.end_time IS NULL
                AND bc.click_time > %s
                AND bc.user_id != %s
            '''
            distinct_result = execute_query(distinct_users_query, (guild_id, user_last_click_time, user_id))
            
            if not distinct_result or not distinct_result[0]:
                different_users_count = 0
            else:
                different_users_count = distinct_result[0][0] or 0
            
            can_click = different_users_count >= sequential_requirement
            
            logger.info(f"Double-click prevention check for user {user_id} in guild {guild_id}: "
                       f"Need {sequential_requirement} different users, found {different_users_count}, "
                       f"can_click={can_click}")
            
            return can_click
            
        except Exception as e:
            logger.error(f"Error in double-click prevention check for user {user_id}, guild {guild_id}: {e}")
            logger.error(traceback.format_exc())
            # On error, allow the click to avoid blocking legitimate users
            return True

    @classmethod
    async def _get_sequential_click_requirement(cls, guild_id):
        """
        Get the sequential click requirement for a guild from database
        Args:
            guild_id: Discord guild ID
        Returns:
            int: Number of different users required before repeat clicks (default: 1)
        """
        try:
            query = '''
                SELECT sequential_click_requirement 
                FROM game_sessions 
                WHERE guild_id = %s AND end_time IS NULL
                ORDER BY start_time DESC 
                LIMIT 1
            '''
            result = execute_query(query, (guild_id,))
            if result and result[0] and result[0][0] is not None:
                requirement = int(result[0][0])
                logger.info(f"Sequential click requirement for guild {guild_id}: {requirement}")
                return requirement
            return 0  # Default requirement
        except Exception as e:
            logger.error(f"Error getting sequential click requirement for guild {guild_id}: {e}")
            return 0  # Safe default

    def __init__(self, bot, style=nextcord.ButtonStyle.primary, label="Click me!", timer_value=0, game_id=None):
        # Initialize with a custom_id based on game_id for persistence
        custom_id = f"button_game_{game_id}" if game_id else None
        super().__init__(style=style, label=label, custom_id=custom_id)
        self.bot = bot
        self.timer_value = timer_value
        self.game_id = game_id
        global lock
        self._interaction_lock = lock

    @classmethod
    def _cleanup_cache(cls):
        """Clean up old entries from the cooldown cache"""
        current_time = time.time()
        # Remove entries older than 24 hours
        expired_users = [user_id for user_id, last_time in cls._cooldown_cache.items() 
                        if current_time - last_time > 86400]  # 24 hours in seconds
        for user_id in expired_users:
            del cls._cooldown_cache[user_id]

    # Callback method for the button, called when the button is clicked
    async def callback(self, interaction: nextcord.Interaction):
        global game_cache, lock
        handler = None
        
        # Capture the most accurate timestamp and start time immediately.
        click_time = interaction.created_at
        task_run_time = datetime.datetime.now(timezone.utc)

        try:
            # First defer the interaction before acquiring the lock
            logger.info(f"Button clicked by {interaction.user.id} at {click_time.isoformat()} - Component ID: {self.custom_id}")
            try:
                await interaction.response.defer(ephemeral=True, with_message=True)
            except nextcord.errors.NotFound as e:
                logger.error(f"Interaction expired before deferral: {e}")
                return
            except Exception as e:
                logger.error(f"Error deferring interaction: {e}")
                return
            
            # Acquire a per-game Redis lock (falls back to local lock if Redis unavailable)
            game_id = None
            try:
                game_session_tmp = await get_game_session_by_guild_id(interaction.guild.id)
                if game_session_tmp:
                    game_id = game_session_tmp['game_id']
            except Exception:
                game_id = None

            lock_ctx = None
            if game_id is not None:
                try:
                    lock_ctx = RedisLock(game_id=game_id, timeout=5.0)
                except Exception:
                    lock_ctx = None

            # If Redis lock not available, use local asyncio lock
            if lock_ctx is None:
                lock_ctx = self._interaction_lock

            async with lock_ctx:
                # Logging for which lock was used
                if isinstance(lock_ctx, RedisLock):
                    logger.info(f"Redis lock acquired for game {game_id} by {interaction.user.id}")
                else:
                    logger.info(f"Local lock acquired for {interaction.user.id}")
                
                # Followup with user that the click is being processed
                # Debug user blocking (keeping existing logic)
                if interaction.user.id in [116341342430298115]: return

                await interaction.followup.send("You attempt a click...", ephemeral=True)
                
                try:
                    # Get the game session and button message
                    game_session = await get_game_session_by_guild_id(interaction.guild.id)
                    game_id = game_session['game_id']
                    timer_duration = game_session['timer_duration']
                    cooldown_duration = game_session['cooldown_duration']
                    
                    # Debug log the current state
                    logger.info(f"Processing click for game {game_id} at {click_time}")
                    cached_game = game_cache.get_game_cache(game_id)
                    if cached_game:
                        logger.info(f"Cache state - Last click: {cached_game['latest_click_time']}, Timer value: {cached_game['last_timer_value']}")
                    
                    button_message = await get_button_message(game_id, self.bot)
                    embed = button_message.embeds[0]
                    user_id = interaction.user.id
                    
                    is_expired, current_timer_value = await is_timer_expired(game_id)
                    
                    if is_expired:
                        logger.error(f"Game {game_id} timer expired: {current_timer_value}")
                        await interaction.followup.send("The timer has expired! Game over!", ephemeral=True)
                        return
                        
                    logger.info(f"Processing click with timer value: {current_timer_value}")

                    # Check double-click prevention using database
                    if not await self._check_double_click_prevention(interaction.guild.id, user_id):
                        sequential_requirement = await self._get_sequential_click_requirement(interaction.guild.id)
                        logger.info(f'Double-click prevention: User {interaction.user} blocked, needs {sequential_requirement} different users to click first')
                        await interaction.followup.send(
                            f"Hold your horses, brave warrior! You must wait for {sequential_requirement} different adventurer{'s' if sequential_requirement != 1 else ''} to click before you can click again. "
                            f"The button demands variety in its champions!", 
                            ephemeral=True
                        )
                        return

                    # Check if the user is on cooldown and alert them if they are
                    try:
                        # Always get the user's last click for this game
                        query = '''
                            SELECT MAX(click_time)
                            FROM button_clicks
                            WHERE user_id = %s
                            AND game_id = %s
                        '''
                        params = (interaction.user.id, game_id)
                        result = execute_query(query, params)
                        
                        if result and result[0][0] is not None:
                            latest_click_time_user = result[0][0].replace(tzinfo=timezone.utc)
                            cooldown_expiry = latest_click_time_user + datetime.timedelta(hours=cooldown_duration)
                            cooldown_remaining = int((cooldown_expiry - click_time).total_seconds())
                            if cooldown_remaining > 0:
                                formatted_cooldown = f"{format(int(cooldown_remaining//3600), '02d')}:{format(int(cooldown_remaining%3600//60), '02d')}:{format(int(cooldown_remaining%60), '02d')}"
                                display_name = interaction.user.display_name
                                if not display_name:
                                    display_name = interaction.user.name
                                # Check for cached message
                                cached_message = self._get_cached_cooldown_message(interaction.user.id)
                                if cached_message:
                                    cooldown_message = cached_message
                                else:
                                    handler = CharacterHandler.get_instance()
                                    # Generate new message and cache it - FIX: properly handle tuple return
                                    cooldown_response_tuple = await handler.generate_cooldown_message(
                                        time_remaining=formatted_cooldown,
                                        player_name=display_name
                                    )
                                    # Extract just the message text (first element of tuple)
                                    cooldown_message = cooldown_response_tuple[0] if isinstance(cooldown_response_tuple, tuple) else cooldown_response_tuple
                                    self._cooldown_messages[interaction.user.id] = (cooldown_message, time.time())
                                await interaction.followup.send(cooldown_message, ephemeral=True)
                                logger.info(f'Button click rejected. User {interaction.user} is on cooldown for {formatted_cooldown}')
                                return
                    except Exception as e:
                        tb = traceback.format_exc()
                        logger.error(f'Error processing cooldown check: {e}, {tb}')
                        return

                    await interaction.message.add_reaction("⏳")

                    # Update user first
                    display_name = interaction.user.display_name or interaction.user.name
                    timer_color_name = get_color_name(current_timer_value, timer_duration)
                    cooldown_expiration = click_time + datetime.timedelta(hours=cooldown_duration)
                    
                    success = user_manager.add_or_update_user(
                        user_id=interaction.user.id,
                        cooldown_expiration=cooldown_expiration,
                        color_rank=timer_color_name,
                        timer_value=current_timer_value,
                        user_name=display_name,
                        game_id=game_id,
                        latest_click_var=click_time
                    )
                    
                    if not success:
                        logger.error(f'Failed to update user data for {interaction.user}')
                        await interaction.followup.send("Error processing your click. Please try again.", ephemeral=True)
                        return

                    # Enqueue the button click for background DB sync via Redis stream
                    try:
                        click_time_str = click_time.isoformat() if hasattr(click_time, 'isoformat') else str(click_time)
                        await push_click_to_queue(
                            game_id=game_id,
                            user_id=interaction.user.id,
                            click_time=click_time_str,
                            timer_value=current_timer_value,
                            user_name=display_name,
                            old_timer=None
                        )
                        logger.info(f'Click enqueued for user {interaction.user.id} in game {game_id}')
                    except Exception as e:
                        # If enqueue fails (Redis unavailable or other), fallback to direct DB insert
                        logger.error(f'Failed to enqueue click, falling back to direct DB insert: {e}')
                        try:
                            query = 'INSERT INTO button_clicks (user_id, click_time, timer_value, game_id) VALUES (%s, %s, %s, %s)'
                            params = (interaction.user.id, click_time, current_timer_value, game_id)
                            success = execute_query(query, params, commit=True)
                            if not success:
                                logger.error(f'Failed to insert button click data (fallback). User: {interaction.user}, Timer Value: {current_timer_value}, Game ID: {game_session["game_id"]}')
                                return
                            logger.info(f'Data inserted for {interaction.user} (fallback)!')
                        except Exception as db_e:
                            logger.error(f'Fallback DB insert failed: {db_e}')
                            return

                    # Update the user's color rank and add the role to the user
                    guild = interaction.guild
                    timer_color_name = get_color_name(current_timer_value, timer_duration)
                    color_role = nextcord.utils.get(guild.roles, name=timer_color_name)
        
                    if color_role:
                        try:
                            await interaction.user.add_roles(color_role)
                            logger.info(f'Role added to {interaction.user}: {color_role.name}')
                        except nextcord.errors.Forbidden:
                            logger.error(f'Failed to add role to {interaction.user}: {color_role.name}')
                            pass
                        except Exception as e:
                            tb = traceback.format_exc()
                            logger.error(f'Error while adding role to {interaction.user}: {e}, {tb}')
                            pass
                    
                    await interaction.followup.send("Button clicked! You have earned a " + timer_color_name + " click!", ephemeral=True)

                    # Create an embed message that announces the button click in the game chat channel
                    color_emoji = get_color_emoji(current_timer_value, timer_duration)
                    current_timer_value = int(current_timer_value)
                    formatted_remaining_time = f"{format(current_timer_value//3600, '02d')} hours {format(current_timer_value%3600//60, '02d')} minutes and {format(round(current_timer_value%60), '02d')} seconds"
                    color_state = get_color_state(current_timer_value, timer_duration)
                    embed = nextcord.Embed(title="", description=f"{color_emoji} {interaction.user.mention} just reset the timer at {formatted_remaining_time} left, for {timer_color_name} rank!", color=nextcord.Color.from_rgb(*color_state))
                    chat_channel = self.bot.get_channel(game_session['game_chat_channel_id'])
                    display_name = interaction.user.display_name
                    if not display_name: display_name = interaction.user.name
                    embed.description = f"{color_emoji}! {display_name} ({interaction.user.mention}), the {timer_color_name} rank warrior, has valiantly reset the timer with a mere {formatted_remaining_time} remaining!\nLet their bravery be celebrated throughout the realm!"

                    # Get user's total clicks and best color
                    query = '''
                        SELECT 
                            COUNT(*) as total_clicks,
                            MIN(timer_value) as lowest_timer,
                            (
                                SELECT color_rank 
                                FROM users 
                                WHERE user_id = %s
                            ) as best_color
                        FROM button_clicks 
                        WHERE user_id = %s 
                        AND game_id = %s
                    '''
                    params = (interaction.user.id, interaction.user.id, game_id)
                    user_stats = execute_query(query, params)

                    if not user_stats or not user_stats[0]:
                        user_clicks_count = 1  # First click
                        user_best_color = timer_color_name  # Current color will be their best
                    else:
                        user_clicks_count = user_stats[0][0] + 1  # Add 1 for current click
                        user_best_color = user_stats[0][2] or timer_color_name

                    # Gather comprehensive context for LLM
                    comprehensive_context = await gather_comprehensive_context(
                        game_id=game_id,
                        user_id=interaction.user.id,
                        current_timer_value=current_timer_value,
                        timer_duration=timer_duration,
                        color=timer_color_name,
                        bot=self.bot
                    )
                    
                    # Add current click context
                    comprehensive_context.update({
                        'color': timer_color_name,
                        'timer_value': current_timer_value,
                        'timer_duration': timer_duration,
                        'player_name': display_name,
                        'total_clicks': user_clicks_count,
                        'best_color': user_best_color
                    })
                    
                    # Get chat context from the chat channel
                    try:
                        chat_channel = self.bot.get_channel(game_session['game_chat_channel_id'])
                        if chat_channel:
                            chat_messages = []
                            async for message in chat_channel.history(limit=20):
                                if not message.author.bot:  # Skip bot messages
                                    chat_messages.append({
                                        "player": message.author.display_name or message.author.name,
                                        "message": message.content,
                                        "timestamp": message.created_at.isoformat()
                                    })
                            comprehensive_context["chat_context"] = chat_messages[:10]  # Last 10 human messages
                    except Exception as e:
                        logger.error(f"Error gathering chat context: {e}")
                        comprehensive_context["chat_context"] = []
                    
                    
                    if handler == None:
                        handler = CharacterHandler.get_instance()
                    
                    # Generate LLM response with comprehensive context
                    llm_response, gif_keywords = await handler.generate_click_response(comprehensive_context)


                    # Calculate the time claimed - this is what we're adding
                    time_claimed = timer_duration - current_timer_value
                    formatted_time_claimed = f"{format(time_claimed//3600, '02d')} hours {format(time_claimed%3600//60, '02d')} minutes and {format(round(time_claimed%60), '02d')} seconds"

                    # Then modify the embed description to include the time claimed
                    embed = nextcord.Embed(title="", color=nextcord.Color.from_rgb(*color_state))
                    base_description = (
                        f"{color_emoji}! {display_name} ({interaction.user.mention}), "
                        f"the {timer_color_name} rank warrior, has valiantly reset the timer "
                        f"with a mere {formatted_remaining_time} remaining!\n"
                        f"**Time Claimed: {formatted_time_claimed}**\n\n\n"
                        f"Let their bravery be celebrated throughout the realm!\n\n"
                        f"The Button Speaks: *{llm_response}*\n\n"
                    )
                    embed.description = base_description

                    await chat_channel.send(embed=embed)

                    # Determine if we should send a GIF based on color and random chance
                    should_send_gif = random.random() < 0.25  # 25% chance
                    if timer_color_name in ['Red', 'Orange']:
                        should_send_gif = random.random() < 0.7  # 70% chance for red/orange
                    
                    if should_send_gif and gif_keywords:
                        # Determine timing context for GIF selection
                        timer_percentage = (current_timer_value / timer_duration) * 100
                        timing_context = None
                        if timer_percentage >= 70:
                            timing_context = "early_click"
                        elif timer_percentage <= 30:
                            timing_context = "late_click"
                        
                        await send_gif_enhanced(chat_channel, gif_keywords, timer_color_name, timing_context)
                    
                    game_cache.update_game_cache(game_id, click_time, None, None, display_name, current_timer_value)
                    
                    # Update Redis cache with the new click data
                    try:
                        await game_state_cache.update_game_state(
                            game_id=game_id,
                            last_click_time=click_time,
                            timer_value=current_timer_value,
                            latest_player_name=display_name,
                            total_clicks=None,  # Will be incremented in background
                            is_active=True
                        )
                        logger.debug(f"Updated Redis cache for game {game_id} after click")
                    except Exception as cache_error:
                        logger.error(f"Failed to update Redis cache for game {game_id}: {cache_error}")
                        # Don't fail the click operation if cache update fails

                except Exception as e:
                    tb = traceback.format_exc()
                    logger.error(f'Error 1 processing button click: {e}, {tb}')
                    await interaction.followup.send("Something went wrong. Please try again later.", ephemeral=True)
            task_run_time = datetime.datetime.now(timezone.utc) - task_run_time
            logger.info(f'Callback run time: {task_run_time.total_seconds()} seconds')
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f'Error 2 processing button click: {e}, {tb}')
        finally:
            # if reaction is present from earlier, remove it
            try:
                await interaction.message.remove_reaction("⏳", self.bot.user)
            except nextcord.errors.NotFound as e:
                logger.error(f"Reaction not found: {e}")
            except Exception as e:
                logger.error(f"Error removing reaction: {e}")


async def is_timer_expired(game_id):
    """
    Check if the timer for a given game has expired using Redis cache with MySQL fallback
    Args:
        game_id: The game ID to check
    Returns:
        tuple: (is_expired: bool, current_timer_value: float)
    """
    try:
        # Try Redis cache first for much faster response
        is_expired, current_timer = await game_state_cache.calculate_current_timer(game_id)
        logger.debug(f"Timer check for game {game_id}: expired={is_expired}, value={current_timer:.1f}s (Redis)")
        return is_expired, current_timer
        
    except Exception as e:
        logger.error(f"Redis timer calculation failed for game {game_id}: {e}")
        # Fallback to original MySQL method
        logger.warning(f"Falling back to MySQL timer calculation for game {game_id}")
        
        try:
            query = '''
                SELECT click_time, timer_value
                FROM button_clicks 
                WHERE game_id = %s
                ORDER BY click_time DESC
                LIMIT 1
            '''
            result = execute_query(query, (game_id,))
            
            if not result or not result[0]:
                game_session = await get_game_session_by_id(game_id)
                return False, game_session['timer_duration']
                
            last_click_time, timer_value = result[0]
            current_time = datetime.datetime.now(timezone.utc)
            elapsed_time = (current_time - last_click_time.replace(tzinfo=timezone.utc)).total_seconds()
            
            # Use the full timer_duration from game_session as the start point
            game_session = await get_game_session_by_id(game_id)
            current_timer = max(0, float(game_session['timer_duration']) - elapsed_time)
            
            logger.debug(f"Timer check for game {game_id}: expired={current_timer <= 0}, value={current_timer:.1f}s (MySQL fallback)")
            return current_timer <= 0, current_timer
            
        except Exception as fallback_error:
            logger.error(f"MySQL fallback timer calculation also failed for game {game_id}: {fallback_error}")
            logger.error(traceback.format_exc())
            return True, 0