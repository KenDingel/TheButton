import datetime
from datetime import timezone
import traceback
from utils import logger
from database import execute_query

class UserManager:
    def __init__(self):
        self.status = None
        self.user_cache = {}

    def add_or_update_user(self, user_id, cooldown_expiration, color_rank, timer_value, user_name, game_id, latest_click_var=None):
        global cursor, db
        try:
            query = '''
                INSERT INTO users (user_id, cooldown_expiration, color_rank, total_clicks, lowest_click_time, latest_click_time, user_name, game_id)
                VALUES (%s, %s, %s, 1, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    cooldown_expiration = VALUES(cooldown_expiration),
                    color_rank = VALUES(color_rank),
                    total_clicks = total_clicks + 1,
                    lowest_click_time = LEAST(lowest_click_time, VALUES(lowest_click_time)),
                    latest_click_time = VALUES(latest_click_time)
            '''
            latest_click_time = latest_click_var if latest_click_var else datetime.datetime.now(timezone.utc)
            params = (user_id, cooldown_expiration, color_rank, timer_value, latest_click_time, user_name, game_id)
            success = execute_query(query, params, commit=True)
            if not success:
                return False
            
            self.user_cache[user_id] = {
                'cooldown_expiration': cooldown_expiration,
                'color_rank': color_rank,
                'timer_value': timer_value,
                'user_name': user_name,
                'game_id': game_id,
                'latest_click_time': latest_click_time
            }
            
            return True
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f'Error adding or updating user: {e}, {tb}')
            return False

    def remove_expired_cooldowns(self):
        global cursor, db
        try:
            query = 'UPDATE users SET cooldown_expiration = NULL WHERE cooldown_expiration <= %s'
            params = (datetime.datetime.now(timezone.utc),)
            success = execute_query(query, params)
            if not success: 
                return
            db.commit()
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f'Error removing expired cooldowns: {e}, {tb}')
            
    def get_user_from_cache(self, user_id):
        cache = self.user_cache.get(user_id)
        if cache:
            return cache
        return None