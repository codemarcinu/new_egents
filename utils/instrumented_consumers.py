"""
Instrumented WebSocket consumers with enhanced debugging capabilities.

These consumers extend the original consumers with additional logging,
scope inspection, and session validation for debugging authentication issues.
"""
import json
import logging
from typing import Dict, Any
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

from agent_chat_app.logviewer.consumers import LogStreamConsumer as OriginalLogStreamConsumer
from agent_chat_app.chat.consumers import ChatConsumer as OriginalChatConsumer
from agent_chat_app.receipts.consumers import ReceiptProgressConsumer as OriginalReceiptProgressConsumer
from utils.websocket_debugger import (
    log_websocket_scope,
    validate_session_data,
    generate_debug_report
)

logger = logging.getLogger(__name__)


class InstrumentedLogStreamConsumer(OriginalLogStreamConsumer):
    """
    LogStreamConsumer with enhanced debugging instrumentation.
    
    Adds detailed logging and validation at each step of the connection process.
    """
    
    async def connect(self):
        consumer_name = self.__class__.__name__
        
        # Log scope information
        log_websocket_scope(self.scope, consumer_name)
        
        # Validate session data
        validation_result = validate_session_data(self.scope)
        logger.info(f"Session validation result for {consumer_name}: {validation_result}")
        
        if not validation_result["is_valid"]:
            logger.error(f"Session validation failed: {validation_result['errors']}")
            
            # Generate and log full debug report
            debug_report = generate_debug_report(self.scope, consumer_name)
            logger.error(f"Full debug report:\n{debug_report}")
        
        # Log connection attempt with user details
        user = self.scope.get("user")
        logger.info(f"[INSTRUMENTED] WebSocket connection attempt from user: {user}")
        logger.info(f"[INSTRUMENTED] User type: {type(user)}")
        logger.info(f"[INSTRUMENTED] User authenticated: {getattr(user, 'is_authenticated', False)}")
        logger.info(f"[INSTRUMENTED] User is staff: {getattr(user, 'is_staff', False)}")
        
        # Check authentication with detailed logging
        if not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
            logger.warning(f"[INSTRUMENTED] Authentication failed - User: {user}")
            logger.warning(f"[INSTRUMENTED] Rejection reason: User not authenticated")
            logger.warning(f"[INSTRUMENTED] Closing connection with code 4401")
            await self.close(code=4401)
            return
        
        # Check staff status with detailed logging
        if not user.is_staff:
            logger.warning(f"[INSTRUMENTED] Authorization failed - User: {user.username}")
            logger.warning(f"[INSTRUMENTED] Rejection reason: User is not staff")
            logger.warning(f"[INSTRUMENTED] User permissions: staff={user.is_staff}, superuser={user.is_superuser}")
            logger.warning(f"[INSTRUMENTED] Closing connection with code 4403")
            await self.close(code=4403)
            return
        
        logger.info(f"[INSTRUMENTED] Authentication and authorization successful for {user.username}")
        
        # Call original connect method
        await super().connect()
        
        logger.info(f"[INSTRUMENTED] Connection established successfully for {user.username}")
    
    async def disconnect(self, close_code):
        logger.info(f"[INSTRUMENTED] Disconnection initiated with code: {close_code}")
        
        user = self.scope.get("user")
        if user and hasattr(user, "username"):
            logger.info(f"[INSTRUMENTED] User {user.username} disconnecting from log stream")
        
        await super().disconnect(close_code)
        
        logger.info(f"[INSTRUMENTED] Disconnection completed")
    
    async def receive(self, text_data):
        logger.debug(f"[INSTRUMENTED] Received message: {text_data}")
        
        await super().receive(text_data)


