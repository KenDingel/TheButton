# Button 
import datetime
from datetime import timezone
import traceback

# Local imports
from utils.utils import logger
from game.game_cache import button_message_cache
from database.database import update_local_game_sessions, game_sessions_dict

# Get button message
# This function is used to get the button message for the timer button.
# It first checks the cache for the button message, and if it is not found, it creates a new one.
async def get_button_message(game_id, bot):
    task_run_time = datetime.datetime.now(timezone.utc)
    game_id = int(game_id)
    
    if game_id in button_message_cache.messages:
        try:
            message = await button_message_cache.get_game_id(game_id)
            return message
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f'Error getting button message: {e}, {tb}')
    
    # Get the game session config to get the button channel id, then get the button channel object
    game_session_config = game_sessions_dict()[game_id]
    if not game_session_config:
        logger.error(f'No game session found for game {game_id}')
        update_local_game_sessions()
        game_session_config = game_sessions_dict()[game_id]
    button_channel = bot.get_channel(int(game_session_config['button_channel_id']))
    
    # Check if there is an existing button message for the game, and delete it if found
    is_message_found = False
    async for message in button_channel.history(limit=1):
        if message.author == bot.user and message.embeds:
            is_message_found = True
            await message.delete()
            logger.info(f'Found existing button message for game {game_id}, deleting and will create a new one...')
    
    # Create a new button message if no existing message is found (or if it was deleted) and update the cache
    if is_message_found:
        logger.error(f'No existing button message found for game {game_id}, creating a new one...')
        from button.button_functions import create_button_message # Import here to avoid circular import
        message = await create_button_message(game_id, bot)
        button_message_cache.update_message_cache(message, game_id)
        task_run_time = datetime.datetime.now(timezone.utc) - task_run_time
        logger.info(f'Get button message run time: {task_run_time.total_seconds()} seconds')
        return message
    return None

# Failed Interaction Count
# Used to keep track of the number of failed interactions.
# Then the bot can take action if the number of failed interactions exceeds a certain threshold.
class Failed_Interaction_Count:
    def __init__(self): self.failed_count = 0

    def increment(self): self.failed_count += 1

    def reset(self): self.failed_count = 0

    def get(self): return self.failed_count
    
# Create the Failed_Interactions instance
Failed_Interactions = Failed_Interaction_Count()