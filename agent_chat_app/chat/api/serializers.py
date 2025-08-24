from rest_framework import serializers
from django.contrib.auth import get_user_model
from agent_chat_app.chat.models import (
    Conversation, 
    Message, 
    Document, 
    DocumentChunk, 
    UserSettings
)

User = get_user_model()


class UserBasicSerializer(serializers.ModelSerializer):
    """Basic user information for API responses"""
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name']
        read_only_fields = ['id', 'username']


class UserSettingsSerializer(serializers.ModelSerializer):
    """User settings for chat configuration"""
    class Meta:
        model = UserSettings
        fields = [
            'id', 'preferred_model', 'system_instruction', 
            'max_tokens', 'temperature', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_temperature(self, value):
        if value < 0.0 or value > 2.0:
            raise serializers.ValidationError("Temperature must be between 0.0 and 2.0")
        return value

    def validate_max_tokens(self, value):
        if value < 1 or value > 32768:
            raise serializers.ValidationError("Max tokens must be between 1 and 32768")
        return value


class MessageSerializer(serializers.ModelSerializer):
    """Message serializer with conversation context"""
    processing_time_display = serializers.SerializerMethodField()
    
    class Meta:
        model = Message
        fields = [
            'id', 'text', 'is_from_user', 'created_at',
            'token_count', 'processing_time', 'processing_time_display',
            'model_used'
        ]
        read_only_fields = [
            'id', 'created_at', 'token_count', 
            'processing_time', 'model_used'
        ]

    def get_processing_time_display(self, obj):
        """Human readable processing time"""
        if obj.processing_time:
            return f"{obj.processing_time:.2f}s"
        return None


class ConversationListSerializer(serializers.ModelSerializer):
    """Conversation list serializer with minimal data"""
    user = UserBasicSerializer(read_only=True)
    latest_message = serializers.SerializerMethodField()
    
    class Meta:
        model = Conversation
        fields = [
            'id', 'title', 'created_at', 'updated_at', 
            'is_archived', 'message_count', 'user', 'latest_message'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'message_count']

    def get_latest_message(self, obj):
        """Get the latest message preview"""
        latest = obj.messages.order_by('-created_at').first()
        if latest:
            return {
                'text': latest.text[:100] + '...' if len(latest.text) > 100 else latest.text,
                'is_from_user': latest.is_from_user,
                'created_at': latest.created_at
            }
        return None


class ConversationDetailSerializer(serializers.ModelSerializer):
    """Detailed conversation serializer with messages"""
    user = UserBasicSerializer(read_only=True)
    messages = MessageSerializer(many=True, read_only=True)
    
    class Meta:
        model = Conversation
        fields = [
            'id', 'title', 'created_at', 'updated_at',
            'is_archived', 'message_count', 'user', 'messages'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'message_count']


class ConversationCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating new conversations"""
    initial_message = serializers.CharField(write_only=True, required=False)
    
    class Meta:
        model = Conversation
        fields = ['title', 'initial_message']

    def create(self, validated_data):
        initial_message = validated_data.pop('initial_message', None)
        user = self.context['request'].user
        conversation = Conversation.objects.create(user=user, **validated_data)
        
        if initial_message:
            Message.objects.create(
                conversation=conversation,
                text=initial_message,
                is_from_user=True
            )
        
        return conversation


class MessageCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating new messages"""
    class Meta:
        model = Message
        fields = ['text']

    def create(self, validated_data):
        conversation = self.context['conversation']
        return Message.objects.create(
            conversation=conversation,
            is_from_user=True,
            **validated_data
        )


class DocumentChunkSerializer(serializers.ModelSerializer):
    """Document chunk serializer"""
    class Meta:
        model = DocumentChunk
        fields = [
            'id', 'content', 'chunk_index', 'total_chunks',
            'character_count', 'created_at'
        ]
        read_only_fields = [
            'id', 'chunk_index', 'total_chunks', 
            'character_count', 'created_at'
        ]


class DocumentSerializer(serializers.ModelSerializer):
    """Document serializer with upload status"""
    user = UserBasicSerializer(read_only=True)
    chunks = DocumentChunkSerializer(many=True, read_only=True)
    processing_status_display = serializers.CharField(
        source='get_processing_status_display', 
        read_only=True
    )
    
    class Meta:
        model = Document
        fields = [
            'id', 'filename', 'file_type', 'file_size',
            'uploaded_at', 'processing_status', 'processing_status_display',
            'processed_at', 'processing_error', 'chunk_count',
            'user', 'chunks'
        ]
        read_only_fields = [
            'id', 'uploaded_at', 'processing_status', 'processed_at',
            'processing_error', 'chunk_count', 'file_size'
        ]


class DocumentUploadSerializer(serializers.ModelSerializer):
    """Serializer for document upload"""
    file = serializers.FileField(write_only=True)
    
    class Meta:
        model = Document
        fields = ['file', 'filename']

    def validate_file(self, value):
        """Validate uploaded file"""
        if value.size > 10 * 1024 * 1024:  # 10MB limit
            raise serializers.ValidationError("File size cannot exceed 10MB")
        
        allowed_types = ['.txt', '.pdf', '.docx', '.md']
        if not any(value.name.lower().endswith(ext) for ext in allowed_types):
            raise serializers.ValidationError(
                f"File type not supported. Allowed types: {', '.join(allowed_types)}"
            )
        
        return value

    def create(self, validated_data):
        file = validated_data.pop('file')
        user = self.context['request'].user
        
        # Create document instance
        document = Document.objects.create(
            user=user,
            filename=validated_data.get('filename', file.name),
            file_type=file.name.split('.')[-1].lower(),
            file_size=file.size,
            file_path='',  # Will be set after saving file
        )
        
        # TODO: Handle file saving and processing
        # This would integrate with your document processing pipeline
        
        return document