class InstrumentedChatConsumer(OriginalChatConsumer):
    """
    ChatConsumer with enhanced debugging instrumentation.
    """
    
    async def connect(self):
        consumer_name = self.__class__.__name__
        conversation_id = self.scope['url_route']['kwargs'].get('conversation_id')
        
        # Log scope and validation
        log_websocket_scope(self.scope, f"{consumer_name} (conversation: {conversation_id})")
        validation_result = validate_session_data(self.scope)
        
        logger.info(f"[INSTRUMENTED] Chat connection attempt for conversation {conversation_id}")
        logger.info(f"[INSTRUMENTED] Session validation: {validation_result['is_valid']}")
        
        if not validation_result["is_valid"]:
            logger.error(f"[INSTRUMENTED] Session validation failed: {validation_result['errors']}")
            debug_report = generate_debug_report(self.scope, consumer_name)
            logger.error(f"[INSTRUMENTED] Debug report:\n{debug_report}")
        
        user = self.scope.get("user")
        logger.info(f"[INSTRUMENTED] User: {user}, Conversation: {conversation_id}")
        
        # Check authentication
        if not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
            logger.warning(f"[INSTRUMENTED] Chat authentication failed for conversation {conversation_id}")
            await self.close(code=4401)
            return
        
        logger.info(f"[INSTRUMENTED] Chat authentication successful for {user.username}")
        
        # Call original connect method
        await super().connect()
        
        logger.info(f"[INSTRUMENTED] Chat connection established for {user.username} on conversation {conversation_id}")
    
    async def disconnect(self, close_code):
        conversation_id = self.scope['url_route']['kwargs'].get('conversation_id')
        user = self.scope.get("user")
        
        logger.info(f"[INSTRUMENTED] Chat disconnection: user={getattr(user, 'username', 'unknown')}, "
                   f"conversation={conversation_id}, code={close_code}")
        
        await super().disconnect(close_code)


class InstrumentedReceiptProgressConsumer(OriginalReceiptProgressConsumer):
    """
    ReceiptProgressConsumer with enhanced debugging instrumentation.
    """
    
    async def connect(self):
        consumer_name = self.__class__.__name__
        receipt_id = self.scope['url_route']['kwargs'].get('receipt_id')
        
        # Log scope and validation
        log_websocket_scope(self.scope, f"{consumer_name} (receipt: {receipt_id})")
        validation_result = validate_session_data(self.scope)
        
        logger.info(f"[INSTRUMENTED] Receipt progress connection attempt for receipt {receipt_id}")
        logger.info(f"[INSTRUMENTED] Session validation: {validation_result['is_valid']}")
        
        if not validation_result["is_valid"]:
            logger.error(f"[INSTRUMENTED] Session validation failed: {validation_result['errors']}")
            debug_report = generate_debug_report(self.scope, consumer_name)
            logger.error(f"[INSTRUMENTED] Debug report:\n{debug_report}")
        
        user = self.scope.get("user")
        logger.info(f"[INSTRUMENTED] User: {user}, Receipt: {receipt_id}")
        
        # Check authentication
        if not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
            logger.warning(f"[INSTRUMENTED] Receipt authentication failed for receipt {receipt_id}")
            await self.close(code=4401)
            return
        
        logger.info(f"[INSTRUMENTED] Receipt authentication successful for {user.username}")
        
        # Call original connect method
        await super().connect()
        
        logger.info(f"[INSTRUMENTED] Receipt connection established for {user.username} on receipt {receipt_id}")
    
    async def disconnect(self, close_code):
        receipt_id = self.scope['url_route']['kwargs'].get('receipt_id')
        user = self.scope.get("user")
        
        logger.info(f"[INSTRUMENTED] Receipt disconnection: user={getattr(user, 'username', 'unknown')}, "
                   f"receipt={receipt_id}, code={close_code}")
        
        await super().disconnect(close_code)


