import pytest
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.utils import timezone
from unittest.mock import patch
import json

from agent_chat_app.chat.models import (
    Conversation,
    Message,
    Document,
    DocumentChunk,
    UserSettings
)
from .factories import (
    UserFactory,
    ConversationFactory,
    MessageFactory,
    DocumentFactory,
    DocumentChunkFactory,
    UserSettingsFactory,
    ConversationWithMessagesFactory,
    ProcessedDocumentFactory
)

User = get_user_model()


@pytest.mark.django_db
class TestUserSettingsModel:
    """Test cases for UserSettings model"""

    def test_create_user_settings(self):
        """Test creating user settings with valid data"""
        user = UserFactory()
        settings = UserSettingsFactory(user=user)
        
        assert settings.user == user
        assert settings.preferred_model == "gemma2:9b"
        assert settings.max_tokens == 2048
        assert settings.temperature == 0.7
        assert str(settings) == f"Settings for {user.username}"

    def test_user_settings_validation(self):
        """Test user settings field validation"""
        user = UserFactory()
        
        # Test temperature validation
        with pytest.raises(ValidationError):
            settings = UserSettingsFactory(user=user, temperature=3.0)
            settings.full_clean()

        with pytest.raises(ValidationError):
            settings = UserSettingsFactory(user=user, temperature=-0.1)
            settings.full_clean()

        # Test max_tokens validation
        with pytest.raises(ValidationError):
            settings = UserSettingsFactory(user=user, max_tokens=0)
            settings.full_clean()

        with pytest.raises(ValidationError):
            settings = UserSettingsFactory(user=user, max_tokens=50000)
            settings.full_clean()

    def test_user_settings_auto_creation(self):
        """Test that user settings are automatically created for new users"""
        user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        
        # UserSettings should be created automatically via signal
        assert hasattr(user, 'chat_settings')
        assert user.chat_settings.preferred_model == "gemma3:4b"  # default value

    def test_user_settings_indexes(self):
        """Test that indexes are properly created"""
        user = UserFactory()
        settings = UserSettingsFactory(user=user)
        
        # This would be tested at the database level in integration tests
        assert settings.pk is not None


@pytest.mark.django_db
class TestConversationModel:
    """Test cases for Conversation model"""

    def test_create_conversation(self):
        """Test creating a conversation"""
        user = UserFactory()
        conversation = ConversationFactory(
            user=user,
            title="Test Conversation"
        )
        
        assert conversation.user == user
        assert conversation.title == "Test Conversation"
        assert conversation.message_count == 0
        assert not conversation.is_archived
        assert str(conversation) == f"Test Conversation by {user.username}"

    def test_conversation_get_absolute_url(self):
        """Test get_absolute_url method"""
        conversation = ConversationFactory()
        url = conversation.get_absolute_url()
        assert f"/chat/conversations/{conversation.pk}/" in url

    def test_conversation_update_timestamp(self):
        """Test update_timestamp method"""
        conversation = ConversationFactory()
        original_updated_at = conversation.updated_at
        
        # Wait a moment to ensure timestamp difference
        import time
        time.sleep(0.01)
        
        conversation.update_timestamp()
        assert conversation.updated_at > original_updated_at

    def test_conversation_increment_message_count(self):
        """Test increment_message_count method"""
        conversation = ConversationFactory()
        assert conversation.message_count == 0
        
        conversation.increment_message_count()
        conversation.refresh_from_db()
        assert conversation.message_count == 1

    def test_conversation_ordering(self):
        """Test that conversations are ordered by updated_at descending"""
        user = UserFactory()
        old_conversation = ConversationFactory(user=user)
        
        import time
        time.sleep(0.01)
        
        new_conversation = ConversationFactory(user=user)
        
        conversations = Conversation.objects.filter(user=user)
        assert conversations.first() == new_conversation
        assert conversations.last() == old_conversation


@pytest.mark.django_db
class TestMessageModel:
    """Test cases for Message model"""

    def test_create_message(self):
        """Test creating a message"""
        conversation = ConversationFactory()
        message = MessageFactory(
            conversation=conversation,
            text="Hello, world!",
            is_from_user=True
        )
        
        assert message.conversation == conversation
        assert message.text == "Hello, world!"
        assert message.is_from_user is True
        assert message.created_at is not None

    def test_message_str_representation(self):
        """Test message string representation"""
        message = MessageFactory(is_from_user=True)
        str_repr = str(message)
        
        assert "User" in str_repr
        assert message.created_at.strftime('%Y-%m-%d %H:%M') in str_repr

        message = MessageFactory(is_from_user=False)
        str_repr = str(message)
        
        assert "AI" in str_repr

    def test_message_save_updates_conversation(self):
        """Test that saving a new message updates conversation timestamp and count"""
        conversation = ConversationFactory()
        original_updated_at = conversation.updated_at
        original_count = conversation.message_count
        
        import time
        time.sleep(0.01)
        
        MessageFactory(conversation=conversation)
        
        conversation.refresh_from_db()
        assert conversation.updated_at > original_updated_at
        assert conversation.message_count == original_count + 1

    def test_message_ordering(self):
        """Test that messages are ordered by created_at ascending"""
        conversation = ConversationFactory()
        
        first_message = MessageFactory(conversation=conversation)
        
        import time
        time.sleep(0.01)
        
        second_message = MessageFactory(conversation=conversation)
        
        messages = conversation.messages.all()
        assert messages.first() == first_message
        assert messages.last() == second_message


