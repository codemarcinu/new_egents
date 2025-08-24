import django_filters
from django.db.models import Q
from agent_chat_app.chat.models import Conversation, Message, Document


class ConversationFilter(django_filters.FilterSet):
    """Filtering for conversations"""
    
    # Date range filtering
    created_after = django_filters.DateTimeFilter(
        field_name='created_at',
        lookup_expr='gte',
        help_text='Filter conversations created after this date'
    )
    created_before = django_filters.DateTimeFilter(
        field_name='created_at',
        lookup_expr='lte',
        help_text='Filter conversations created before this date'
    )
    
    # Message count filtering
    min_messages = django_filters.NumberFilter(
        field_name='message_count',
        lookup_expr='gte',
        help_text='Minimum number of messages'
    )
    max_messages = django_filters.NumberFilter(
        field_name='message_count',
        lookup_expr='lte',
        help_text='Maximum number of messages'
    )
    
    # Archive status
    is_archived = django_filters.BooleanFilter(
        field_name='is_archived',
        help_text='Filter by archive status'
    )
    
    # Search in title
    title_contains = django_filters.CharFilter(
        field_name='title',
        lookup_expr='icontains',
        help_text='Filter by title containing text'
    )

    class Meta:
        model = Conversation
        fields = {
            'created_at': ['exact', 'gte', 'lte'],
            'updated_at': ['exact', 'gte', 'lte'],
            'is_archived': ['exact'],
            'message_count': ['exact', 'gte', 'lte'],
        }


class MessageFilter(django_filters.FilterSet):
    """Filtering for messages"""
    
    # Filter by conversation
    conversation_id = django_filters.NumberFilter(
        field_name='conversation__id',
        help_text='Filter messages by conversation ID'
    )
    
    # Date range filtering
    created_after = django_filters.DateTimeFilter(
        field_name='created_at',
        lookup_expr='gte',
        help_text='Filter messages created after this date'
    )
    created_before = django_filters.DateTimeFilter(
        field_name='created_at',
        lookup_expr='lte',
        help_text='Filter messages created before this date'
    )
    
    # Message type filtering
    is_from_user = django_filters.BooleanFilter(
        field_name='is_from_user',
        help_text='Filter by message source (user or AI)'
    )
    
    # Text search
    text_contains = django_filters.CharFilter(
        field_name='text',
        lookup_expr='icontains',
        help_text='Filter messages containing text'
    )
    
    # Model filtering (for AI messages)
    model_used = django_filters.CharFilter(
        field_name='model_used',
        lookup_expr='iexact',
        help_text='Filter by AI model used'
    )
    
    # Token count filtering
    min_tokens = django_filters.NumberFilter(
        field_name='token_count',
        lookup_expr='gte',
        help_text='Minimum token count'
    )
    max_tokens = django_filters.NumberFilter(
        field_name='token_count',
        lookup_expr='lte',
        help_text='Maximum token count'
    )

    class Meta:
        model = Message
        fields = {
            'created_at': ['exact', 'gte', 'lte'],
            'is_from_user': ['exact'],
            'token_count': ['exact', 'gte', 'lte'],
            'processing_time': ['exact', 'gte', 'lte'],
        }


class DocumentFilter(django_filters.FilterSet):
    """Filtering for documents"""
    
    # File type filtering
    file_type = django_filters.CharFilter(
        field_name='file_type',
        lookup_expr='iexact',
        help_text='Filter by file type (pdf, txt, docx, etc.)'
    )
    
    # Processing status filtering
    processing_status = django_filters.ChoiceFilter(
        field_name='processing_status',
        choices=Document.PROCESSING_STATUS_CHOICES,
        help_text='Filter by processing status'
    )
    
    # Date range filtering
    uploaded_after = django_filters.DateTimeFilter(
        field_name='uploaded_at',
        lookup_expr='gte',
        help_text='Filter documents uploaded after this date'
    )
    uploaded_before = django_filters.DateTimeFilter(
        field_name='uploaded_at',
        lookup_expr='lte',
        help_text='Filter documents uploaded before this date'
    )
    
    # File size filtering
    min_size = django_filters.NumberFilter(
        field_name='file_size',
        lookup_expr='gte',
        help_text='Minimum file size in bytes'
    )
    max_size = django_filters.NumberFilter(
        field_name='file_size',
        lookup_expr='lte',
        help_text='Maximum file size in bytes'
    )
    
    # Chunk count filtering
    min_chunks = django_filters.NumberFilter(
        field_name='chunk_count',
        lookup_expr='gte',
        help_text='Minimum number of chunks'
    )
    max_chunks = django_filters.NumberFilter(
        field_name='chunk_count',
        lookup_expr='lte',
        help_text='Maximum number of chunks'
    )
    
    # Filename search
    filename_contains = django_filters.CharFilter(
        field_name='filename',
        lookup_expr='icontains',
        help_text='Filter by filename containing text'
    )
    
    # Only successfully processed documents
    only_processed = django_filters.BooleanFilter(
        method='filter_only_processed',
        help_text='Show only successfully processed documents'
    )

    def filter_only_processed(self, queryset, name, value):
        """Filter for only successfully processed documents"""
        if value:
            return queryset.filter(processing_status='completed')
        return queryset

    class Meta:
        model = Document
        fields = {
            'uploaded_at': ['exact', 'gte', 'lte'],
            'processing_status': ['exact'],
            'file_type': ['exact', 'iexact'],
            'file_size': ['exact', 'gte', 'lte'],
            'chunk_count': ['exact', 'gte', 'lte'],
        }