import json
import asyncio
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from .models import Conversation, Message
from .services import OllamaService
from .hybrid_rag_service import HybridRAGService

logger = logging.getLogger(__name__)

class ChatConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.hybrid_rag_service = HybridRAGService()
    
    async def connect(self):
        # Get conversation ID from URL
        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        self.room_group_name = f'chat_{self.conversation_id}'
        
        # Check authentication
        if self.scope["user"] == AnonymousUser():
            await self.close()
            return
        
        # Verify user has access to this conversation
        has_access = await self.check_conversation_access()
        if not has_access:
            await self.close()
            return
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        logger.info(f"WebSocket connected for conversation {self.conversation_id}")

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        logger.info(f"WebSocket disconnected for conversation {self.conversation_id}")

    async def receive(self, text_data):
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type')
            message_content = text_data_json.get('message', '')
            selected_model = text_data_json.get('selected_model', '')
            temp_instruction = text_data_json.get('temp_instruction', '')
            
            if message_type == 'chat_message' and message_content.strip():
                # Save user message to database
                user_message = await self.save_message(
                    conversation_id=self.conversation_id,
                    text=message_content,
                    is_from_user=True
                )
                
                # Send user message to room group
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_message',
                        'message': message_content,
                        'is_from_user': True,
                        'timestamp': user_message.created_at.isoformat(),
                        'message_id': user_message.id
                    }
                )
                
                # Send typing indicator
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'typing_indicator',
                        'is_typing': True
                    }
                )
                
                # Generate AI response asynchronously
                asyncio.create_task(self.generate_ai_response(message_content, selected_model, temp_instruction))
                
        except json.JSONDecodeError:
            logger.error("Invalid JSON received in WebSocket")
        except Exception as e:
            logger.error(f"Error processing WebSocket message: {e}")

    async def generate_ai_response(self, user_message, selected_model=None, temp_instruction=None):
        """Generate AI response in background using hybrid RAG"""
        try:
            # Get enhanced AI response using hybrid RAG (this runs in a thread pool)
            response_data = await asyncio.to_thread(
                self.hybrid_rag_service.get_enhanced_response,
                prompt=user_message,
                model=selected_model if selected_model else None,
                user_id=self.scope["user"].id,
                custom_instruction=temp_instruction if temp_instruction else None,
                conversation_id=self.conversation_id
            )
            
            ai_response, response_metadata = response_data
            
            # Format response with transparency information
            formatted_response = self.hybrid_rag_service.format_response_with_transparency(
                ai_response, response_metadata
            )
            
            # Save AI message to database
            ai_message = await self.save_message(
                conversation_id=self.conversation_id,
                text=formatted_response,
                is_from_user=False
            )
            
            # Send metadata as additional information
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'response_metadata',
                    'metadata': {
                        'knowledge_source': response_metadata.knowledge_source.value,
                        'confidence_level': response_metadata.confidence.overall,
                        'sources_used': len(response_metadata.rag_chunks_used),
                        'fallback_used': response_metadata.fallback_used
                    }
                }
            )
            
            # Stop typing indicator
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'typing_indicator',
                    'is_typing': False
                }
            )
            
            # Send AI response to room group
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': formatted_response,
                    'is_from_user': False,
                    'timestamp': ai_message.created_at.isoformat(),
                    'message_id': ai_message.id
                }
            )
            
        except Exception as e:
            logger.error(f"Error generating AI response: {e}")
            
            # Stop typing indicator even on error
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'typing_indicator',
                    'is_typing': False
                }
            )
            
            # Send error message
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'error_message',
                    'message': 'Sorry, I encountered an error generating a response.'
                }
            )

    # Receive message from room group
    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message': event['message'],
            'is_from_user': event['is_from_user'],
            'timestamp': event['timestamp'],
            'message_id': event['message_id']
        }))

    async def typing_indicator(self, event):
        await self.send(text_data=json.dumps({
            'type': 'typing_indicator',
            'is_typing': event['is_typing']
        }))

    async def error_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'error_message',
            'message': event['message']
        }))

    async def response_metadata(self, event):
        """Send response metadata to client"""
        await self.send(text_data=json.dumps({
            'type': 'response_metadata',
            'metadata': event['metadata']
        }))

    @database_sync_to_async
    def check_conversation_access(self):
        """Check if user has access to this conversation"""
        try:
            conversation = Conversation.objects.get(
                id=self.conversation_id,
                user=self.scope["user"]
            )
            return True
        except Conversation.DoesNotExist:
            return False

    @database_sync_to_async
    def save_message(self, conversation_id, text, is_from_user):
        """Save message to database"""
        conversation = Conversation.objects.get(id=conversation_id)
        return Message.objects.create(
            conversation=conversation,
            text=text,
            is_from_user=is_from_user
        )