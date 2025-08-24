from django.db import models
from django.conf import settings
from django.urls import reverse
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver
import json


class UserSettings(models.Model):
    """User preferences for chat configuration"""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='chat_settings',
        db_index=True
    )
    preferred_model = models.CharField(max_length=100, default="gemma3:4b", db_index=True)
    system_instruction = models.TextField(
        default="You are a helpful AI assistant. Be concise and accurate in your responses.",
        help_text="Custom system instruction/prompt for the AI model"
    )
    max_tokens = models.IntegerField(
        default=2048, 
        help_text="Maximum tokens for response",
        validators=[MinValueValidator(1), MaxValueValidator(32768)]
    )
    temperature = models.FloatField(
        default=0.7, 
        help_text="Response randomness (0.0-1.0)",
        validators=[MinValueValidator(0.0), MaxValueValidator(2.0)]
    )
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "User Settings"
        verbose_name_plural = "User Settings"
        indexes = [
            models.Index(fields=['user', 'preferred_model']),
            models.Index(fields=['-updated_at']),
        ]
    
    def __str__(self):
        return f"Settings for {self.user.username}"


class Conversation(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,
        db_index=True,
        related_name='conversations'
    )
    title = models.CharField(max_length=200, default="New Conversation", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_archived = models.BooleanField(default=False, db_index=True)
    message_count = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['-updated_at']
        verbose_name = "Conversation"
        verbose_name_plural = "Conversations"
        indexes = [
            models.Index(fields=['user', '-updated_at']),
            models.Index(fields=['user', 'is_archived', '-updated_at']),
            models.Index(fields=['title']),
            models.Index(fields=['-created_at']),
        ]
        
    def __str__(self):
        return f"{self.title} by {self.user.username}"
        
    def get_absolute_url(self):
        return reverse('chat:conversation_detail', kwargs={'pk': self.pk})
    
    def update_timestamp(self):
        """Update the updated_at timestamp when new messages are added"""
        self.updated_at = timezone.now()
        self.save(update_fields=['updated_at'])
    
    def increment_message_count(self):
        """Increment message count efficiently"""
        self.message_count = models.F('message_count') + 1
        self.save(update_fields=['message_count'])


class Message(models.Model):
    conversation = models.ForeignKey(
        Conversation, 
        related_name='messages', 
        on_delete=models.CASCADE,
        db_index=True
    )
    text = models.TextField()
    is_from_user = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    token_count = models.PositiveIntegerField(null=True, blank=True)
    processing_time = models.FloatField(null=True, blank=True, help_text="Time in seconds to generate response")
    model_used = models.CharField(max_length=100, blank=True)
    
    class Meta:
        ordering = ['created_at']
        verbose_name = "Message"
        verbose_name_plural = "Messages"
        indexes = [
            models.Index(fields=['conversation', 'created_at']),
            models.Index(fields=['conversation', 'is_from_user']),
            models.Index(fields=['is_from_user', '-created_at']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return f"{'User' if self.is_from_user else 'AI'} on {self.created_at.strftime('%Y-%m-%d %H:%M')}"
    
    def save(self, *args, **kwargs):
        """Override save to update conversation timestamp"""
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            self.conversation.update_timestamp()
            self.conversation.increment_message_count()


class Document(models.Model):
    """Uploaded document for RAG"""
    PROCESSING_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,
        db_index=True,
        related_name='documents'
    )
    filename = models.CharField(max_length=255, db_index=True)
    file_type = models.CharField(max_length=10, db_index=True)
    file_path = models.CharField(max_length=500)
    file_size = models.PositiveIntegerField()
    uploaded_at = models.DateTimeField(auto_now_add=True, db_index=True)
    processing_status = models.CharField(
        max_length=20, 
        choices=PROCESSING_STATUS_CHOICES, 
        default='pending',
        db_index=True
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    processing_error = models.TextField(blank=True)
    chunk_count = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = "Document"
        verbose_name_plural = "Documents"
        indexes = [
            models.Index(fields=['user', '-uploaded_at']),
            models.Index(fields=['user', 'processing_status']),
            models.Index(fields=['processing_status', '-uploaded_at']),
            models.Index(fields=['file_type']),
        ]

    def __str__(self):
        return f"{self.filename} by {self.user.username}"
    
    def mark_as_processing(self):
        """Mark document as being processed"""
        self.processing_status = 'processing'
        self.save(update_fields=['processing_status'])
    
    def mark_as_completed(self, chunk_count=0):
        """Mark document as successfully processed"""
        self.processing_status = 'completed'
        self.processed_at = timezone.now()
        self.chunk_count = chunk_count
        self.save(update_fields=['processing_status', 'processed_at', 'chunk_count'])
    
    def mark_as_failed(self, error_message=''):
        """Mark document as failed to process"""
        self.processing_status = 'failed'
        self.processing_error = error_message
        self.save(update_fields=['processing_status', 'processing_error'])


class DocumentChunk(models.Model):
    """Text chunk from processed document"""
    document = models.ForeignKey(
        Document, 
        related_name='chunks', 
        on_delete=models.CASCADE,
        db_index=True
    )
    content = models.TextField()
    chunk_index = models.PositiveIntegerField(db_index=True)
    total_chunks = models.PositiveIntegerField()
    embedding = models.TextField(blank=True, null=True)  # JSON serialized embedding vector
    character_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['document', 'chunk_index']
        verbose_name = "Document Chunk"
        verbose_name_plural = "Document Chunks"
        unique_together = ['document', 'chunk_index']
        indexes = [
            models.Index(fields=['document', 'chunk_index']),
            models.Index(fields=['-created_at']),
        ]
    
    def set_embedding(self, embedding_vector):
        """Store embedding vector as JSON"""
        self.embedding = json.dumps(embedding_vector)
    
    def get_embedding(self):
        """Retrieve embedding vector from JSON"""
        if self.embedding:
            return json.loads(self.embedding)
        return None
    
    def save(self, *args, **kwargs):
        """Override save to calculate character count"""
        if self.content:
            self.character_count = len(self.content)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Chunk {self.chunk_index+1}/{self.total_chunks} of {self.document.filename}"


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_settings(sender, instance, created, **kwargs):
    """Automatically create UserSettings when a new user is created"""
    if created:
        UserSettings.objects.create(user=instance)