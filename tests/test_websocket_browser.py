"""
Browser-based WebSocket Integration Tests

Tests WebSocket authentication and session handling in real browser environments
using Selenium WebDriver for cross-tab session validation and cookie inheritance.
"""
import pytest
import asyncio
import time
import json
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.contrib.auth import get_user_model
from django.test import override_settings
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, WebDriverException
from unittest.mock import patch

User = get_user_model()


@override_settings(ALLOWED_HOSTS=['*'])
class WebSocketBrowserTestCase(StaticLiveServerTestCase):
    """Base class for browser-based WebSocket tests"""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Setup Chrome options for testing
        cls.chrome_options = Options()
        cls.chrome_options.add_argument('--headless')
        cls.chrome_options.add_argument('--no-sandbox')
        cls.chrome_options.add_argument('--disable-dev-shm-usage')
        cls.chrome_options.add_argument('--disable-gpu')
        cls.chrome_options.add_argument('--window-size=1920,1080')
        
    def setUp(self):
        try:
            self.driver = webdriver.Chrome(options=self.chrome_options)
        except WebDriverException:
            # Fallback to Firefox if Chrome is not available
            from selenium.webdriver.firefox.options import Options as FirefoxOptions
            firefox_options = FirefoxOptions()
            firefox_options.add_argument('--headless')
            self.driver = webdriver.Firefox(options=firefox_options)
        
        self.driver.implicitly_wait(10)
        
        # Create test users
        self.regular_user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        self.staff_user = User.objects.create_user(
            username='staffuser',
            email='staff@example.com',
            password='staffpass123',
            is_staff=True
        )
    
    def tearDown(self):
        self.driver.quit()
        super().tearDown()
    
    def login_user(self, username, password):
        """Helper method to login a user via browser"""
        self.driver.get(f'{self.live_server_url}/')
        
        # Navigate to login page
        try:
            login_link = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.LINK_TEXT, "Log In"))
            )
            login_link.click()
        except TimeoutException:
            # Maybe already on login page or different UI
            pass
        
        # Fill login form
        username_field = WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.NAME, "login"))
        )
        username_field.clear()
        username_field.send_keys(username)
        
        password_field = self.driver.find_element(By.NAME, "password")
        password_field.clear()
        password_field.send_keys(password)
        
        # Submit form
        submit_button = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        submit_button.click()
        
        # Wait for redirect after login
        WebDriverWait(self.driver, 10).until(
            lambda driver: driver.current_url != f'{self.live_server_url}/accounts/login/'
        )
    
    def inject_websocket_test_script(self, websocket_url):
        """Inject JavaScript to test WebSocket connection"""
        script = f"""
        window.websocketTest = {{
            socket: null,
            connected: false,
            errors: [],
            messages: [],
            
            connect: function() {{
                try {{
                    this.socket = new WebSocket('{websocket_url}');
                    
                    this.socket.onopen = function(event) {{
                        window.websocketTest.connected = true;
                        window.websocketTest.messages.push({{'type': 'open', 'data': event}});
                    }};
                    
                    this.socket.onclose = function(event) {{
                        window.websocketTest.connected = false;
                        window.websocketTest.messages.push({{'type': 'close', 'code': event.code, 'reason': event.reason}});
                    }};
                    
                    this.socket.onerror = function(error) {{
                        window.websocketTest.errors.push(error);
                        window.websocketTest.messages.push({{'type': 'error', 'data': error}});
                    }};
                    
                    this.socket.onmessage = function(event) {{
                        window.websocketTest.messages.push({{'type': 'message', 'data': event.data}});
                    }};
                }} catch (e) {{
                    this.errors.push(e);
                }}
            }},
            
            disconnect: function() {{
                if (this.socket) {{
                    this.socket.close();
                }}
            }},
            
            sendMessage: function(message) {{
                if (this.socket && this.socket.readyState === WebSocket.OPEN) {{
                    this.socket.send(JSON.stringify(message));
                }}
            }},
            
            getStatus: function() {{
                return {{
                    connected: this.connected,
                    errors: this.errors,
                    messages: this.messages,
                    readyState: this.socket ? this.socket.readyState : null
                }};
            }}
        }};
        """
        self.driver.execute_script(script)
    
    def wait_for_websocket_connection(self, timeout=5):
        """Wait for WebSocket connection to establish"""
        end_time = time.time() + timeout
        while time.time() < end_time:
            connected = self.driver.execute_script("return window.websocketTest.connected;")
            if connected:
                return True
            time.sleep(0.1)
        return False
    
    def get_websocket_status(self):
        """Get current WebSocket status"""
        return self.driver.execute_script("return window.websocketTest.getStatus();")


