"""
WebSocket debugging utilities for session validation and troubleshooting.

This module provides utilities for debugging WebSocket authentication issues,
logging scope data, and validating session information.
"""
import json
import logging
from typing import Dict, Any, Optional
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model

User = get_user_model()
logger = logging.getLogger(__name__)


def log_websocket_scope(scope: Dict[str, Any], consumer_name: str = "Unknown") -> None:
    """
    Log detailed WebSocket scope information for debugging.
    
    Args:
        scope: The ASGI scope dictionary
        consumer_name: Name of the consumer for context
    """
    logger.info(f"=== WebSocket Scope Debug - {consumer_name} ===")
    
    # Log basic scope info
    logger.info(f"Type: {scope.get('type', 'unknown')}")
    logger.info(f"Path: {scope.get('path', 'unknown')}")
    logger.info(f"Method: {scope.get('method', 'N/A')}")
    
    # Log user information
    user = scope.get('user')
    if user:
        logger.info(f"User: {user}")
        logger.info(f"User type: {type(user)}")
        logger.info(f"Is authenticated: {getattr(user, 'is_authenticated', False)}")
        logger.info(f"Is staff: {getattr(user, 'is_staff', False)}")
        logger.info(f"Is superuser: {getattr(user, 'is_superuser', False)}")
        if hasattr(user, 'username'):
            logger.info(f"Username: {user.username}")
    else:
        logger.warning("No user found in scope")
    
    # Log session information
    session = scope.get('session', {})
    logger.info(f"Session keys: {list(session.keys())}")
    
    # Log authentication backend info
    auth_user_id = session.get('_auth_user_id')
    auth_backend = session.get('_auth_user_backend')
    logger.info(f"Auth user ID from session: {auth_user_id}")
    logger.info(f"Auth backend: {auth_backend}")
    
    # Log headers
    headers = dict(scope.get('headers', []))
    logger.info(f"Headers: {headers}")
    
    # Log cookies
    cookies = scope.get('cookies', {})
    logger.info(f"Cookies: {list(cookies.keys())}")
    
    logger.info("=== End WebSocket Scope Debug ===")


