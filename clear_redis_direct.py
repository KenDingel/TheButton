#!/usr/bin/env python3
"""
Direct Redis cache clearing script
"""

import asyncio
import redis.asyncio as redis
import os

async def clear_cache_direct():
    """Clear Redis cache directly"""
    try:
        # Get Redis host from environment or default to localhost
        redis_host = os.getenv('REDIS_HOST', 'localhost')
        redis_port = int(os.getenv('REDIS_PORT', '6379'))
        
        print(f"🔌 Connecting to Redis at {redis_host}:{redis_port}")
        
        # Create direct Redis connection
        client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
        
        # Test connection
        await client.ping()
        print("✅ Redis connection successful")
        
        # Get all game state keys
        keys = await client.keys("game:*:state")
        if keys:
            print(f"🗑️  Found {len(keys)} game cache keys to delete")
            deleted = await client.delete(*keys)
            print(f"✅ Deleted {deleted} cache keys")
            
            # Also clear any other game-related cache
            other_keys = await client.keys("game:*")
            if other_keys:
                print(f"🗑️  Found {len(other_keys)} additional game keys")
                deleted_other = await client.delete(*other_keys)
                print(f"✅ Deleted {deleted_other} additional keys")
        else:
            print("ℹ️  No game cache keys found")
            
        await client.aclose()
        print("🔄 Cache cleared! Bot should reload data from database.")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    
    return True

if __name__ == "__main__":
    asyncio.run(clear_cache_direct())