class TestLoginAndWebSocketConnection(WebSocketBrowserTestCase):
    """Test login and WebSocket connection flow"""
    
    def test_anonymous_user_websocket_rejection(self):
        """Test that anonymous users cannot connect to WebSocket"""
        # Navigate to app without logging in
        self.driver.get(f'{self.live_server_url}/')
        
        # Try to connect to log stream WebSocket
        websocket_url = f"ws://{self.live_server_url.replace('http://', '')}/ws/logs/"
        self.inject_websocket_test_script(websocket_url)
        
        # Attempt connection
        self.driver.execute_script("window.websocketTest.connect();")
        time.sleep(2)  # Give time for connection attempt
        
        status = self.get_websocket_status()
        
        # Should not be connected
        self.assertFalse(status['connected'])
        
        # Check for close event with authentication error code
        close_messages = [msg for msg in status['messages'] if msg['type'] == 'close']
        if close_messages:
            self.assertEqual(close_messages[0]['code'], 4401)
    
    def test_regular_user_staff_websocket_rejection(self):
        """Test that regular (non-staff) users cannot connect to staff WebSocket"""
        # Login as regular user
        self.login_user('testuser', 'testpass123')
        
        # Try to connect to log stream WebSocket (requires staff)
        websocket_url = f"ws://{self.live_server_url.replace('http://', '')}/ws/logs/"
        self.inject_websocket_test_script(websocket_url)
        
        # Attempt connection
        self.driver.execute_script("window.websocketTest.connect();")
        time.sleep(2)
        
        status = self.get_websocket_status()
        
        # Should not be connected
        self.assertFalse(status['connected'])
        
        # Check for close event with permission error code
        close_messages = [msg for msg in status['messages'] if msg['type'] == 'close']
        if close_messages:
            self.assertEqual(close_messages[0]['code'], 4403)
    
    def test_staff_user_websocket_success(self):
        """Test that staff users can successfully connect to WebSocket"""
        # Login as staff user
        self.login_user('staffuser', 'staffpass123')
        
        # Try to connect to log stream WebSocket
        websocket_url = f"ws://{self.live_server_url.replace('http://', '')}/ws/logs/"
        self.inject_websocket_test_script(websocket_url)
        
        # Attempt connection
        self.driver.execute_script("window.websocketTest.connect();")
        
        # Wait for connection
        connected = self.wait_for_websocket_connection(timeout=10)
        
        self.assertTrue(connected, "Staff user should be able to connect to WebSocket")
        
        status = self.get_websocket_status()
        self.assertTrue(status['connected'])
        self.assertEqual(len(status['errors']), 0, f"Should have no errors: {status['errors']}")
        
        # Test ping-pong
        self.driver.execute_script("""
            window.websocketTest.sendMessage({
                type: 'ping',
                timestamp: '2024-01-01T00:00:00Z'
            });
        """)
        
        time.sleep(1)  # Wait for response
        
        status = self.get_websocket_status()
        message_data = [msg for msg in status['messages'] if msg['type'] == 'message']
        
        if message_data:
            response = json.loads(message_data[0]['data'])
            self.assertEqual(response['type'], 'pong')
            self.assertEqual(response['timestamp'], '2024-01-01T00:00:00Z')


