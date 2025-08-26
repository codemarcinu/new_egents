#!/usr/bin/env python3
"""
Enhanced WebSocket authentication test with token support.
"""

import asyncio
import json
import time
import websockets
import requests
from urllib.parse import urlencode

# Configuration
BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000"
TEST_USER = {
    "username": "testuser",
    "password": "testpass123"
}


async def test_websocket_auth():
    """Test WebSocket authentication with token."""
    print("🧪 Testing WebSocket Authentication...")
    
    # Step 1: Create user and get token
    print("\n1. Creating test user and getting token...")
    
    try:
        print("ℹ️ Using existing user, skipping creation...")
        
        # Get token
        login_response = requests.post(
            f"{BASE_URL}/api/auth-token/",
            json={
                "username": TEST_USER["username"],
                "password": TEST_USER["password"]
            },
            headers={"Accept": "application/json; version=v1"}
        )
        
        if login_response.status_code != 200:
            print(f"❌ Failed to login: {login_response.status_code} - {login_response.text}")
            return
            
        token = login_response.json().get("token")
        if not token:
            print("❌ No token received from login")
            return
            
        print(f"✅ Token received: {token[:20]}...")
        
        # Step 2: Create a test receipt
        print("\n2. Creating test receipt...")
        
        with open('/tmp/test_receipt.jpg', 'wb') as f:
            f.write(b"fake image data for testing")
        
        with open('/tmp/test_receipt.jpg', 'rb') as f:
            files = {'receipt_file': ('test_receipt.jpg', f, 'image/jpeg')}
            upload_response = requests.post(
                f"{BASE_URL}/api/v1/receipts/upload/",
                files=files,
                headers={
                    "Authorization": f"Token {token}",
                    "Accept": "application/json; version=v1"
                }
            )
        
        if upload_response.status_code != 201:
            print(f"❌ Failed to create receipt: {upload_response.status_code} - {upload_response.text}")
            return
            
        receipt_id = upload_response.json().get("id")
        print(f"✅ Receipt created: ID {receipt_id}")
        
        # Step 3: Test WebSocket connection with token in query parameter
        print("\n3. Testing WebSocket connection with token authentication...")
        
        query_params = urlencode({"token": token})
        ws_uri = f"{WS_URL}/ws/receipt/{receipt_id}/?{query_params}"
        
        try:
            async with websockets.connect(ws_uri) as websocket:
                print("✅ WebSocket connected successfully!")
                
                # Send test message
                test_message = {"type": "get_status"}
                await websocket.send(json.dumps(test_message))
                print(f"📤 Sent: {test_message}")
                
                # Wait for response
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    response_data = json.loads(response)
                    print(f"📥 Received: {response_data}")
                    
                    if response_data.get("type") == "status_update":
                        print("✅ Status update received successfully!")
                        
                        # Check for server timestamp (performance middleware)
                        if "server_timestamp" in response_data:
                            server_time = response_data["server_timestamp"]
                            client_time = time.time()
                            latency = (client_time - server_time) * 1000  # ms
                            print(f"📊 WebSocket latency: {latency:.2f}ms")
                        
                    else:
                        print(f"⚠️ Unexpected message type: {response_data.get('type')}")
                        
                except asyncio.TimeoutError:
                    print("⚠️ No response received within 5 seconds")
                
                # Test sending another message
                await asyncio.sleep(1)
                await websocket.send(json.dumps({"type": "get_status"}))
                
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=3.0)
                    print(f"📥 Second response: {json.loads(response)}")
                except asyncio.TimeoutError:
                    print("⚠️ No second response received")
                    
        except websockets.exceptions.ConnectionClosed as e:
            print(f"❌ WebSocket connection closed: {e}")
        except Exception as e:
            print(f"❌ WebSocket connection failed: {e}")
        
        # Step 4: Test other WebSocket endpoints
        print("\n4. Testing other WebSocket endpoints...")
        
        endpoints_to_test = [
            ("Inventory Notifications", f"{WS_URL}/ws/inventory/?{query_params}"),
            ("General Notifications", f"{WS_URL}/ws/notifications/?{query_params}")
        ]
        
        for name, uri in endpoints_to_test:
            try:
                async with websockets.connect(uri) as websocket:
                    print(f"✅ {name}: Connected successfully")
                    
                    # Send a ping
                    await websocket.ping()
                    print(f"✅ {name}: Ping successful")
                    
            except Exception as e:
                print(f"❌ {name}: Connection failed - {e}")
        
        print("\n🎉 WebSocket authentication test completed!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")


async def test_websocket_without_auth():
    """Test WebSocket connection without authentication (should fail)."""
    print("\n🚫 Testing WebSocket without authentication...")
    
    try:
        # Try to connect without token
        ws_uri = f"{WS_URL}/ws/inventory/"
        
        async with websockets.connect(ws_uri) as websocket:
            print("❌ Connection succeeded when it should have failed!")
            
    except websockets.exceptions.ConnectionClosedError as e:
        print(f"✅ Connection properly rejected: {e}")
    except Exception as e:
        print(f"✅ Connection failed as expected: {e}")


async def main():
    """Run all WebSocket authentication tests."""
    print("🚀 Starting WebSocket Authentication Tests")
    print("=" * 50)
    
    await test_websocket_auth()
    await test_websocket_without_auth()
    
    print("\n" + "=" * 50)
    print("✅ All tests completed!")


if __name__ == "__main__":
    asyncio.run(main())