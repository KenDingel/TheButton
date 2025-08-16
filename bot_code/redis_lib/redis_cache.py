# Redis Game State Cache
"""
Game state caching operations for The Button Game

Provides fast access to:
- Game state (timer, clicks, players)
- Timer calculations
- Cache warming and invalidation
"""

import json
import datetime
from datetime import timezone
from typing import Dict, Optional, Tuple, Any
from database.database import execute_query, get_game_session_by_id
from utils.utils import logger, config
from .redis_client import redis_client


class GameStateCache:
    """Redis-based game state cache with MySQL fallback"""
    
    def __init__(self):
        self.redis = redis_client
    
    def _get_game_state_key(self, game_id: int) -> str:
        """Get Redis key for game state"""
        return f"game:{game_id}:state"
    
    def _serialize_game_state(self, state: Dict[str, Any]) -> Dict[str, str]:
        """Serialize game state for Redis storage"""
        serialized = {}
        for key, value in state.items():
            if isinstance(value, datetime.datetime):
                serialized[key] = value.isoformat()
            elif value is None:
                serialized[key] = ""
            else:
                serialized[key] = str(value)
        return serialized
    
    def _deserialize_game_state(self, state: Dict[str, str]) -> Dict[str, Any]:
        """Deserialize game state from Redis"""
        if not state:
            return {}
            
        deserialized = {}
        for key, value in state.items():
            if not value:  # Empty string means None
                deserialized[key] = None
            elif key.endswith('_time'):
                try:
                    deserialized[key] = datetime.datetime.fromisoformat(value)
                except (ValueError, TypeError):
                    deserialized[key] = None
            elif key in ['timer_value', 'timer_duration', 'cooldown_duration']:
                try:
                    deserialized[key] = float(value)
                except (ValueError, TypeError):
                    deserialized[key] = 0.0
            elif key in ['total_clicks', 'total_players', 'game_id']:
                try:
                    deserialized[key] = int(value)
                except (ValueError, TypeError):
                    deserialized[key] = 0
            elif key == 'is_active':
                deserialized[key] = value.lower() == 'true'
            else:
                deserialized[key] = value
                
        return deserialized
    
    async def get_game_state(self, game_id: int) -> Optional[Dict[str, Any]]:
        """Get complete game state from cache with MySQL fallback"""
        try:
            client = await self.redis.get_client()
            if client:
                key = self._get_game_state_key(game_id)
                state = await client.hgetall(key)
                if state:
                    logger.debug(f"Cache hit for game {game_id}")
                    return self._deserialize_game_state(state)
                else:
                    logger.debug(f"Cache miss for game {game_id}")
        except Exception as e:
            logger.error(f"Redis error getting game state for {game_id}: {e}")
        
        # Fallback to database
        return await self._load_from_database(game_id)
    
    async def _load_from_database(self, game_id: int) -> Optional[Dict[str, Any]]:
        """Load game state from MySQL database"""
        try:
            # Get game session data
            game_session = await get_game_session_by_id(game_id)
            if not game_session:
                logger.warning(f"No game session found for game {game_id}")
                return None
            
            # Get latest click data
            click_query = '''
                SELECT users.user_name, button_clicks.click_time, button_clicks.timer_value,
                    (SELECT COUNT(*) FROM button_clicks WHERE game_id = %s) AS total_clicks,
                    (SELECT COUNT(DISTINCT user_id) FROM button_clicks WHERE game_id = %s) AS total_players
                FROM button_clicks
                INNER JOIN users ON button_clicks.user_id = users.user_id
                WHERE button_clicks.game_id = %s
                ORDER BY button_clicks.id DESC
                LIMIT 1
            '''
            click_result = execute_query(click_query, (game_id, game_id, game_id))
            
            if click_result and click_result[0]:
                # Game has clicks
                result = click_result[0]
                state = {
                    'game_id': game_id,
                    'last_click_time': result[1].replace(tzinfo=timezone.utc) if result[1] else None,
                    'timer_value': float(result[2]) if result[2] is not None else float(game_session['timer_duration']),
                    'total_clicks': int(result[3]) if result[3] is not None else 0,
                    'total_players': int(result[4]) if result[4] is not None else 0,
                    'latest_player_name': str(result[0]) if result[0] else "Unknown",
                    'timer_duration': float(game_session['timer_duration']),
                    'cooldown_duration': float(game_session['cooldown_duration']),
                    'is_active': game_session.get('end_time') is None
                }
            else:
                # No clicks yet - initial state
                state = {
                    'game_id': game_id,
                    'last_click_time': game_session['start_time'].replace(tzinfo=timezone.utc),
                    'timer_value': float(game_session['timer_duration']),
                    'total_clicks': 0,
                    'total_players': 0,
                    'latest_player_name': "Game Initialized",
                    'timer_duration': float(game_session['timer_duration']),
                    'cooldown_duration': float(game_session['cooldown_duration']),
                    'is_active': game_session.get('end_time') is None
                }
            
            # Cache the state in Redis for future use
            await self._cache_game_state(game_id, state)
            
            logger.info(f"Loaded game state from database for game {game_id}")
            return state
            
        except Exception as e:
            logger.error(f"Error loading game state from database for game {game_id}: {e}")
            return None
    
    async def _cache_game_state(self, game_id: int, state: Dict[str, Any]):
        """Cache game state in Redis"""
        try:
            client = await self.redis.get_client()
            if not client:
                return
                
            key = self._get_game_state_key(game_id)
            serialized = self._serialize_game_state(state)
            
            # Set with TTL
            ttl = config.get('cache', {}).get('game_state_ttl', 3600)
            await client.hset(key, mapping=serialized)
            await client.expire(key, ttl)
            
            logger.debug(f"Cached game state for game {game_id}")
            
        except Exception as e:
            logger.error(f"Error caching game state for game {game_id}: {e}")
    
    async def update_game_state(self, game_id: int, **updates):
        """Update specific fields in game state cache"""
        try:
            client = await self.redis.get_client()
            if not client:
                return
                
            key = self._get_game_state_key(game_id)
            serialized = self._serialize_game_state(updates)
            
            await client.hset(key, mapping=serialized)
            
            # Reset TTL
            ttl = config.get('cache', {}).get('game_state_ttl', 3600)
            await client.expire(key, ttl)
            
            logger.debug(f"Updated game state cache for game {game_id}: {list(updates.keys())}")
            
        except Exception as e:
            logger.error(f"Error updating game state cache for game {game_id}: {e}")
    
    async def calculate_current_timer(self, game_id: int) -> Tuple[bool, float]:
        """
        Calculate current timer value from cached data with MySQL fallback
        
        Returns:
            tuple: (is_expired: bool, current_timer_value: float)
        """
        try:
            state = await self.get_game_state(game_id)
            if not state:
                logger.warning(f"No game state found for game {game_id}")
                return True, 0.0
            
            last_click_time = state.get('last_click_time')
            timer_duration = state.get('timer_duration', 43200)  # Default 12 hours
            
            if not last_click_time:
                # No clicks yet, use full timer
                return False, float(timer_duration)
            
            # Calculate elapsed time since last click
            current_time = datetime.datetime.now(timezone.utc)
            if isinstance(last_click_time, str):
                last_click_time = datetime.datetime.fromisoformat(last_click_time)
            if last_click_time.tzinfo is None:
                last_click_time = last_click_time.replace(tzinfo=timezone.utc)
                
            elapsed_seconds = (current_time - last_click_time).total_seconds()
            current_timer = max(0.0, float(timer_duration) - elapsed_seconds)
            
            is_expired = current_timer <= 0.0
            
            logger.debug(f"Timer calculation for game {game_id}: elapsed={elapsed_seconds:.1f}s, "
                        f"current={current_timer:.1f}s, expired={is_expired}")
            
            return is_expired, current_timer
            
        except Exception as e:
            logger.error(f"Error calculating timer for game {game_id}: {e}")
            # Fallback to original database method
            return await self._fallback_timer_calculation(game_id)
    
    async def _fallback_timer_calculation(self, game_id: int) -> Tuple[bool, float]:
        """Fallback timer calculation using direct database query"""
        try:
            from utils.timer_button import is_timer_expired
            logger.warning(f"Using fallback timer calculation for game {game_id}")
            return await is_timer_expired(game_id)
        except Exception as e:
            logger.error(f"Fallback timer calculation failed for game {game_id}: {e}")
            return True, 0.0
    
    async def invalidate_game_cache(self, game_id: int):
        """Invalidate game state cache"""
        try:
            client = await self.redis.get_client()
            if not client:
                return
                
            key = self._get_game_state_key(game_id)
            await client.delete(key)
            
            logger.info(f"Invalidated cache for game {game_id}")
            
        except Exception as e:
            logger.error(f"Error invalidating cache for game {game_id}: {e}")
    
    async def warm_cache_for_active_games(self):
        """Warm Redis cache for all active games"""
        try:
            # Get all active games
            query = "SELECT id FROM game_sessions WHERE end_time IS NULL"
            result = execute_query(query, ())
            
            if not result:
                logger.info("No active games found for cache warming")
                return
                
            for row in result:
                game_id = row[0]
                try:
                    await self.get_game_state(game_id)  # This will cache it
                    logger.debug(f"Warmed cache for game {game_id}")
                except Exception as e:
                    logger.error(f"Error warming cache for game {game_id}: {e}")
            
            logger.info(f"Cache warming completed for {len(result)} active games")
            
        except Exception as e:
            logger.error(f"Error during cache warming: {e}")


# Global game state cache instance
game_state_cache = GameStateCache()
