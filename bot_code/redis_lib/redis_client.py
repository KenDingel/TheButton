# Redis Client Connection Management
"""
Redis connection management with circuit breaker pattern and health checks
"""

import asyncio
import time
import os
from typing import Optional, Any
import redis.asyncio
from utils.utils import config, logger


class CircuitBreaker:
    """Circuit breaker pattern implementation for Redis operations"""
    
    def __init__(self, failure_threshold: int = 5, timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        
    async def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection"""
        if self.state == "OPEN":
            if self.last_failure_time and time.time() - self.last_failure_time > self.timeout:
                self.state = "HALF_OPEN"
                logger.info("Circuit breaker transitioning from OPEN to HALF_OPEN")
            else:
                raise CircuitBreakerOpenError("Circuit breaker is OPEN")
                
        try:
            result = await func(*args, **kwargs)
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failure_count = 0
                logger.info("Circuit breaker transitioning from HALF_OPEN to CLOSED")
            return result
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                logger.error(f"Circuit breaker transitioning to OPEN after {self.failure_count} failures")
            raise


class CircuitBreakerOpenError(Exception):
    """Exception raised when circuit breaker is open"""
    pass


class RedisClient:
    """Redis connection client with connection pooling and circuit breaker"""
    
    def __init__(self):
        self.pool: Optional[redis.asyncio.ConnectionPool] = None
        self.client: Optional[redis.asyncio.Redis] = None
        self._circuit_breaker = CircuitBreaker()
        self._initialized = False
        
    async def initialize(self) -> bool:
        """Initialize Redis connection pool"""
        try:
            logger.info("Initializing Redis connection...")
            
            redis_config = config.get('redis', {})
            
            # Create connection pool
            self.pool = redis.asyncio.ConnectionPool(
                host=redis_config.get('host', 'localhost'),
                port=redis_config.get('port', 6379),
                db=redis_config.get('db', 0),
                password=redis_config.get('password'),
                max_connections=redis_config.get('connection_pool_size', 10),
                socket_timeout=redis_config.get('socket_timeout', 5),
                socket_connect_timeout=redis_config.get('socket_connect_timeout', 5),
                retry_on_timeout=True,
                health_check_interval=30,
                encoding='utf-8',
                decode_responses=True
            )
            
            # Create Redis client
            self.client = redis.asyncio.Redis(connection_pool=self.pool)
            
            # Test connection
            await self.health_check()
            
            self._initialized = True
            logger.info("Redis connection initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Redis connection: {e}")
            self._initialized = False
            return False
    
    async def health_check(self) -> bool:
        """Check Redis connectivity"""
        try:
            if not self.client:
                return False
                
            await self._circuit_breaker.call(self.client.ping)
            return True
            
        except CircuitBreakerOpenError:
            logger.warning("Redis health check failed: Circuit breaker is open")
            return False
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False
    
    async def get_client(self) -> Optional[redis.asyncio.Redis]:
        """Get Redis client if available and healthy"""
        if not self._initialized or not self.client:
            return None
            
        # Quick health check
        try:
            await self._circuit_breaker.call(self.client.ping)
            return self.client
        except Exception:
            return None
    
    async def execute_with_fallback(self, operation, *args, fallback_value=None, **kwargs):
        """
        Execute Redis operation with fallback value if Redis is unavailable
        """
        try:
            client = await self.get_client()
            if not client:
                logger.warning("Redis client unavailable, returning fallback value")
                return fallback_value
                
            return await self._circuit_breaker.call(operation, *args, **kwargs)
            
        except CircuitBreakerOpenError:
            logger.warning("Redis circuit breaker is open, returning fallback value")
            return fallback_value
        except Exception as e:
            logger.error(f"Redis operation failed: {e}, returning fallback value")
            return fallback_value
    
    async def close(self):
        """Close Redis connection"""
        if self.client:
            try:
                await self.client.close()
                logger.info("Redis connection closed")
            except Exception as e:
                logger.error(f"Error closing Redis connection: {e}")
        
        if self.pool:
            try:
                await self.pool.disconnect()
                logger.info("Redis connection pool closed")
            except Exception as e:
                logger.error(f"Error closing Redis connection pool: {e}")
                
        self._initialized = False
    
    def is_available(self) -> bool:
        """Check if Redis is available (circuit breaker not open)"""
        return (self._initialized and 
                self.client is not None and 
                self._circuit_breaker.state != "OPEN")


# Global Redis client instance
redis_client = RedisClient()
