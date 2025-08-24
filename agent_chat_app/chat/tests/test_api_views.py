import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
import json

from agent_chat_app.chat.models import Conversation, Message, Document
from .factories import (
    UserFactory,
    ConversationFactory,
    MessageFactory,
    DocumentFactory,
    UserSettingsFactory,
    ConversationWithMessagesFactory,
    ProcessedDocumentFactory
)

User = get_user_model()


@pytest.fixture
def api_client():
    """Fixture providing API client"""
    return APIClient()


@pytest.fixture
def authenticated_client(api_client):
    """Fixture providing authenticated API client"""
    user = UserFactory()
    api_client.force_authenticate(user=user)
    api_client.user = user  # Store user for easy access in tests
    return api_client


@pytest.mark.django_db
class TestConversationAPI:
    """Test cases for Conversation API endpoints"""

    def test_list_conversations(self, authenticated_client):
        """Test listing conversations for authenticated user"""
        user = authenticated_client.user
        
        # Create conversations for the user
        ConversationFactory.create_batch(3, user=user)
        # Create conversations for another user (should not appear)
        ConversationFactory.create_batch(2, user=UserFactory())
        
        url = reverse('api:conversation-list')
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 3

    def test_create_conversation(self, authenticated_client):
        """Test creating a new conversation"""
        url = reverse('api:conversation-list')
        data = {
            'title': 'New Test Conversation',
            'initial_message': 'Hello, this is my first message'
        }
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['title'] == 'New Test Conversation'
        
        # Check that conversation was created in database
        conversation = Conversation.objects.get(id=response.data['id'])
        assert conversation.user == authenticated_client.user
        assert conversation.messages.count() == 1
        assert conversation.messages.first().text == 'Hello, this is my first message'

    def test_create_conversation_without_initial_message(self, authenticated_client):
        """Test creating a conversation without initial message"""
        url = reverse('api:conversation-list')
        data = {'title': 'Empty Conversation'}
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_201_CREATED
        conversation = Conversation.objects.get(id=response.data['id'])
        assert conversation.messages.count() == 0

    def test_retrieve_conversation(self, authenticated_client):
        """Test retrieving a specific conversation"""
        user = authenticated_client.user
        conversation = ConversationWithMessagesFactory(user=user)
        
        url = reverse('api:conversation-detail', kwargs={'pk': conversation.pk})
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == conversation.id
        assert response.data['title'] == conversation.title
        assert 'messages' in response.data
        assert len(response.data['messages']) == conversation.messages.count()

    def test_update_conversation(self, authenticated_client):
        """Test updating a conversation"""
        user = authenticated_client.user
        conversation = ConversationFactory(user=user, title="Old Title")
        
        url = reverse('api:conversation-detail', kwargs={'pk': conversation.pk})
        data = {'title': 'Updated Title'}
        
        response = authenticated_client.patch(url, data, format='json')
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['title'] == 'Updated Title'
        
        conversation.refresh_from_db()
        assert conversation.title == 'Updated Title'

    def test_delete_conversation(self, authenticated_client):
        """Test deleting a conversation"""
        user = authenticated_client.user
        conversation = ConversationFactory(user=user)
        
        url = reverse('api:conversation-detail', kwargs={'pk': conversation.pk})
        response = authenticated_client.delete(url)
        
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Conversation.objects.filter(id=conversation.id).exists()

    def test_send_message_to_conversation(self, authenticated_client):
        """Test sending a message to a conversation"""
        user = authenticated_client.user
        conversation = ConversationFactory(user=user)
        
        url = reverse('api:conversation-send-message', kwargs={'pk': conversation.pk})
        data = {'text': 'This is a test message'}
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['text'] == 'This is a test message'
        assert response.data['is_from_user'] is True
        
        # Check message was created in database
        assert conversation.messages.count() == 1
        message = conversation.messages.first()
        assert message.text == 'This is a test message'

    def test_toggle_archive_conversation(self, authenticated_client):
        """Test toggling archive status of a conversation"""
        user = authenticated_client.user
        conversation = ConversationFactory(user=user, is_archived=False)
        
        url = reverse('api:conversation-toggle-archive', kwargs={'pk': conversation.pk})
        response = authenticated_client.post(url)
        
        assert response.status_code == status.HTTP_200_OK
        conversation.refresh_from_db()
        assert conversation.is_archived is True
        
        # Toggle back
        response = authenticated_client.post(url)
        assert response.status_code == status.HTTP_200_OK
        conversation.refresh_from_db()
        assert conversation.is_archived is False

    def test_conversation_stats(self, authenticated_client):
        """Test getting conversation statistics"""
        user = authenticated_client.user
        conversation = ConversationWithMessagesFactory(user=user)
        
        url = reverse('api:conversation-stats', kwargs={'pk': conversation.pk})
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert 'message_count' in response.data
        assert 'user_messages' in response.data
        assert 'ai_messages' in response.data
        assert 'total_characters' in response.data

    def test_unauthorized_access_denied(self, api_client):
        """Test that unauthenticated requests are denied"""
        url = reverse('api:conversation-list')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_access_other_user_conversation_denied(self, authenticated_client):
        """Test that users cannot access other users' conversations"""
        other_user = UserFactory()
        other_conversation = ConversationFactory(user=other_user)
        
        url = reverse('api:conversation-detail', kwargs={'pk': other_conversation.pk})
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestMessageAPI:
    """Test cases for Message API endpoints"""

    def test_list_messages(self, authenticated_client):
        """Test listing messages for user's conversations"""
        user = authenticated_client.user
        conversation = ConversationWithMessagesFactory(user=user)
        
        # Create messages for another user (should not appear)
        other_conversation = ConversationWithMessagesFactory(user=UserFactory())
        
        url = reverse('api:message-list')
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        # Should only see messages from user's conversations
        assert len(response.data['results']) == conversation.messages.count()

    def test_filter_messages_by_conversation(self, authenticated_client):
        """Test filtering messages by conversation ID"""
        user = authenticated_client.user
        conversation1 = ConversationWithMessagesFactory(user=user)
        conversation2 = ConversationWithMessagesFactory(user=user)
        
        url = reverse('api:message-list')
        response = authenticated_client.get(url, {'conversation_id': conversation1.id})
        
        assert response.status_code == status.HTTP_200_OK
        # Should only see messages from specified conversation
        for message_data in response.data['results']:
            assert message_data['conversation'] == conversation1.id

    def test_retrieve_message(self, authenticated_client):
        """Test retrieving a specific message"""
        user = authenticated_client.user
        conversation = ConversationFactory(user=user)
        message = MessageFactory(conversation=conversation)
        
        url = reverse('api:message-detail', kwargs={'pk': message.pk})
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == message.id
        assert response.data['text'] == message.text


