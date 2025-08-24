"""
ASGI Configuration Validator

Utilities for validating ASGI configuration, middleware stack,
and WebSocket routing for authentication issues.
"""
import importlib
import logging
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


def verify_auth_middleware_stack() -> Dict[str, Any]:
    """
    Verify that AuthMiddlewareStack is properly configured in ASGI.
    
    Returns:
        Dictionary with validation results
    """
    result = {
        "is_valid": True,
        "errors": [],
        "warnings": [],
        "configuration": {},
        "recommendations": []
    }
    
    try:
        # Import the ASGI application
        from config.asgi import application
        
        # Check if application is ProtocolTypeRouter
        if hasattr(application, 'application_mapping'):
            result["configuration"]["router_type"] = "ProtocolTypeRouter"
            
            # Check websocket configuration
            websocket_app = application.application_mapping.get('websocket')
            if websocket_app:
                result["configuration"]["websocket_configured"] = True
                
                # Check if AuthMiddlewareStack is present
                app_class_name = websocket_app.__class__.__name__
                result["configuration"]["websocket_app_type"] = app_class_name
                
                if "AllowedHostsOriginValidator" in app_class_name:
                    result["configuration"]["origin_validator"] = True
                    
                    # Check inner middleware
                    if hasattr(websocket_app, 'application'):
                        inner_app = websocket_app.application
                        inner_class_name = inner_app.__class__.__name__
                        result["configuration"]["inner_app_type"] = inner_class_name
                        
                        if "AuthMiddlewareStack" in inner_class_name:
                            result["configuration"]["auth_middleware"] = True
                        else:
                            result["is_valid"] = False
                            result["errors"].append(
                                f"Expected AuthMiddlewareStack, found {inner_class_name}"
                            )
                            result["recommendations"].append(
                                "Wrap URLRouter with AuthMiddlewareStack in ASGI configuration"
                            )
                else:
                    result["warnings"].append("AllowedHostsOriginValidator not detected")
                    result["recommendations"].append(
                        "Consider wrapping with AllowedHostsOriginValidator for security"
                    )
            else:
                result["is_valid"] = False
                result["errors"].append("No websocket configuration found")
                result["recommendations"].append(
                    "Add 'websocket' key to ProtocolTypeRouter mapping"
                )
        else:
            result["is_valid"] = False
            result["errors"].append("Application is not a ProtocolTypeRouter")
            result["recommendations"].append(
                "Use ProtocolTypeRouter to separate HTTP and WebSocket handling"
            )
            
    except ImportError as e:
        result["is_valid"] = False
        result["errors"].append(f"Cannot import ASGI application: {e}")
        result["recommendations"].append("Check ASGI configuration file path")
    except Exception as e:
        result["is_valid"] = False
        result["errors"].append(f"Error analyzing ASGI configuration: {e}")
    
    return result


def validate_routing_configuration() -> Dict[str, Any]:
    """
    Validate WebSocket routing configuration.
    
    Returns:
        Dictionary with routing validation results
    """
    result = {
        "is_valid": True,
        "errors": [],
        "warnings": [],
        "routes": [],
        "consumers": {},
        "recommendations": []
    }
    
    try:
        # Import routing configuration
        from agent_chat_app.chat.routing import websocket_urlpatterns
        
        result["routes"] = []
        for pattern in websocket_urlpatterns:
            route_info = {
                "pattern": str(pattern.pattern.pattern),
                "consumer": pattern.callback.__class__.__name__ if hasattr(pattern.callback, '__class__') else "Unknown"
            }
            result["routes"].append(route_info)
        
        # Check specific consumers
        consumer_modules = [
            ("LogStreamConsumer", "agent_chat_app.logviewer.consumers"),
            ("ChatConsumer", "agent_chat_app.chat.consumers"),
            ("ReceiptProgressConsumer", "agent_chat_app.receipts.consumers"),
        ]
        
        for consumer_name, module_path in consumer_modules:
            try:
                module = importlib.import_module(module_path)
                consumer_class = getattr(module, consumer_name, None)
                
                if consumer_class:
                    result["consumers"][consumer_name] = {
                        "found": True,
                        "module": module_path,
                        "has_connect": hasattr(consumer_class, 'connect'),
                        "has_disconnect": hasattr(consumer_class, 'disconnect'),
                        "authentication_check": _check_authentication_in_consumer(consumer_class)
                    }
                else:
                    result["consumers"][consumer_name] = {
                        "found": False,
                        "module": module_path
                    }
                    result["warnings"].append(f"Consumer {consumer_name} not found in {module_path}")
                    
            except ImportError:
                result["consumers"][consumer_name] = {
                    "found": False,
                    "module": module_path,
                    "import_error": True
                }
                result["errors"].append(f"Cannot import {module_path}")
        
        if len(result["routes"]) == 0:
            result["warnings"].append("No WebSocket routes found")
            result["recommendations"].append("Add WebSocket URL patterns to routing configuration")
        
    except ImportError as e:
        result["is_valid"] = False
        result["errors"].append(f"Cannot import routing configuration: {e}")
        result["recommendations"].append("Check WebSocket routing configuration")
    except Exception as e:
        result["is_valid"] = False
        result["errors"].append(f"Error analyzing routing: {e}")
    
    return result


