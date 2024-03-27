#Game Cache
import datetime
from datetime import timezone
from bot_code.database.database import logger

class GameCache:
    def __init__(self):
        self.games = {}

    def update_game_cache(self, game_id, latest_click_time, total_clicks, total_players, latest_player_name, last_timer_value):
        logger.info(f'Updating game cache for game {game_id}')
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
        logger.info(f'Clearing game cache for game {game_id}')
        self.games.pop(game_id, None)
        logger.info(f'Game cache cleared for game {game_id}, {self.games}')

class ButtonMessageCache:
    def __init__(self):
        self.messages = {}

    def update_message_cache(self, message, game_id):
        logger.info(f'Updating message cache for message {message.id}')
        self.messages[game_id] = message
        logger.info(f'Message cache updated for message {message.id}, {self.messages}')

    async def get_game_id(self, game_id):
        message = self.messages.get(game_id, None)
        #test if message is still valid
        if message is not None:
            try:
                message = await message.channel.fetch_message(message.id)
                return message
            except Exception as e:
                logger.error(f'Failed to fetch message {message.id}: {e}')
                return None
        else:
            return None

game_cache = GameCache()
button_message_cache = ButtonMessageCache()