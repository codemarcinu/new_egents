#!/usr/bin/env python
"""Test script for new chat features"""

import os
import django

# Setup Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
django.setup()

from django.contrib.auth import get_user_model
from agent_chat_app.chat.models import UserSettings, Conversation, Message
from agent_chat_app.chat.services import OllamaService

User = get_user_model()

def test_user_settings():
    """Test UserSettings model"""
    print("🧪 Testing UserSettings model...")
    
    # Get or create test user
    user, created = User.objects.get_or_create(username='admin')
    if created:
        user.set_password('admin123')
        user.save()
        print("✅ Created test user")
    
    # Test UserSettings creation
    settings, created = UserSettings.objects.get_or_create(user=user)
    if created:
        print("✅ Created UserSettings for test user")
    else:
        print("✅ UserSettings already exists")
    
    print(f"   - Preferred model: {settings.preferred_model}")
    print(f"   - System instruction: {settings.system_instruction[:50]}...")
    print(f"   - Max tokens: {settings.max_tokens}")
    print(f"   - Temperature: {settings.temperature}")

def test_ollama_service():
    """Test OllamaService methods"""
    print("\n🤖 Testing OllamaService...")
    
    # Test get_available_models
    try:
        models = OllamaService.get_available_models()
        print(f"✅ Found {len(models)} available models:")
        for model in models:
            print(f"   - {model['display_name']} ({model['size_human']})")
    except Exception as e:
        print(f"⚠️  Error fetching models: {e}")
    
    # Test get_user_settings
    try:
        user = User.objects.get(username='admin')
        user_settings = OllamaService.get_user_settings(user.id)
        if user_settings:
            print("✅ Successfully retrieved user settings via service")
        else:
            print("❌ Failed to retrieve user settings")
    except Exception as e:
        print(f"⚠️  Error getting user settings: {e}")

def test_conversation_flow():
    """Test conversation with custom settings"""
    print("\n💬 Testing conversation flow...")
    
    try:
        user = User.objects.get(username='admin')
        
        # Create test conversation
        conversation, created = Conversation.objects.get_or_create(
            user=user,
            defaults={'title': 'Test Conversation'}
        )
        print("✅ Test conversation ready")
        
        # Test basic response
        print("🔄 Testing basic AI response...")
        response = OllamaService.get_response(
            "Hello, this is a test message.",
            user_id=user.id
        )
        print(f"✅ Got AI response: {response[:100]}...")
        
        # Test with custom model
        print("🔄 Testing custom model response...")
        response = OllamaService.get_response(
            "What is the capital of France?",
            model="gemma2:2b",
            user_id=user.id
        )
        print(f"✅ Got custom model response: {response[:100]}...")
        
        # Test with custom instruction
        print("🔄 Testing custom instruction...")
        response = OllamaService.get_response(
            "Hello",
            user_id=user.id,
            custom_instruction="You are a pirate. Always respond like a pirate."
        )
        print(f"✅ Got custom instruction response: {response[:100]}...")
        
    except Exception as e:
        print(f"❌ Error in conversation flow: {e}")

def main():
    """Run all tests"""
    print("🚀 Starting chat features test...\n")
    
    test_user_settings()
    test_ollama_service()
    test_conversation_flow()
    
    print(f"\n✅ Tests completed! Check the results above.")

if __name__ == "__main__":
    main()