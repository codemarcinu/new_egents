from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404
from django.db.models import Q, Prefetch
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.core.cache import cache
from drf_spectacular.utils import extend_schema, extend_schema_view
from drf_spectacular.openapi import OpenApiParameter, OpenApiTypes

from agent_chat_app.chat.models import (
    Conversation, 
    Message, 
    Document, 
    DocumentChunk, 
    UserSettings
)
from .serializers import (
    ConversationListSerializer,
    ConversationDetailSerializer,
    ConversationCreateSerializer,
    MessageSerializer,
    MessageCreateSerializer,
    DocumentSerializer,
    DocumentUploadSerializer,
    UserSettingsSerializer,
)
from .filters import ConversationFilter, MessageFilter, DocumentFilter


@extend_schema_view(
    list=extend_schema(
        description="List all conversations for the authenticated user",
        tags=['Conversations']
    ),
    create=extend_schema(
        description="Create a new conversation",
        tags=['Conversations']
    ),
    retrieve=extend_schema(
        description="Retrieve a specific conversation with all messages",
        tags=['Conversations']
    ),
    update=extend_schema(
        description="Update conversation details",
        tags=['Conversations']
    ),
    destroy=extend_schema(
        description="Delete a conversation",
        tags=['Conversations']
    ),
)
class ConversationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing conversations.
    
    Provides CRUD operations for conversations with proper filtering and permissions.
    """
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ConversationFilter
    search_fields = ['title']
    ordering_fields = ['created_at', 'updated_at', 'message_count']
    ordering = ['-updated_at']

    def get_queryset(self):
        """Filter conversations by authenticated user"""
        return Conversation.objects.filter(
            user=self.request.user
        ).select_related('user').prefetch_related(
            Prefetch('messages', queryset=Message.objects.order_by('created_at'))
        )

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'list':
            return ConversationListSerializer
        elif self.action == 'create':
            return ConversationCreateSerializer
        return ConversationDetailSerializer

    @method_decorator(cache_page(60 * 5))  # Cache for 5 minutes
    def list(self, request, *args, **kwargs):
        """List conversations with caching"""
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer):
        """Set user when creating conversation"""
        serializer.save(user=self.request.user)

    @extend_schema(
        description="Send a message to the conversation",
        request=MessageCreateSerializer,
        responses={201: MessageSerializer},
        tags=['Conversations']
    )
    @action(detail=True, methods=['post'], url_path='messages')
    def send_message(self, request, pk=None):
        """Send a message to this conversation"""
        conversation = self.get_object()
        serializer = MessageCreateSerializer(
            data=request.data,
            context={'conversation': conversation, 'request': request}
        )
        
        if serializer.is_valid():
            message = serializer.save()
            
            # TODO: Trigger AI response generation here
            # This would integrate with your chat service
            
            response_serializer = MessageSerializer(message)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        description="Archive/unarchive a conversation",
        request=None,
        responses={200: ConversationDetailSerializer},
        tags=['Conversations']
    )
    @action(detail=True, methods=['post'], url_path='toggle-archive')
    def toggle_archive(self, request, pk=None):
        """Toggle archive status of conversation"""
        conversation = self.get_object()
        conversation.is_archived = not conversation.is_archived
        conversation.save(update_fields=['is_archived'])
        
        serializer = self.get_serializer(conversation)
        return Response(serializer.data)

    @extend_schema(
        description="Get conversation statistics",
        responses={200: dict},
        tags=['Conversations']
    )
    @action(detail=True, methods=['get'], url_path='stats')
    def stats(self, request, pk=None):
        """Get conversation statistics"""
        conversation = self.get_object()
        
        stats = {
            'message_count': conversation.message_count,
            'user_messages': conversation.messages.filter(is_from_user=True).count(),
            'ai_messages': conversation.messages.filter(is_from_user=False).count(),
            'total_characters': sum(
                len(msg.text) for msg in conversation.messages.all()
            ),
            'created_at': conversation.created_at,
            'updated_at': conversation.updated_at,
        }
        
        return Response(stats)


@extend_schema_view(
    list=extend_schema(
        description="List messages for a conversation",
        tags=['Messages']
    ),
    retrieve=extend_schema(
        description="Retrieve a specific message",
        tags=['Messages']
    ),
)
class MessageViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing messages.
    
    Messages are read-only through the API as they're managed through conversation endpoints.
    """
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = MessageFilter
    ordering_fields = ['created_at']
    ordering = ['created_at']

    def get_queryset(self):
        """Filter messages by user's conversations"""
        return Message.objects.filter(
            conversation__user=self.request.user
        ).select_related('conversation')

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='conversation_id',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description='Filter messages by conversation ID'
            ),
        ]
    )
    def list(self, request, *args, **kwargs):
        """List messages with optional conversation filter"""
        return super().list(request, *args, **kwargs)


