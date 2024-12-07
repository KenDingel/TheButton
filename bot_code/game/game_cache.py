#Game Cache
import datetime
from datetime import timezone
from database.database import logger

# GameCache class
# This class is used to cache game data for the timer button..
class GameCache:
    def __init__(self):
        self.games = {}

    def update_game_cache(self, game_id, latest_click_time, total_clicks, total_players, latest_player_name, last_timer_value):
        game_id = int(game_id)
        self.games[game_id] = {
            'latest_click_time': latest_click_time,
            'total_clicks': total_clicks,
            'total_players': total_players,
            'last_update_time': datetime.datetime.now(timezone.utc),
            'latest_player_name': latest_player_name,
            'last_timer_value': last_timer_value
        }
        logger.info(f'Game cache updated for game {game_id}, {self.games}')

    def get_game_cache(self, game_id):
        game_id = int(game_id)
        return self.games.get(game_id, None)
    
    def clear_game_cache(self, game_id):
        game_id = int(game_id)
        self.games.pop(game_id, None)
        logger.info(f'Game cache cleared for game {game_id}, {self.games}')

# ButtonMessageCache class
# This class is used to cache button messages for the timer button.
class ButtonMessageCache:
    def __init__(self):
        self.messages = {}

    def update_message_cache(self, message, game_id):
        message_id = message.id
        self.messages[game_id] = message_id
        logger.info(f'Message cache updated for message {message_id}, {self.messages}')

    async def get_message_cache(self, game_id):
        message_id = self.messages.get(game_id, None)
        if message_id is not None:
            try: 
                return message_id
            except Exception as e: 
                logger.error(f'Failed to fetch message {message_id}: {e}'); return None
        else:
            logger.error(f'No message found for game {game_id} in cache')
            return None
        
    async def cleanup_stale_messages(self):
        """Remove any stale message references"""
        stale_games = []
        for game_id, message_id in self.messages.items():
            try:
                if not message_id:
                    stale_games.append(game_id)
            except Exception as e:
                logger.error(f"Error checking message {message_id} for game {game_id}: {e}")
                stale_games.append(game_id)
        
        for game_id in stale_games:
            self.messages.pop(game_id, None)
            logger.info(f"Removed stale message cache for game {game_id}")

# Create the GameCache and ButtonMessageCache instances
game_cache = GameCache()
button_message_cache = ButtonMessageCache()