@pytest.mark.django_db
class TestDocumentAPI:
    """Test cases for Document API endpoints"""

    def test_list_documents(self, authenticated_client):
        """Test listing documents for authenticated user"""
        user = authenticated_client.user
        
        # Create documents for the user
        DocumentFactory.create_batch(3, user=user)
        # Create documents for another user (should not appear)
        DocumentFactory.create_batch(2, user=UserFactory())
        
        url = reverse('api:document-list')
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 3

    def test_retrieve_document(self, authenticated_client):
        """Test retrieving a specific document"""
        user = authenticated_client.user
        document = ProcessedDocumentFactory(user=user)
        
        url = reverse('api:document-detail', kwargs={'pk': document.pk})
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == document.id
        assert response.data['filename'] == document.filename
        assert 'chunks' in response.data

    def test_delete_document(self, authenticated_client):
        """Test deleting a document"""
        user = authenticated_client.user
        document = DocumentFactory(user=user)
        
        url = reverse('api:document-detail', kwargs={'pk': document.pk})
        response = authenticated_client.delete(url)
        
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Document.objects.filter(id=document.id).exists()

    def test_reprocess_document(self, authenticated_client):
        """Test reprocessing a failed document"""
        user = authenticated_client.user
        document = DocumentFactory(user=user, processing_status='failed')
        
        url = reverse('api:document-reprocess', kwargs={'pk': document.pk})
        response = authenticated_client.post(url)
        
        assert response.status_code == status.HTTP_200_OK
        document.refresh_from_db()
        assert document.processing_status == 'pending'

    def test_reprocess_completed_document_fails(self, authenticated_client):
        """Test that reprocessing a completed document fails"""
        user = authenticated_client.user
        document = DocumentFactory(user=user, processing_status='completed')
        
        url = reverse('api:document-reprocess', kwargs={'pk': document.pk})
        response = authenticated_client.post(url)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'already processed' in response.data['error']