class WebSocketMiddlewareTracer:
    """
    Middleware to trace WebSocket connections through the ASGI stack.
    
    This class can be used to wrap WebSocket applications and log
    detailed information about request processing.
    """
    
    def __init__(self, inner):
        self.inner = inner
    
    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            logger.info(f"[MIDDLEWARE_TRACER] WebSocket request received")
            logger.info(f"[MIDDLEWARE_TRACER] Path: {scope.get('path', 'unknown')}")
            logger.info(f"[MIDDLEWARE_TRACER] Headers: {dict(scope.get('headers', []))}")
            logger.info(f"[MIDDLEWARE_TRACER] User in scope: {'user' in scope}")
            logger.info(f"[MIDDLEWARE_TRACER] Session in scope: {'session' in scope}")
            
            if 'user' in scope:
                user = scope['user']
                logger.info(f"[MIDDLEWARE_TRACER] User: {user} (type: {type(user)})")
                logger.info(f"[MIDDLEWARE_TRACER] Authenticated: {getattr(user, 'is_authenticated', False)}")
            
            if 'session' in scope:
                session = scope['session']
                logger.info(f"[MIDDLEWARE_TRACER] Session keys: {list(session.keys())}")
            
            # Wrap send function to trace outgoing messages
            async def traced_send(message):
                if message["type"] == "websocket.close":
                    logger.info(f"[MIDDLEWARE_TRACER] WebSocket closing with code: {message.get('code', 'unknown')}")
                elif message["type"] == "websocket.accept":
                    logger.info(f"[MIDDLEWARE_TRACER] WebSocket connection accepted")
                elif message["type"] == "websocket.send":
                    logger.debug(f"[MIDDLEWARE_TRACER] WebSocket message sent: {message.get('text', message.get('bytes', 'binary'))}")
                
                await send(message)
            
            await self.inner(scope, receive, traced_send)
        else:
            await self.inner(scope, receive, send)


def create_instrumented_routing():
    """
    Create instrumented WebSocket routing with enhanced debugging.
    
    Returns routing patterns using instrumented consumers.
    """
    from django.urls import re_path
    
    websocket_urlpatterns = [
        # Instrumented consumers for debugging
        re_path(r'ws/logs/debug/$', InstrumentedLogStreamConsumer.as_asgi()),
        re_path(r"ws/chat/debug/(?P<conversation_id>\d+)/$", InstrumentedChatConsumer.as_asgi()),
        re_path(r'ws/receipt/debug/(?P<receipt_id>\d+)/$', InstrumentedReceiptProgressConsumer.as_asgi()),
    ]
    
    return websocket_urlpatterns


class SessionDataCollector:
    """
    Utility class to collect session data from WebSocket connections for analysis.
    """
    
    def __init__(self):
        self.connection_data = []
    
    def collect_connection_data(self, scope: Dict[str, Any], consumer_name: str = "Unknown"):
        """Collect data from a WebSocket connection attempt"""
        user = scope.get("user")
        session = scope.get("session", {})
        
        connection_info = {
            "timestamp": logger.handlers[0].formatter.formatTime(
                logging.LogRecord("", 0, "", 0, "", (), None)
            ) if logger.handlers else "unknown",
            "consumer": consumer_name,
            "path": scope.get("path", "unknown"),
            "user_type": str(type(user)),
            "user_authenticated": getattr(user, "is_authenticated", False),
            "user_staff": getattr(user, "is_staff", False),
            "session_keys": list(session.keys()),
            "has_auth_user_id": "_auth_user_id" in session,
            "has_sessionid_cookie": "sessionid" in scope.get("cookies", {}),
            "headers_count": len(scope.get("headers", [])),
        }
        
        if hasattr(user, "username"):
            connection_info["username"] = user.username
        
        self.connection_data.append(connection_info)
    
    def get_analytics(self):
        """Get analytics from collected connection data"""
        if not self.connection_data:
            return {"message": "No connection data collected"}
        
        total_connections = len(self.connection_data)
        authenticated_connections = sum(1 for c in self.connection_data if c["user_authenticated"])
        staff_connections = sum(1 for c in self.connection_data if c["user_staff"])
        anonymous_connections = sum(1 for c in self.connection_data if "AnonymousUser" in c["user_type"])
        
        return {
            "total_connections": total_connections,
            "authenticated_connections": authenticated_connections,
            "staff_connections": staff_connections,
            "anonymous_connections": anonymous_connections,
            "authentication_rate": authenticated_connections / total_connections if total_connections > 0 else 0,
            "consumers_used": list(set(c["consumer"] for c in self.connection_data)),
            "paths_accessed": list(set(c["path"] for c in self.connection_data))
        }


# Global session data collector for debugging
session_collector = SessionDataCollector()