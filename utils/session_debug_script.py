"""
Session debugging script for WebSocket authentication issues.

This script can be run from Django shell to validate session handling,
authentication middleware, and ASGI configuration.
"""
import os
import sys
import django
from pathlib import Path

# Setup Django environment
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
django.setup()

from django.contrib.auth import get_user_model
from django.test import Client
from utils.websocket_debugger import (
    create_mock_authenticated_scope,
    create_mock_anonymous_scope,
    validate_session_data,
    generate_debug_report
)
from utils.asgi_validator import run_asgi_diagnostics

User = get_user_model()

def run_session_diagnostics():
    """Run comprehensive session diagnostics"""
    print("=" * 60)
    print("WebSocket Session Diagnostics")
    print("=" * 60)
    
    # 1. Check ASGI Configuration
    print("\n1. ASGI CONFIGURATION ANALYSIS")
    print("-" * 40)
    
    try:
        asgi_results = run_asgi_diagnostics()
        print(asgi_results['report'])
    except Exception as e:
        print(f"Error analyzing ASGI configuration: {e}")
    
    # 2. Test User Authentication
    print("\n2. USER AUTHENTICATION TEST")
    print("-" * 40)
    
    try:
        # Create test users if they don't exist
        staff_user, created = User.objects.get_or_create(
            username='debug_staff',
            defaults={
                'email': 'debug@example.com',
                'is_staff': True
            }
        )
        if created:
            staff_user.set_password('debugpass123')
            staff_user.save()
            print(f"Created debug staff user: {staff_user.username}")
        else:
            print(f"Using existing staff user: {staff_user.username}")
        
        regular_user, created = User.objects.get_or_create(
            username='debug_regular',
            defaults={
                'email': 'regular@example.com',
                'is_staff': False
            }
        )
        if created:
            regular_user.set_password('regularpass123')
            regular_user.save()
            print(f"Created debug regular user: {regular_user.username}")
        else:
            print(f"Using existing regular user: {regular_user.username}")
            
    except Exception as e:
        print(f"Error setting up test users: {e}")
        return
    
    # 3. Test WebSocket Scope Validation
    print("\n3. WEBSOCKET SCOPE VALIDATION")
    print("-" * 40)
    
    # Test authenticated staff user scope
    print("\nTesting authenticated staff user scope:")
    staff_scope = create_mock_authenticated_scope(staff_user, "/ws/logs/")
    staff_validation = validate_session_data(staff_scope)
    print(f"  Valid: {staff_validation['is_valid']}")
    if not staff_validation['is_valid']:
        print(f"  Errors: {staff_validation['errors']}")
    else:
        print(f"  User: {staff_validation['user_info']['username']} (staff: {staff_validation['user_info']['is_staff']})")
    
    # Test authenticated regular user scope
    print("\nTesting authenticated regular user scope:")
    regular_scope = create_mock_authenticated_scope(regular_user, "/ws/logs/")
    regular_validation = validate_session_data(regular_scope)
    print(f"  Valid: {regular_validation['is_valid']}")
    if not regular_validation['is_valid']:
        print(f"  Errors: {regular_validation['errors']}")
    else:
        print(f"  User: {regular_validation['user_info']['username']} (staff: {regular_validation['user_info']['is_staff']})")
    
    # Test anonymous user scope
    print("\nTesting anonymous user scope:")
    anon_scope = create_mock_anonymous_scope("/ws/logs/")
    anon_validation = validate_session_data(anon_scope)
    print(f"  Valid: {anon_validation['is_valid']}")
    print(f"  Errors: {anon_validation['errors']}")
    
    # 4. Test HTTP Session Creation
    print("\n4. HTTP SESSION CREATION TEST")
    print("-" * 40)
    
    try:
        client = Client()
        
        # Test login
        login_response = client.post('/accounts/login/', {
            'login': staff_user.username,
            'password': 'debugpass123'
        })
        
        print(f"Login response status: {login_response.status_code}")
        
        if hasattr(client, 'session'):
            session = client.session
            print(f"Session created: {bool(session)}")
            print(f"Session key: {session.session_key}")
            print(f"Session data keys: {list(session.keys())}")
            
            if '_auth_user_id' in session:
                print(f"Auth user ID in session: {session['_auth_user_id']}")
            else:
                print("No auth user ID found in session")
        else:
            print("No session object available")
            
    except Exception as e:
        print(f"Error testing HTTP session: {e}")
    
    # 5. Consumer Analysis
    print("\n5. CONSUMER ANALYSIS")
    print("-" * 40)
    
    try:
        from agent_chat_app.logviewer.consumers import LogStreamConsumer
        from agent_chat_app.chat.consumers import ChatConsumer
        from agent_chat_app.receipts.consumers import ReceiptProgressConsumer
        
        consumers = [
            ("LogStreamConsumer", LogStreamConsumer),
            ("ChatConsumer", ChatConsumer),
            ("ReceiptProgressConsumer", ReceiptProgressConsumer)
        ]
        
        for name, consumer_class in consumers:
            print(f"\n{name}:")
            print(f"  Has connect method: {hasattr(consumer_class, 'connect')}")
            print(f"  Has disconnect method: {hasattr(consumer_class, 'disconnect')}")
            
            if hasattr(consumer_class, 'connect'):
                import inspect
                try:
                    source = inspect.getsource(consumer_class.connect)
                    has_auth_check = "is_authenticated" in source or "AnonymousUser" in source
                    has_staff_check = "is_staff" in source
                    print(f"  Has authentication check: {has_auth_check}")
                    print(f"  Has staff check: {has_staff_check}")
                except Exception:
                    print(f"  Could not analyze source code")
    
    except Exception as e:
        print(f"Error analyzing consumers: {e}")
    
    # 6. Generate Full Debug Reports
    print("\n6. FULL DEBUG REPORTS")
    print("-" * 40)
    
    print("\nStaff User Debug Report:")
    print(generate_debug_report(staff_scope, "LogStreamConsumer"))
    
    print("\nAnonymous User Debug Report:")
    print(generate_debug_report(anon_scope, "LogStreamConsumer"))
    
    # 7. Recommendations
    print("\n7. RECOMMENDATIONS")
    print("-" * 40)
    
    recommendations = []
    
    if not staff_validation['is_valid']:
        recommendations.append("Fix session validation for authenticated users")
    
    if not asgi_results.get('middleware', {}).get('is_valid', True):
        recommendations.append("Review ASGI middleware configuration")
    
    if not asgi_results.get('routing', {}).get('is_valid', True):
        recommendations.append("Review WebSocket routing configuration")
    
    recommendations.extend([
        "Test WebSocket connections with real browser sessions",
        "Verify session cookie transmission in production environment",
        "Monitor authentication logs for pattern analysis",
        "Consider adding consumer-specific debugging middleware"
    ])
    
    for i, rec in enumerate(recommendations, 1):
        print(f"  {i}. {rec}")
    
    print("\n" + "=" * 60)
    print("Session diagnostics completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    run_session_diagnostics()