def _check_authentication_in_consumer(consumer_class) -> Dict[str, Any]:
    """
    Check if consumer implements authentication checks.
    
    Args:
        consumer_class: The consumer class to analyze
        
    Returns:
        Dictionary with authentication check results
    """
    auth_info = {
        "has_auth_check": False,
        "checks_user": False,
        "checks_staff": False,
        "close_codes": []
    }
    
    try:
        if hasattr(consumer_class, 'connect'):
            import inspect
            source = inspect.getsource(consumer_class.connect)
            
            # Look for common authentication patterns
            if "user" in source and ("is_authenticated" in source or "AnonymousUser" in source):
                auth_info["checks_user"] = True
                auth_info["has_auth_check"] = True
            
            if "is_staff" in source:
                auth_info["checks_staff"] = True
            
            # Look for close codes
            import re
            close_code_pattern = r'close\(code=(\d+)\)'
            matches = re.findall(close_code_pattern, source)
            auth_info["close_codes"] = [int(code) for code in matches]
            
    except Exception as e:
        logger.warning(f"Could not analyze consumer authentication: {e}")
    
    return auth_info


def check_cookie_transmission() -> Dict[str, Any]:
    """
    Check cookie transmission configuration.
    
    Returns:
        Dictionary with cookie configuration results
    """
    result = {
        "is_valid": True,
        "errors": [],
        "warnings": [],
        "settings": {},
        "recommendations": []
    }
    
    try:
        from django.conf import settings
        
        # Check session settings
        session_settings = {
            "SESSION_COOKIE_AGE": getattr(settings, 'SESSION_COOKIE_AGE', None),
            "SESSION_COOKIE_SECURE": getattr(settings, 'SESSION_COOKIE_SECURE', None),
            "SESSION_COOKIE_HTTPONLY": getattr(settings, 'SESSION_COOKIE_HTTPONLY', None),
            "SESSION_COOKIE_SAMESITE": getattr(settings, 'SESSION_COOKIE_SAMESITE', None),
            "SESSION_SAVE_EVERY_REQUEST": getattr(settings, 'SESSION_SAVE_EVERY_REQUEST', None),
        }
        
        result["settings"]["session"] = session_settings
        
        # Check CSRF settings
        csrf_settings = {
            "CSRF_COOKIE_SECURE": getattr(settings, 'CSRF_COOKIE_SECURE', None),
            "CSRF_COOKIE_HTTPONLY": getattr(settings, 'CSRF_COOKIE_HTTPONLY', None),
            "CSRF_COOKIE_SAMESITE": getattr(settings, 'CSRF_COOKIE_SAMESITE', None),
        }
        
        result["settings"]["csrf"] = csrf_settings
        
        # Check channel layers
        channel_layers = getattr(settings, 'CHANNEL_LAYERS', None)
        if channel_layers:
            result["settings"]["channel_layers"] = True
            default_layer = channel_layers.get('default', {})
            result["settings"]["channel_backend"] = default_layer.get('BACKEND', 'Not set')
        else:
            result["warnings"].append("CHANNEL_LAYERS not configured")
            result["recommendations"].append("Configure CHANNEL_LAYERS for WebSocket support")
        
        # Validate settings
        if session_settings.get('SESSION_COOKIE_SECURE') and settings.DEBUG:
            result["warnings"].append("SESSION_COOKIE_SECURE=True may cause issues in DEBUG mode")
            result["recommendations"].append("Consider setting SESSION_COOKIE_SECURE=False for development")
        
        if not session_settings.get('SESSION_SAVE_EVERY_REQUEST'):
            result["warnings"].append("SESSION_SAVE_EVERY_REQUEST is not enabled")
            result["recommendations"].append("Consider enabling SESSION_SAVE_EVERY_REQUEST for WebSocket sessions")
        
    except Exception as e:
        result["is_valid"] = False
        result["errors"].append(f"Error checking cookie configuration: {e}")
    
    return result