@extend_schema_view(
    list=extend_schema(
        description="List user's uploaded documents",
        tags=['Documents']
    ),
    create=extend_schema(
        description="Upload a new document for RAG processing",
        tags=['Documents']
    ),
    retrieve=extend_schema(
        description="Retrieve document details with chunks",
        tags=['Documents']
    ),
    destroy=extend_schema(
        description="Delete a document and its chunks",
        tags=['Documents']
    ),
)
class DocumentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing documents and RAG processing.
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = DocumentFilter
    search_fields = ['filename']
    ordering_fields = ['uploaded_at', 'file_size', 'chunk_count']
    ordering = ['-uploaded_at']

    def get_queryset(self):
        """Filter documents by authenticated user"""
        return Document.objects.filter(
            user=self.request.user
        ).prefetch_related('chunks')

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return DocumentUploadSerializer
        return DocumentSerializer

    def perform_create(self, serializer):
        """Set user when creating document"""
        serializer.save(user=self.request.user)

    @extend_schema(
        description="Reprocess a failed or pending document",
        request=None,
        responses={200: DocumentSerializer},
        tags=['Documents']
    )
    @action(detail=True, methods=['post'], url_path='reprocess')
    def reprocess(self, request, pk=None):
        """Reprocess a document"""
        document = self.get_object()
        
        if document.processing_status == 'completed':
            return Response(
                {'error': 'Document is already processed'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Reset status and trigger reprocessing
        document.processing_status = 'pending'
        document.processing_error = ''
        document.save(update_fields=['processing_status', 'processing_error'])
        
        # TODO: Trigger document processing task
        
        serializer = self.get_serializer(document)
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(
        description="Get user settings (returns single object)",
        tags=['User Settings']
    ),
    update=extend_schema(
        description="Update user settings",
        tags=['User Settings']
    ),
)
class UserSettingsViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing user chat settings.
    
    Each user has exactly one settings object.
    """
    serializer_class = UserSettingsSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'put', 'patch']  # No create/delete

    def get_queryset(self):
        """Return user's settings"""
        return UserSettings.objects.filter(user=self.request.user)

    def get_object(self):
        """Get or create user settings"""
        settings, created = UserSettings.objects.get_or_create(
            user=self.request.user
        )
        return settings

    def list(self, request, *args, **kwargs):
        """Return single settings object instead of list"""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @extend_schema(
        description="Reset user settings to defaults",
        request=None,
        responses={200: UserSettingsSerializer},
        tags=['User Settings']
    )
    @action(detail=False, methods=['post'], url_path='reset')
    def reset_to_defaults(self, request):
        """Reset user settings to defaults"""
        settings = self.get_object()
        settings.preferred_model = "gemma3:4b"
        settings.system_instruction = "You are a helpful AI assistant. Be concise and accurate in your responses."
        settings.max_tokens = 2048
        settings.temperature = 0.7
        settings.save()
        
        # Clear cache
        cache.delete(f'user_settings_{request.user.id}')
        
        serializer = self.get_serializer(settings)
        return Response(serializer.data)