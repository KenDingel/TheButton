import datetime
from datetime import timezone
from database import logger

class GameCache:
    def __init__(self):
        self.games = {}

    def update_game_cache(self, game_id, latest_click_time, total_clicks, total_players, latest_player_name):
        logger.info(f'Updating game cache for game {game_id}')
        game_id = int(game_id)
        self.games[game_id] = {
            'latest_click_time': latest_click_time,
            'total_clicks': total_clicks,
            'total_players': total_players,
            'last_update_time': datetime.datetime.now(timezone.utc),
            'latest_player_name': latest_player_name
        }
        logger.info(f'Game cache updated for game {game_id}, {self.games}')

    def get_game_cache(self, game_id):
        game_id = int(game_id)
        return self.games.get(game_id, None)

class ButtonMessageCache:
    def __init__(self):
        self.messages = {}

    def update_message_cache(self, message, game_id):
        logger.info(f'Updating message cache for message {message.id}')
        self.messages[game_id] = message
        logger.info(f'Message cache updated for message {message.id}, {self.messages}')

    def get_game_id(self, game_id):
        return self.messages.get(game_id, None)

game_cache = GameCache()
button_message_cache = ButtonMessageCache()