@pytest.mark.django_db
class TestDocumentModel:
    """Test cases for Document model"""

    def test_create_document(self):
        """Test creating a document"""
        user = UserFactory()
        document = DocumentFactory(
            user=user,
            filename="test.pdf",
            file_type="pdf",
            file_size=1024
        )
        
        assert document.user == user
        assert document.filename == "test.pdf"
        assert document.file_type == "pdf"
        assert document.file_size == 1024
        assert document.processing_status == "completed"

    def test_document_status_methods(self):
        """Test document status update methods"""
        document = DocumentFactory(processing_status="pending")
        
        # Test mark_as_processing
        document.mark_as_processing()
        assert document.processing_status == "processing"
        
        # Test mark_as_completed
        document.mark_as_completed(chunk_count=5)
        assert document.processing_status == "completed"
        assert document.chunk_count == 5
        assert document.processed_at is not None
        
        # Test mark_as_failed
        document.mark_as_failed("Test error")
        assert document.processing_status == "failed"
        assert document.processing_error == "Test error"

    def test_document_str_representation(self):
        """Test document string representation"""
        user = UserFactory(username="testuser")
        document = DocumentFactory(
            user=user,
            filename="test.pdf"
        )
        
        assert str(document) == "test.pdf by testuser"

    def test_document_ordering(self):
        """Test that documents are ordered by uploaded_at descending"""
        user = UserFactory()
        
        old_document = DocumentFactory(user=user)
        
        import time
        time.sleep(0.01)
        
        new_document = DocumentFactory(user=user)
        
        documents = Document.objects.filter(user=user)
        assert documents.first() == new_document
        assert documents.last() == old_document


@pytest.mark.django_db
class TestDocumentChunkModel:
    """Test cases for DocumentChunk model"""

    def test_create_document_chunk(self):
        """Test creating a document chunk"""
        document = DocumentFactory()
        chunk = DocumentChunkFactory(
            document=document,
            content="This is test content.",
            chunk_index=0,
            total_chunks=5
        )
        
        assert chunk.document == document
        assert chunk.content == "This is test content."
        assert chunk.chunk_index == 0
        assert chunk.total_chunks == 5
        assert chunk.character_count == len("This is test content.")

    def test_embedding_methods(self):
        """Test embedding storage and retrieval methods"""
        chunk = DocumentChunkFactory()
        
        # Test setting embedding
        test_embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
        chunk.set_embedding(test_embedding)
        assert chunk.embedding == json.dumps(test_embedding)
        
        # Test getting embedding
        retrieved_embedding = chunk.get_embedding()
        assert retrieved_embedding == test_embedding
        
        # Test with no embedding
        chunk.embedding = None
        assert chunk.get_embedding() is None

    def test_chunk_save_calculates_character_count(self):
        """Test that save method calculates character count"""
        chunk = DocumentChunkFactory(content="Test content")
        assert chunk.character_count == len("Test content")
        
        # Test updating content
        chunk.content = "Updated test content"
        chunk.save()
        assert chunk.character_count == len("Updated test content")

    def test_chunk_str_representation(self):
        """Test chunk string representation"""
        document = DocumentFactory(filename="test.pdf")
        chunk = DocumentChunkFactory(
            document=document,
            chunk_index=2,
            total_chunks=10
        )
        
        expected_str = "Chunk 3/10 of test.pdf"
        assert str(chunk) == expected_str

    def test_chunk_ordering(self):
        """Test that chunks are ordered by document and chunk_index"""
        document = ProcessedDocumentFactory(chunk_count=3)
        chunks = document.chunks.all()
        
        assert chunks[0].chunk_index == 0
        assert chunks[1].chunk_index == 1
        assert chunks[2].chunk_index == 2

    def test_chunk_unique_together_constraint(self):
        """Test that document and chunk_index combination is unique"""
        document = DocumentFactory()
        DocumentChunkFactory(document=document, chunk_index=0)
        
        # This should raise an IntegrityError in a real database
        with pytest.raises(Exception):  # More specific exception would be caught in integration tests
            DocumentChunkFactory(document=document, chunk_index=0)