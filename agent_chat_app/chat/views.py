from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.core.files.storage import default_storage
from django.conf import settings
from django.http import JsonResponse
from django.core.cache import cache
import os
from .models import Conversation, Message, Document, UserSettings
from .services import OllamaService
from .forms import DocumentUploadForm, UserSettingsForm
from .document_processor import DocumentProcessor
from .rag_service import RAGService
from .tasks import process_document_task, delete_document_task


class ChatView(LoginRequiredMixin, View):
    template_name = 'chat/chat_interface.html'
    
    def _get_cached_models(self):
        """Cache available models for 5 minutes to avoid repeated API calls"""
        cache_key = 'ollama_available_models'
        models = cache.get(cache_key)
        
        if models is None:
            models = OllamaService.get_available_models()
            cache.set(cache_key, models, 300)  # 5 minutes
        
        return models

    def get(self, request, conversation_id=None, redirect_to_latest=False):
        # Handle redirect to latest conversation
        if redirect_to_latest:
            latest_conversation = Conversation.objects.filter(user=request.user).order_by('-created_at').first()
            if latest_conversation:
                return redirect('chat:chat_view', conversation_id=latest_conversation.id)
            else:
                conversation = Conversation.objects.create(user=request.user)
                return redirect('chat:chat_view', conversation_id=conversation.id)
        
        if conversation_id:
            try:
                conversation = get_object_or_404(Conversation, id=conversation_id, user=request.user)
            except:
                # Jeśli konwersacja nie istnieje, przekieruj na najnowszą lub stwórz nową
                latest_conversation = Conversation.objects.filter(user=request.user).order_by('-created_at').first()
                if latest_conversation:
                    messages.info(request, f'Conversation {conversation_id} not found. Redirected to latest conversation.')
                    return redirect('chat:chat_view', conversation_id=latest_conversation.id)
                else:
                    conversation = Conversation.objects.create(user=request.user)
                    return redirect('chat:chat_view', conversation_id=conversation.id)
        else:
            # Stwórz nową konwersację jeśli brak aktywnej
            conversation = Conversation.objects.create(user=request.user)
            return redirect('chat:chat_view', conversation_id=conversation.id)

        # Optymalizacja: pobierz tylko potrzebne pola
        conversations = Conversation.objects.filter(user=request.user).only('id', 'title', 'created_at').order_by('-created_at')
        
        # Get user settings and available models
        user_settings, _ = UserSettings.objects.get_or_create(user=request.user)
        available_models = self._get_cached_models()
        
        return render(request, self.template_name, {
            'conversation': conversation,
            'conversations': conversations,
            'user_settings': user_settings,
            'available_models': available_models
        })

    def post(self, request, conversation_id):
        conversation = get_object_or_404(Conversation, id=conversation_id, user=request.user)
        user_message_text = request.POST.get('message', '')

        if user_message_text:
            # Get optional overrides from the form
            selected_model = request.POST.get('selected_model', '')
            temp_instruction = request.POST.get('temp_instruction', '')
            
            # Zapisz wiadomość użytkownika
            Message.objects.create(conversation=conversation, text=user_message_text, is_from_user=True)
            
            # Pobierz odpowiedź z Ollama (z RAG i opcjonalnymi ustawieniami)
            ai_response_text = OllamaService.get_response(
                user_message_text, 
                model=selected_model if selected_model else None,
                user_id=request.user.id,
                custom_instruction=temp_instruction if temp_instruction else None
            )
            
            # Zapisz odpowiedź AI
            Message.objects.create(conversation=conversation, text=ai_response_text, is_from_user=False)

        return redirect('chat:chat_view', conversation_id=conversation.id)