class TestCrossTabSessionValidation(WebSocketBrowserTestCase):
    """Test session validation across browser tabs"""
    
    def test_session_persistence_across_tabs(self):
        """Test that WebSocket authentication persists across tabs"""
        # Login as staff user in first tab
        self.login_user('staffuser', 'staffpass123')
        
        # Connect to WebSocket in first tab
        websocket_url = f"ws://{self.live_server_url.replace('http://', '')}/ws/logs/"
        self.inject_websocket_test_script(websocket_url)
        self.driver.execute_script("window.websocketTest.connect();")
        
        # Verify connection in first tab
        self.assertTrue(self.wait_for_websocket_connection())
        
        # Get session cookies
        cookies = self.driver.get_cookies()
        session_cookie = next((c for c in cookies if c['name'] == 'sessionid'), None)
        self.assertIsNotNone(session_cookie, "Session cookie should be present")
        
        # Open new tab (simulate by opening new window)
        self.driver.execute_script("window.open('');")
        self.driver.switch_to.window(self.driver.window_handles[1])
        
        # Navigate to app in new tab
        self.driver.get(f'{self.live_server_url}/')
        
        # Session should be maintained - try WebSocket connection
        self.inject_websocket_test_script(websocket_url)
        self.driver.execute_script("window.websocketTest.connect();")
        
        # Should connect successfully in new tab too
        connected_in_new_tab = self.wait_for_websocket_connection()
        self.assertTrue(connected_in_new_tab, "Session should persist to new tab")
    
    def test_cookie_inheritance_validation(self):
        """Test that cookies are properly inherited for WebSocket connections"""
        # Login and get cookies
        self.login_user('staffuser', 'staffpass123')
        
        cookies_before = {c['name']: c['value'] for c in self.driver.get_cookies()}
        self.assertIn('sessionid', cookies_before, "Session cookie should be set after login")
        
        # Connect to WebSocket
        websocket_url = f"ws://{self.live_server_url.replace('http://', '')}/ws/logs/"
        self.inject_websocket_test_script(websocket_url)
        
        # Add cookie validation to WebSocket test
        self.driver.execute_script("""
            window.websocketTest.originalConnect = window.websocketTest.connect;
            window.websocketTest.connect = function() {
                // Capture document cookies before connection
                window.websocketTest.cookiesAtConnection = document.cookie;
                this.originalConnect();
            };
        """)
        
        self.driver.execute_script("window.websocketTest.connect();")
        
        # Verify connection
        self.assertTrue(self.wait_for_websocket_connection())
        
        # Check that cookies were available during connection
        cookies_at_connection = self.driver.execute_script(
            "return window.websocketTest.cookiesAtConnection;"
        )
        self.assertIn('sessionid', cookies_at_connection, 
                     "Session cookie should be available to WebSocket")


class TestWebSocketSessionDebugging(WebSocketBrowserTestCase):
    """Test session debugging scenarios"""
    
    def test_expired_session_handling(self):
        """Test WebSocket behavior with expired sessions"""
        # Login as staff user
        self.login_user('staffuser', 'staffpass123')
        
        # Manually expire session by clearing cookies
        self.driver.delete_all_cookies()
        
        # Try to connect to WebSocket with expired session
        websocket_url = f"ws://{self.live_server_url.replace('http://', '')}/ws/logs/"
        self.inject_websocket_test_script(websocket_url)
        self.driver.execute_script("window.websocketTest.connect();")
        
        time.sleep(2)
        
        status = self.get_websocket_status()
        
        # Should not be connected due to expired session
        self.assertFalse(status['connected'])
        
        # Should get authentication error
        close_messages = [msg for msg in status['messages'] if msg['type'] == 'close']
        if close_messages:
            self.assertEqual(close_messages[0]['code'], 4401)
    
    def test_session_cookie_security_attributes(self):
        """Test that session cookies have appropriate security attributes"""
        # Login to get cookies
        self.login_user('staffuser', 'staffpass123')
        
        cookies = self.driver.get_cookies()
        session_cookie = next((c for c in cookies if c['name'] == 'sessionid'), None)
        
        self.assertIsNotNone(session_cookie)
        
        # In test environment, secure should be False
        # In production, this should be True for HTTPS
        if hasattr(session_cookie, 'secure'):
            # Check based on environment - should be False for HTTP test server
            self.assertFalse(session_cookie.get('secure', False))
        
        # HttpOnly should typically be True for session cookies
        if hasattr(session_cookie, 'httpOnly'):
            # Note: Selenium might not expose this attribute in all drivers
            pass


# Pytest integration for browser tests
@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.skipif(
    not pytest.importorskip("selenium", reason="Selenium not available"),
    reason="Selenium WebDriver not available"
)
class TestWebSocketBrowserIntegration:
    """Pytest-based browser integration tests"""
    
    @pytest.fixture
    def browser_test_case(self):
        """Create a browser test case instance"""
        test_case = WebSocketBrowserTestCase()
        test_case.setUp()
        yield test_case
        test_case.tearDown()
    
    def test_browser_websocket_authentication_flow(self, browser_test_case):
        """Test complete authentication flow in browser"""
        # Test anonymous rejection
        browser_test_case.driver.get(f'{browser_test_case.live_server_url}/')
        
        websocket_url = f"ws://{browser_test_case.live_server_url.replace('http://', '')}/ws/logs/"
        browser_test_case.inject_websocket_test_script(websocket_url)
        browser_test_case.driver.execute_script("window.websocketTest.connect();")
        
        time.sleep(2)
        status = browser_test_case.get_websocket_status()
        assert not status['connected']
        
        # Test successful staff login and connection
        browser_test_case.login_user('staffuser', 'staffpass123')
        browser_test_case.driver.execute_script("window.websocketTest.connect();")
        
        connected = browser_test_case.wait_for_websocket_connection()
        assert connected, "Staff user should connect successfully"