def generate_asgi_validation_report() -> str:
    """
    Generate a comprehensive ASGI validation report.
    
    Returns:
        Formatted validation report as string
    """
    middleware_validation = verify_auth_middleware_stack()
    routing_validation = validate_routing_configuration()
    cookie_validation = check_cookie_transmission()
    
    report_lines = [
        "ASGI Configuration Validation Report",
        "=" * 50,
        "",
        "MIDDLEWARE STACK:",
        f"  Valid: {'✓' if middleware_validation['is_valid'] else '✗'}",
    ]
    
    if middleware_validation["configuration"]:
        for key, value in middleware_validation["configuration"].items():
            report_lines.append(f"  {key.replace('_', ' ').title()}: {value}")
    
    report_lines.extend([
        "",
        "ROUTING CONFIGURATION:",
        f"  Valid: {'✓' if routing_validation['is_valid'] else '✗'}",
        f"  Routes found: {len(routing_validation['routes'])}",
    ])
    
    for route in routing_validation["routes"]:
        report_lines.append(f"    • {route['pattern']} → {route['consumer']}")
    
    report_lines.extend([
        "",
        "CONSUMER ANALYSIS:",
    ])
    
    for consumer, info in routing_validation["consumers"].items():
        status = "✓" if info.get("found", False) else "✗"
        report_lines.append(f"  {consumer}: {status}")
        
        if info.get("found"):
            auth_check = info.get("authentication_check", {})
            if auth_check.get("has_auth_check"):
                report_lines.append(f"    Authentication: ✓")
                if auth_check.get("close_codes"):
                    report_lines.append(f"    Close codes: {auth_check['close_codes']}")
            else:
                report_lines.append(f"    Authentication: ⚠ No checks found")
    
    report_lines.extend([
        "",
        "COOKIE CONFIGURATION:",
        f"  Valid: {'✓' if cookie_validation['is_valid'] else '✗'}",
    ])
    
    # Add all errors and warnings
    all_errors = (
        middleware_validation.get("errors", []) +
        routing_validation.get("errors", []) +
        cookie_validation.get("errors", [])
    )
    
    all_warnings = (
        middleware_validation.get("warnings", []) +
        routing_validation.get("warnings", []) +
        cookie_validation.get("warnings", [])
    )
    
    all_recommendations = (
        middleware_validation.get("recommendations", []) +
        routing_validation.get("recommendations", []) +
        cookie_validation.get("recommendations", [])
    )
    
    if all_errors:
        report_lines.extend([
            "",
            "ERRORS:",
        ])
        for error in all_errors:
            report_lines.append(f"  • {error}")
    
    if all_warnings:
        report_lines.extend([
            "",
            "WARNINGS:",
        ])
        for warning in all_warnings:
            report_lines.append(f"  • {warning}")
    
    if all_recommendations:
        report_lines.extend([
            "",
            "RECOMMENDATIONS:",
        ])
        for recommendation in all_recommendations:
            report_lines.append(f"  • {recommendation}")
    
    return "\n".join(report_lines)


def run_asgi_diagnostics() -> Dict[str, Any]:
    """
    Run comprehensive ASGI diagnostics and return results.
    
    Returns:
        Complete diagnostic results dictionary
    """
    return {
        "middleware": verify_auth_middleware_stack(),
        "routing": validate_routing_configuration(),
        "cookies": check_cookie_transmission(),
        "report": generate_asgi_validation_report()
    }