"""
Custom middleware for WebSocket authentication and performance monitoring.
"""

import json
import logging
import time
from typing import Optional
from urllib.parse import parse_qs

from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework.authtoken.models import Token

logger = logging.getLogger(__name__)
User = get_user_model()


class WebSocketAuthMiddleware(BaseMiddleware):
    """
    Custom WebSocket authentication middleware that supports both:
    1. Django sessions (from logged-in users)
    2. Token authentication (for API clients)
    """

    def __init__(self, inner):
        super().__init__(inner)

    async def __call__(self, scope, receive, send):
        # Add authentication to WebSocket connections
        if scope["type"] == "websocket":
            logger.info(f"WebSocket middleware called for: {scope.get('path')}")
            scope = await self.authenticate_websocket(scope)
        
        return await super().__call__(scope, receive, send)

    async def authenticate_websocket(self, scope):
        """Authenticate WebSocket connection using session or token."""
        
        logger.info(f"WebSocket authentication middleware called for {scope.get('path', 'unknown')}")
        logger.info(f"Query string: {scope.get('query_string', b'').decode()}")
        logger.info(f"Headers: {dict(scope.get('headers', []))}")
        
        # First try session authentication (for web users)
        user = scope.get("user")
        if user and not isinstance(user, AnonymousUser):
            logger.info(f"WebSocket authenticated via session: user {user.id}")
            return scope

        # Try token authentication from query parameters
        query_string = scope.get("query_string", b"").decode()
        query_params = parse_qs(query_string)
        
        token_key = None
        if "token" in query_params:
            token_key = query_params["token"][0]
        elif "auth_token" in query_params:
            token_key = query_params["auth_token"][0]

        if token_key:
            user = await self.get_user_from_token(token_key)
            if user:
                scope["user"] = user
                logger.info(f"WebSocket authenticated via token: user {user.id}")
                return scope

        # Try token from headers (if available)
        headers = dict(scope.get("headers", []))
        auth_header = headers.get(b"authorization")
        if auth_header:
            auth_value = auth_header.decode()
            if auth_value.startswith("Token "):
                token_key = auth_value[6:]  # Remove "Token " prefix
                user = await self.get_user_from_token(token_key)
                if user:
                    scope["user"] = user
                    logger.info(f"WebSocket authenticated via header token: user {user.id}")
                    return scope

        # No valid authentication found
        logger.warning("WebSocket connection without valid authentication")
        scope["user"] = AnonymousUser()
        return scope

    @database_sync_to_async
    def get_user_from_token(self, token_key: str) -> Optional[User]:
        """Get user from authentication token."""
        try:
            token = Token.objects.select_related("user").get(key=token_key)
            return token.user
        except Token.DoesNotExist:
            return None
        except Exception as e:
            logger.error(f"Error getting user from token: {e}")
            return None


class WebSocketPerformanceMiddleware(BaseMiddleware):
    """
    Middleware to monitor WebSocket connection performance and latency.
    """

    def __init__(self, inner):
        super().__init__(inner)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            # Wrap send to measure message latency
            original_send = send
            scope["websocket_start_time"] = time.time()
            
            async def wrapped_send(message):
                if message.get("type") == "websocket.send":
                    # Add timestamp to outgoing messages
                    if "text" in message:
                        try:
                            data = json.loads(message["text"])
                            data["server_timestamp"] = time.time()
                            message["text"] = json.dumps(data)
                        except (json.JSONDecodeError, KeyError):
                            pass  # Skip non-JSON messages
                
                return await original_send(message)
            
            return await super().__call__(scope, receive, wrapped_send)
        
        return await super().__call__(scope, receive, send)


# Custom authentication stack combining both middlewares
def WebSocketAuthMiddlewareStack(inner):
    """
    Authentication middleware stack for WebSockets that includes:
    - Standard Django authentication
    - Token authentication
    - Performance monitoring
    """
    return WebSocketPerformanceMiddleware(
        WebSocketAuthMiddleware(
            AuthMiddlewareStack(inner)
        )
    )