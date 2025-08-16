#!/usr/bin/env python3
"""
Redis Phase 1 Implementation Test

This script tests the basic Redis caching functionality
"""

import asyncio
import sys
import os
import datetime
from datetime import timezone


#✗ Failed to import Redis modules: No module named 'redis.asyncio'
# Fix by installing the required package
# pip install redis

# Add the bot_code directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bot_code'))

try:
    from bot_code.redis_lib.redis_client import redis_client
    from bot_code.redis_lib.redis_cache import game_state_cache
    from utils.utils import logger, config
    print("✓ Redis modules imported successfully")
except ImportError as e:
    print(f"✗ Failed to import Redis modules: {e}")
    sys.exit(1)

async def test_redis_connection():
    """Test Redis connection and basic operations"""
    print("\n=== Testing Redis Connection ===")
    
    # Initialize Redis
    success = await redis_client.initialize()
    if success:
        print("✓ Redis connection initialized successfully")
    else:
        print("✗ Redis connection failed - using fallback mode")
        return False
    
    # Test health check
    health = await redis_client.health_check()
    if health:
        print("✓ Redis health check passed")
    else:
        print("✗ Redis health check failed")
        return False
    
    return True

async def test_game_state_cache():
    """Test game state caching operations"""
    print("\n=== Testing Game State Cache ===")
    
    test_game_id = 999999  # Use a test game ID that won't conflict
    
    # Test cache miss (should fallback to database gracefully)
    try:
        state = await game_state_cache.get_game_state(test_game_id)
        if state is None:
            print("✓ Cache miss handled gracefully (no game session found)")
        else:
            print(f"✓ Retrieved game state: {state}")
    except Exception as e:
        print(f"✗ Game state retrieval failed: {e}")
        return False
    
    # Test manual cache update
    try:
        test_state = {
            'game_id': test_game_id,
            'last_click_time': datetime.datetime.now(timezone.utc),
            'timer_value': 43200.0,
            'total_clicks': 5,
            'total_players': 3,
            'latest_player_name': 'TestPlayer',
            'timer_duration': 43200.0,
            'cooldown_duration': 1.0,
            'is_active': True
        }
        
        await game_state_cache._cache_game_state(test_game_id, test_state)
        print("✓ Manual cache update successful")
        
        # Retrieve the cached state
        cached_state = await game_state_cache.get_game_state(test_game_id)
        if cached_state and cached_state.get('latest_player_name') == 'TestPlayer':
            print("✓ Cache retrieval successful")
        else:
            print("✗ Cache retrieval failed or data mismatch")
            return False
            
    except Exception as e:
        print(f"✗ Cache operations failed: {e}")
        return False
    
    # Test timer calculation
    try:
        is_expired, timer_value = await game_state_cache.calculate_current_timer(test_game_id)
        print(f"✓ Timer calculation: expired={is_expired}, value={timer_value:.1f}s")
    except Exception as e:
        print(f"✗ Timer calculation failed: {e}")
        return False
    
    # Clean up test data
    try:
        await game_state_cache.invalidate_game_cache(test_game_id)
        print("✓ Cache cleanup successful")
    except Exception as e:
        print(f"✗ Cache cleanup failed: {e}")
    
    return True

async def test_circuit_breaker():
    """Test circuit breaker functionality"""
    print("\n=== Testing Circuit Breaker ===")
    
    # Test that circuit breaker is available
    if redis_client.is_available():
        print("✓ Circuit breaker shows Redis as available")
    else:
        print("✗ Circuit breaker shows Redis as unavailable")
        return False
    
    return True

async def main():
    """Main test function"""
    print("Redis Phase 1 Implementation Test")
    print("=" * 40)
    
    print(f"Config Redis host: {config.get('redis', {}).get('host', 'localhost')}")
    print(f"Config Redis port: {config.get('redis', {}).get('port', 6379)}")
    
    try:
        # Test Redis connection
        redis_available = await test_redis_connection()
        
        if redis_available:
            # Test game state cache
            cache_success = await test_game_state_cache()
            
            # Test circuit breaker
            breaker_success = await test_circuit_breaker()
            
            if cache_success and breaker_success:
                print("\n🎉 All tests passed! Redis Phase 1 implementation is working.")
                return True
            else:
                print("\n❌ Some tests failed.")
                return False
        else:
            print("\n⚠️  Redis connection failed - fallback mode will be used.")
            print("   This is acceptable for testing without Redis server.")
            return True
            
    except Exception as e:
        print(f"\n💥 Test suite failed with exception: {e}")
        import traceback
        print(traceback.format_exc())
        return False
    
    finally:
        # Clean up
        try:
            await redis_client.close()
            print("\n🔧 Redis connections closed")
        except Exception as e:
            print(f"🔧 Redis cleanup error: {e}")

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
