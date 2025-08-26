#!/usr/bin/env python3
"""
Simple WebSocket connection test with debugging.
"""

import asyncio
import websockets
import json

async def test_simple_connection():
    """Test basic WebSocket connection."""
    
    # Token from our test
    token = "7429d40229bb6a43aa5c826b6b3575a44c5cef23"
    
    # Test different connection methods
    test_cases = [
        ("Query param", f"ws://localhost:8000/ws/notifications/?token={token}"),
        ("Auth header", "ws://localhost:8000/ws/notifications/"),
    ]
    
    for name, uri in test_cases:
        print(f"\n🧪 Testing {name}...")
        print(f"URI: {uri}")
        
        try:
            extra_headers = {}
            if "Auth header" in name:
                extra_headers["Authorization"] = f"Token {token}"
            
            if extra_headers:
                print(f"Headers: {extra_headers}")
                async with websockets.connect(uri, extra_headers=extra_headers) as websocket:
                    print("✅ Connected successfully!")
                    await websocket.send(json.dumps({"type": "ping"}))
                    print("📤 Sent ping")
                    
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=2)
                        print(f"📥 Response: {response}")
                    except asyncio.TimeoutError:
                        print("⏰ No response (timeout)")
            else:
                async with websockets.connect(uri) as websocket:
                    print("✅ Connected successfully!")
                    await websocket.send(json.dumps({"type": "ping"}))
                    print("📤 Sent ping")
                    
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=2)
                        print(f"📥 Response: {response}")
                    except asyncio.TimeoutError:
                        print("⏰ No response (timeout)")
                    
        except Exception as e:
            print(f"❌ Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_simple_connection())