import factory
from django.contrib.auth import get_user_model
from agent_chat_app.chat.models import (
    Conversation,
    Message,
    Document,
    DocumentChunk,
    UserSettings
)

User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    """Factory for creating test users"""
    username = factory.Sequence(lambda n: f"testuser{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.com")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")

    class Meta:
        model = User
        django_get_or_create = ("username",)


class UserSettingsFactory(factory.django.DjangoModelFactory):
    """Factory for creating test user settings"""
    user = factory.SubFactory(UserFactory)
    preferred_model = "gemma2:9b"
    system_instruction = "You are a helpful AI assistant."
    max_tokens = 2048
    temperature = 0.7

    class Meta:
        model = UserSettings


class ConversationFactory(factory.django.DjangoModelFactory):
    """Factory for creating test conversations"""
    user = factory.SubFactory(UserFactory)
    title = factory.Faker("sentence", nb_words=4)
    message_count = 0

    class Meta:
        model = Conversation


class MessageFactory(factory.django.DjangoModelFactory):
    """Factory for creating test messages"""
    conversation = factory.SubFactory(ConversationFactory)
    text = factory.Faker("text", max_nb_chars=500)
    is_from_user = True
    token_count = factory.Faker("random_int", min=10, max=100)
    processing_time = factory.Faker("random_number", digits=1, fix_len=False)
    model_used = "gemma2:9b"

    class Meta:
        model = Message

    @factory.post_generation
    def update_conversation_count(self, create, extracted, **kwargs):
        """Update conversation message count after creating message"""
        if create:
            self.conversation.message_count = self.conversation.messages.count()
            self.conversation.save(update_fields=['message_count'])


class DocumentFactory(factory.django.DjangoModelFactory):
    """Factory for creating test documents"""
    user = factory.SubFactory(UserFactory)
    filename = factory.Faker("file_name", extension="pdf")
    file_type = "pdf"
    file_path = factory.LazyAttribute(lambda obj: f"/uploads/{obj.filename}")
    file_size = factory.Faker("random_int", min=1024, max=1024*1024*10)  # 1KB to 10MB
    processing_status = "completed"
    chunk_count = factory.Faker("random_int", min=1, max=50)

    class Meta:
        model = Document


class DocumentChunkFactory(factory.django.DjangoModelFactory):
    """Factory for creating test document chunks"""
    document = factory.SubFactory(DocumentFactory)
    content = factory.Faker("text", max_nb_chars=1000)
    chunk_index = factory.Sequence(lambda n: n)
    total_chunks = 10
    character_count = factory.LazyAttribute(lambda obj: len(obj.content))

    class Meta:
        model = DocumentChunk


# Specialized factories for common test scenarios

class ConversationWithMessagesFactory(ConversationFactory):
    """Factory that creates a conversation with several messages"""
    
    @factory.post_generation
    def messages(self, create, extracted, **kwargs):
        if not create:
            return

        if extracted:
            # If specific messages were passed, create them
            for message_data in extracted:
                MessageFactory(conversation=self, **message_data)
        else:
            # Create default conversation flow
            MessageFactory(
                conversation=self,
                text="Hello, I need help with something.",
                is_from_user=True
            )
            MessageFactory(
                conversation=self,
                text="Of course! I'd be happy to help. What do you need assistance with?",
                is_from_user=False,
                model_used="gemma2:9b"
            )
            MessageFactory(
                conversation=self,
                text="Can you explain how Django models work?",
                is_from_user=True
            )


class ProcessedDocumentFactory(DocumentFactory):
    """Factory for fully processed documents with chunks"""
    processing_status = "completed"
    chunk_count = 5

    @factory.post_generation
    def chunks(self, create, extracted, **kwargs):
        if not create:
            return

        chunk_count = extracted or self.chunk_count
        for i in range(chunk_count):
            DocumentChunkFactory(
                document=self,
                chunk_index=i,
                total_chunks=chunk_count
            )


class FailedDocumentFactory(DocumentFactory):
    """Factory for failed document processing"""
    processing_status = "failed"
    processing_error = "Failed to extract text from document"
    chunk_count = 0