def validate_session_data(scope: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate session data and return validation results.
    
    Args:
        scope: The ASGI scope dictionary
        
    Returns:
        Dictionary with validation results and recommendations
    """
    validation_result = {
        "is_valid": True,
        "errors": [],
        "warnings": [],
        "user_info": {},
        "session_info": {},
        "recommendations": []
    }
    
    # Check user
    user = scope.get('user')
    if not user:
        validation_result["is_valid"] = False
        validation_result["errors"].append("No user found in scope")
    elif isinstance(user, AnonymousUser):
        validation_result["is_valid"] = False
        validation_result["errors"].append("User is anonymous")
    else:
        validation_result["user_info"] = {
            "username": getattr(user, 'username', 'unknown'),
            "is_authenticated": getattr(user, 'is_authenticated', False),
            "is_staff": getattr(user, 'is_staff', False),
            "is_superuser": getattr(user, 'is_superuser', False),
        }
        
        if not user.is_authenticated:
            validation_result["is_valid"] = False
            validation_result["errors"].append("User is not authenticated")
    
    # Check session
    session = scope.get('session', {})
    validation_result["session_info"] = {
        "has_session": bool(session),
        "session_keys": list(session.keys()),
        "auth_user_id": session.get('_auth_user_id'),
        "auth_backend": session.get('_auth_user_backend')
    }
    
    if not session:
        validation_result["warnings"].append("No session data found")
        validation_result["recommendations"].append(
            "Ensure AuthMiddlewareStack is properly configured"
        )
    
    # Check session consistency
    if user and not isinstance(user, AnonymousUser):
        session_user_id = session.get('_auth_user_id')
        if session_user_id and str(user.id) != str(session_user_id):
            validation_result["warnings"].append(
                f"Session user ID ({session_user_id}) doesn't match scope user ID ({user.id})"
            )
    
    # Check cookies
    cookies = scope.get('cookies', {})
    if 'sessionid' not in cookies:
        validation_result["warnings"].append("No sessionid cookie found")
        validation_result["recommendations"].append(
            "Check if session cookies are being transmitted properly"
        )
    
    return validation_result


def check_middleware_stack(scope: Dict[str, Any]) -> Dict[str, Any]:
    """
    Check if the middleware stack is properly configured.
    
    Args:
        scope: The ASGI scope dictionary
        
    Returns:
        Dictionary with middleware validation results
    """
    middleware_result = {
        "auth_middleware_present": False,
        "session_middleware_present": False,
        "errors": [],
        "recommendations": []
    }
    
    # Check if user is in scope (indicates AuthMiddleware is working)
    if 'user' in scope:
        middleware_result["auth_middleware_present"] = True
    else:
        middleware_result["errors"].append("AuthMiddleware not detected - no user in scope")
        middleware_result["recommendations"].append(
            "Ensure AuthMiddlewareStack is configured in ASGI application"
        )
    
    # Check if session is in scope (indicates SessionMiddleware is working)
    if 'session' in scope:
        middleware_result["session_middleware_present"] = True
    else:
        middleware_result["errors"].append("SessionMiddleware not detected - no session in scope")
        middleware_result["recommendations"].append(
            "Ensure SessionMiddlewareStack is configured in ASGI application"
        )
    
    return middleware_result


def generate_debug_report(scope: Dict[str, Any], consumer_name: str = "Unknown") -> str:
    """
    Generate a comprehensive debug report for WebSocket connection issues.
    
    Args:
        scope: The ASGI scope dictionary
        consumer_name: Name of the consumer for context
        
    Returns:
        Formatted debug report as string
    """
    session_validation = validate_session_data(scope)
    middleware_validation = check_middleware_stack(scope)
    
    report_lines = [
        f"WebSocket Debug Report - {consumer_name}",
        "=" * 50,
        "",
        "USER INFORMATION:",
        f"  User: {scope.get('user', 'Not found')}",
        f"  Type: {type(scope.get('user', 'N/A'))}",
    ]
    
    if session_validation["user_info"]:
        for key, value in session_validation["user_info"].items():
            report_lines.append(f"  {key.replace('_', ' ').title()}: {value}")
    
    report_lines.extend([
        "",
        "SESSION INFORMATION:",
        f"  Has session: {session_validation['session_info']['has_session']}",
        f"  Session keys: {session_validation['session_info']['session_keys']}",
        f"  Auth user ID: {session_validation['session_info']['auth_user_id']}",
        f"  Auth backend: {session_validation['session_info']['auth_backend']}",
        "",
        "MIDDLEWARE STATUS:",
        f"  Auth middleware: {'✓' if middleware_validation['auth_middleware_present'] else '✗'}",
        f"  Session middleware: {'✓' if middleware_validation['session_middleware_present'] else '✗'}",
        "",
        "VALIDATION RESULT:",
        f"  Is valid: {'✓' if session_validation['is_valid'] else '✗'}",
    ])
    
    if session_validation["errors"]:
        report_lines.extend([
            "",
            "ERRORS:",
        ])
        for error in session_validation["errors"]:
            report_lines.append(f"  • {error}")
    
    if session_validation["warnings"]:
        report_lines.extend([
            "",
            "WARNINGS:",
        ])
        for warning in session_validation["warnings"]:
            report_lines.append(f"  • {warning}")
    
    if session_validation["recommendations"]:
        report_lines.extend([
            "",
            "RECOMMENDATIONS:",
        ])
        for recommendation in session_validation["recommendations"]:
            report_lines.append(f"  • {recommendation}")
    
    return "\n".join(report_lines)


class WebSocketDebugMixin:
    """
    Mixin class to add debugging capabilities to WebSocket consumers.
    
    Usage:
        class MyConsumer(WebSocketDebugMixin, AsyncWebsocketConsumer):
            async def connect(self):
                # Debug info will be automatically logged
                await super().connect()
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._debug_enabled = True  # Set to False to disable debugging
    
    async def connect(self):
        if self._debug_enabled:
            consumer_name = self.__class__.__name__
            log_websocket_scope(self.scope, consumer_name)
            
            validation_result = validate_session_data(self.scope)
            if not validation_result["is_valid"]:
                logger.error(f"WebSocket validation failed for {consumer_name}: {validation_result['errors']}")
                
                # Log full debug report
                debug_report = generate_debug_report(self.scope, consumer_name)
                logger.error(f"Debug Report:\n{debug_report}")
        
        await super().connect()


def create_mock_authenticated_scope(user, path: str = "/ws/test/") -> Dict[str, Any]:
    """
    Create a mock authenticated WebSocket scope for testing.
    
    Args:
        user: Django user instance
        path: WebSocket path
        
    Returns:
        Mock scope dictionary
    """
    return {
        "type": "websocket",
        "path": path,
        "user": user,
        "session": {
            "_auth_user_id": str(user.id),
            "_auth_user_backend": "django.contrib.auth.backends.ModelBackend",
            "sessionid": f"mock_session_{user.id}"
        },
        "cookies": {
            "sessionid": f"mock_session_{user.id}"
        },
        "headers": [
            (b"origin", b"http://localhost:8000"),
            (b"user-agent", b"test-client"),
            (b"cookie", f"sessionid=mock_session_{user.id}".encode())
        ]
    }


def create_mock_anonymous_scope(path: str = "/ws/test/") -> Dict[str, Any]:
    """
    Create a mock anonymous WebSocket scope for testing.
    
    Args:
        path: WebSocket path
        
    Returns:
        Mock scope dictionary
    """
    return {
        "type": "websocket",
        "path": path,
        "user": AnonymousUser(),
        "session": {},
        "cookies": {},
        "headers": [
            (b"origin", b"http://localhost:8000"),
            (b"user-agent", b"test-client")
        ]
    }