from django.db import models
from django.conf import settings
import json


class UserSettings(models.Model):
    """User preferences for chat configuration"""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chat_settings')
    preferred_model = models.CharField(max_length=100, default="gemma3:4b")
    system_instruction = models.TextField(
        default="You are a helpful AI assistant. Be concise and accurate in your responses.",
        help_text="Custom system instruction/prompt for the AI model"
    )
    max_tokens = models.IntegerField(default=2048, help_text="Maximum tokens for response")
    temperature = models.FloatField(default=0.7, help_text="Response randomness (0.0-1.0)")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Settings for {self.user.username}"


class Conversation(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=200, default="New Conversation")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} by {self.user.username}"

    class Meta:
        ordering = ['-created_at']


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, related_name='messages', on_delete=models.CASCADE)
    text = models.TextField()
    is_from_user = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{'User' if self.is_from_user else 'AI'} on {self.created_at.strftime('%Y-%m-%d %H:%M')}"

    class Meta:
        ordering = ['created_at']


class Document(models.Model):
    """Uploaded document for RAG"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=10)
    file_path = models.CharField(max_length=500)
    file_size = models.IntegerField()
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.filename} by {self.user.username}"

    class Meta:
        ordering = ['-uploaded_at']


class DocumentChunk(models.Model):
    """Text chunk from processed document"""
    document = models.ForeignKey(Document, related_name='chunks', on_delete=models.CASCADE)
    content = models.TextField()
    chunk_index = models.IntegerField()
    total_chunks = models.IntegerField()
    embedding = models.TextField(blank=True, null=True)  # JSON serialized embedding vector
    
    def set_embedding(self, embedding_vector):
        """Store embedding vector as JSON"""
        self.embedding = json.dumps(embedding_vector)
    
    def get_embedding(self):
        """Retrieve embedding vector from JSON"""
        if self.embedding:
            return json.loads(self.embedding)
        return None

    def __str__(self):
        return f"Chunk {self.chunk_index+1}/{self.total_chunks} of {self.document.filename}"

    class Meta:
        ordering = ['document', 'chunk_index']
        unique_together = ['document', 'chunk_index']