@pytest.mark.django_db
class TestUserSettingsAPI:
    """Test cases for UserSettings API endpoints"""

    def test_get_user_settings(self, authenticated_client):
        """Test retrieving user settings"""
        user = authenticated_client.user
        settings = UserSettingsFactory(user=user)
        
        url = reverse('api:usersettings-list')
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['preferred_model'] == settings.preferred_model
        assert response.data['max_tokens'] == settings.max_tokens

    def test_update_user_settings(self, authenticated_client):
        """Test updating user settings"""
        user = authenticated_client.user
        UserSettingsFactory(user=user)
        
        url = reverse('api:usersettings-list')  # Settings uses list URL for single object
        data = {
            'preferred_model': 'gpt-4',
            'temperature': 0.8,
            'max_tokens': 3000
        }
        
        response = authenticated_client.patch(url, data, format='json')
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['preferred_model'] == 'gpt-4'
        assert response.data['temperature'] == 0.8
        assert response.data['max_tokens'] == 3000

    def test_reset_user_settings(self, authenticated_client):
        """Test resetting user settings to defaults"""
        user = authenticated_client.user
        UserSettingsFactory(
            user=user,
            preferred_model='custom-model',
            temperature=1.5
        )
        
        url = reverse('api:usersettings-reset')
        response = authenticated_client.post(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['preferred_model'] == 'gemma3:4b'  # default
        assert response.data['temperature'] == 0.7  # default

    def test_settings_validation(self, authenticated_client):
        """Test user settings validation"""
        user = authenticated_client.user
        UserSettingsFactory(user=user)
        
        url = reverse('api:usersettings-list')
        
        # Test invalid temperature
        data = {'temperature': 3.0}
        response = authenticated_client.patch(url, data, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        
        # Test invalid max_tokens
        data = {'max_tokens': 50000}
        response = authenticated_client.patch(url, data, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestAPIAuthentication:
    """Test cases for API authentication and permissions"""

    def test_token_authentication(self, api_client):
        """Test authentication using token"""
        from rest_framework.authtoken.models import Token
        
        user = UserFactory()
        token = Token.objects.create(user=user)
        
        api_client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        
        url = reverse('api:conversation-list')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK

    def test_invalid_token_rejected(self, api_client):
        """Test that invalid tokens are rejected"""
        api_client.credentials(HTTP_AUTHORIZATION='Token invalid-token-123')
        
        url = reverse('api:conversation-list')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_missing_authentication_rejected(self, api_client):
        """Test that requests without authentication are rejected"""
        url = reverse('api:conversation-list')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestAPIFiltering:
    """Test cases for API filtering and search functionality"""

    def test_conversation_filtering(self, authenticated_client):
        """Test filtering conversations by various criteria"""
        user = authenticated_client.user
        
        # Create test data
        archived_conv = ConversationFactory(user=user, is_archived=True)
        active_conv = ConversationFactory(user=user, is_archived=False)
        
        url = reverse('api:conversation-list')
        
        # Test filtering by archive status
        response = authenticated_client.get(url, {'is_archived': 'true'})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1
        assert response.data['results'][0]['id'] == archived_conv.id

    def test_conversation_search(self, authenticated_client):
        """Test searching conversations by title"""
        user = authenticated_client.user
        
        ConversationFactory(user=user, title="Python Programming Help")
        ConversationFactory(user=user, title="Django Models Tutorial")
        ConversationFactory(user=user, title="JavaScript Basics")
        
        url = reverse('api:conversation-list')
        response = authenticated_client.get(url, {'search': 'Python'})
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1
        assert 'Python' in response.data['results'][0]['title']

    def test_document_filtering(self, authenticated_client):
        """Test filtering documents by file type"""
        user = authenticated_client.user
        
        DocumentFactory(user=user, file_type='pdf')
        DocumentFactory(user=user, file_type='txt')
        DocumentFactory(user=user, file_type='pdf')
        
        url = reverse('api:document-list')
        response = authenticated_client.get(url, {'file_type': 'pdf'})
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 2
        for doc in response.data['results']:
            assert doc['file_type'] == 'pdf'