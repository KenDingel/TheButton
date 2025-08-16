#!/usr/bin/env python3
"""
Script to clear Redis cache and force data reload for The Button games
"""

import asyncio
import sys
import os

# Add the bot_code directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'bot_code'))

from redis_lib.redis_client import redis_client

async def clear_game_cache():
    """Clear Redis cache for all games"""
    try:
        client = await redis_client.get_client()
        if not client:
            print("❌ Redis client not available")
            return
        
        # Get all game state keys
        keys = await client.keys("game:*:state")
        if keys:
            print(f"🗑️  Found {len(keys)} game cache keys to delete")
            deleted = await client.delete(*keys)
            print(f"✅ Deleted {deleted} cache keys")
        else:
            print("ℹ️  No game cache keys found")
            
        # Also clear any other game-related keys
        other_keys = await client.keys("game:*")
        if other_keys:
            print(f"🗑️  Found {len(other_keys)} other game keys to delete")
            deleted = await client.delete(*other_keys)
            print(f"✅ Deleted {deleted} other keys")
            
        print("🎯 Redis cache cleared! The bot will reload fresh data from the database.")
        
    except Exception as e:
        print(f"❌ Error clearing cache: {e}")

if __name__ == "__main__":
    asyncio.run(clear_game_cache())