class DocumentUploadView(LoginRequiredMixin, View):
    """Handle document uploads for RAG"""
    template_name = 'chat/document_upload.html'
    
    def get(self, request):
        form = DocumentUploadForm()
        documents = Document.objects.filter(user=request.user).order_by('-uploaded_at')
        
        # Get RAG stats
        try:
            rag_service = RAGService()
            stats = rag_service.get_document_stats(user_id=request.user.id)
        except Exception:
            stats = {'documents': 0, 'chunks': 0, 'chromadb_items': 0}
        
        return render(request, self.template_name, {
            'form': form,
            'documents': documents,
            'stats': stats
        })
    
    def post(self, request):
        form = DocumentUploadForm(request.POST, request.FILES)
        
        if form.is_valid():
            uploaded_file = form.cleaned_data['file']
            
            try:
                # Save file to media directory
                media_root = getattr(settings, 'MEDIA_ROOT', os.path.join(settings.BASE_DIR, 'media'))
                documents_dir = os.path.join(media_root, 'documents', str(request.user.id))
                os.makedirs(documents_dir, exist_ok=True)
                
                file_path = os.path.join(documents_dir, uploaded_file.name)
                with open(file_path, 'wb+') as destination:
                    for chunk in uploaded_file.chunks():
                        destination.write(chunk)
                
                # Create Document record
                document = Document.objects.create(
                    user=request.user,
                    filename=uploaded_file.name,
                    file_type=os.path.splitext(uploaded_file.name)[1].lower(),
                    file_path=file_path,
                    file_size=uploaded_file.size
                )
                
                # Process document asynchronously with Celery
                task = process_document_task.delay(document.id)
                
                messages.success(request, f'Document "{uploaded_file.name}" uploaded successfully! Processing in background...')
                messages.info(request, f'Task ID: {task.id} - You can check processing status on this page.')
                
            except Exception as e:
                messages.error(request, f'Error uploading document: {str(e)}')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, error)
        
        return redirect('chat:document_upload')


class DocumentDeleteView(LoginRequiredMixin, View):
    """Delete document and its chunks"""
    
    def post(self, request, document_id):
        try:
            document = get_object_or_404(Document, id=document_id, user=request.user)
            filename = document.filename
            file_path = document.file_path
            
            # Delete document record first
            document.delete()
            
            # Schedule asynchronous cleanup
            task = delete_document_task.delay(document_id, file_path)
            
            messages.success(request, f'Document "{filename}" deletion scheduled successfully!')
            messages.info(request, f'Cleanup task ID: {task.id}')
                
        except Exception as e:
            messages.error(request, f'Error: {str(e)}')
        
        return redirect('chat:document_upload')


class ConversationDeleteView(LoginRequiredMixin, View):
    """Delete conversation and its messages"""
    
    def post(self, request, conversation_id):
        try:
            conversation = get_object_or_404(Conversation, id=conversation_id, user=request.user)
            title = conversation.title or f"Conversation {conversation.id}"
            
            # Delete conversation (cascades to messages)
            conversation.delete()
            
            messages.success(request, f'Conversation "{title}" deleted successfully!')
            
            # Redirect to a new conversation or to the latest one
            latest_conversation = Conversation.objects.filter(user=request.user).order_by('-created_at').first()
            if latest_conversation:
                return redirect('chat:chat_view', conversation_id=latest_conversation.id)
            else:
                return redirect('chat:chat_start')
                
        except Exception as e:
            messages.error(request, f'Error deleting conversation: {str(e)}')
            return redirect('chat:chat_view', conversation_id=conversation_id)
    
    def delete(self, request, conversation_id):
        """Handle AJAX delete requests"""
        try:
            conversation = get_object_or_404(Conversation, id=conversation_id, user=request.user)
            title = conversation.title or f"Conversation {conversation.id}"
            conversation.delete()
            
            return JsonResponse({
                'success': True, 
                'message': f'Conversation "{title}" deleted successfully!'
            })
        except Exception as e:
            return JsonResponse({
                'success': False, 
                'message': f'Error deleting conversation: {str(e)}'
            }, status=400)


class UserSettingsView(LoginRequiredMixin, View):
    """User chat settings management"""
    template_name = 'chat/user_settings.html'
    
    def get(self, request):
        user_settings, created = UserSettings.objects.get_or_create(user=request.user)
        form = UserSettingsForm(instance=user_settings)
        
        # Get available models for display
        available_models = OllamaService.get_available_models()
        
        return render(request, self.template_name, {
            'form': form,
            'user_settings': user_settings,
            'available_models': available_models
        })
    
    def post(self, request):
        user_settings, created = UserSettings.objects.get_or_create(user=request.user)
        form = UserSettingsForm(request.POST, instance=user_settings)
        
        if form.is_valid():
            form.save()
            messages.success(request, 'Settings updated successfully!')
            return redirect('chat:user_settings')
        else:
            messages.error(request, 'Please correct the errors below.')
        
        available_models = OllamaService.get_available_models()
        return render(request, self.template_name, {
            'form': form,
            'user_settings': user_settings,
            'available_models': available_models
        })
