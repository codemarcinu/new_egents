import requests
import json
import logging
from .rag_service import RAGService
from .models import UserSettings

logger = logging.getLogger(__name__)

OLLAMA_API_URL = "http://localhost:11434/api/generate"
OLLAMA_MODELS_URL = "http://localhost:11434/api/tags"


class OllamaService:
    @staticmethod
    def get_available_models():
        """Get list of available Ollama models"""
        try:
            response = requests.get(OLLAMA_MODELS_URL, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            models = []
            for model in data.get('models', []):
                model_name = model.get('name', '')
                model_size = model.get('size', 0)
                models.append({
                    'name': model_name,
                    'display_name': model_name.replace(':', ' '),
                    'size': model_size,
                    'size_human': OllamaService._format_size(model_size)
                })
            
            return models
        except Exception as e:
            logger.error(f"Error fetching available models: {e}")
            # Return default models if API fails
            return [
                {'name': 'gemma3:4b', 'display_name': 'Gemma3 4B', 'size': 0, 'size_human': 'N/A'},
                {'name': 'gpt-oss:latest', 'display_name': 'GPT-OSS Latest', 'size': 0, 'size_human': 'N/A'},
            ]
    
    @staticmethod
    def _format_size(size_bytes):
        """Format size in bytes to human readable format"""
        if size_bytes == 0:
            return "N/A"
        
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} PB"
    
    @staticmethod
    def get_user_settings(user_id: int):
        """Get or create user settings"""
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user = User.objects.get(id=user_id)
            settings, created = UserSettings.objects.get_or_create(user=user)
            return settings
        except Exception as e:
            logger.error(f"Error getting user settings: {e}")
            return None
    
    @staticmethod
    def get_response(prompt: str, model: str = None, user_id: int = None, use_rag: bool = True, custom_instruction: str = None, conversation_id: int = None) -> str:
        """
        Komunikuje się z API Ollama i zwraca wygenerowaną odpowiedź jako string.
        Opcjonalnie używa RAG do wzbogacenia kontekstu i ustawień użytkownika.
        """
        try:
            # Get user settings if user_id provided
            user_settings = None
            if user_id:
                user_settings = OllamaService.get_user_settings(user_id)
            
            # Determine model to use
            final_model = model
            if not final_model and user_settings:
                final_model = user_settings.preferred_model
            if not final_model:
                final_model = "gemma3:4b"
            
            # Prepare system instruction
            system_instruction = custom_instruction
            if not system_instruction and user_settings:
                system_instruction = user_settings.system_instruction
            if not system_instruction:
                system_instruction = "You are a helpful AI assistant. Be concise and accurate in your responses."
            
            # Prepare prompt with RAG context if enabled and user provided
            final_prompt = prompt
            if use_rag and user_id:
                try:
                    rag_service = RAGService()
                    rag_context = rag_service.generate_rag_context(prompt, user_id=user_id)
                    if rag_context:
                        final_prompt = f"{rag_context}\n\nUser question: {prompt}"
                        logger.info(f"Enhanced prompt with RAG context for user {user_id}")
                except Exception as e:
                    logger.warning(f"Failed to generate RAG context: {e}")
                    # Continue with original prompt if RAG fails
            
            # Get conversation context if provided
            context_messages = []
            if conversation_id:
                context_messages = OllamaService.get_conversation_context(conversation_id)
            
            # Build context-aware prompt
            if context_messages:
                context_str = "\n".join(context_messages[-10:])  # Last 10 messages for context
                full_prompt = f"{system_instruction}\n\nConversation context:\n{context_str}\n\nUser: {final_prompt}\nAssistant:"
            else:
                full_prompt = f"{system_instruction}\n\nUser: {final_prompt}\nAssistant:"
            
            # Optimize context window
            full_prompt = OllamaService.optimize_context_window(full_prompt, user_settings)
            
            # Prepare payload with user settings
            payload = {
                "model": final_model,
                "prompt": full_prompt,
                "stream": False
            }
            
            # Add optional parameters if user settings available
            if user_settings:
                if user_settings.temperature:
                    payload["options"] = payload.get("options", {})
                    payload["options"]["temperature"] = user_settings.temperature
                if user_settings.max_tokens:
                    payload["options"] = payload.get("options", {})
                    payload["options"]["num_predict"] = user_settings.max_tokens
            
            response = requests.post(OLLAMA_API_URL, json=payload, timeout=90)
            response.raise_for_status()

            response_data = response.json()
            
            return response_data.get("response", "Error: No response field in Ollama output.")

        except requests.exceptions.RequestException as e:
            logger.error(f"Błąd połączenia z Ollama: {e}")
            return "Przepraszam, mam problem z połączeniem z modelem językowym."
        except json.JSONDecodeError as e:
            logger.error(f"Błąd parsowania odpowiedzi od Ollama: {e}")
            return "Przepraszam, otrzymałem nieprawidłową odpowiedź od modelu."
    
    @staticmethod
    def get_conversation_context(conversation_id: int, max_messages: int = 10) -> list:
        """Get recent messages from conversation for context"""
        try:
            from .models import Conversation, Message
            conversation = Conversation.objects.get(id=conversation_id)
            
            recent_messages = Message.objects.filter(
                conversation=conversation
            ).order_by('-created_at')[:max_messages]
            
            context_messages = []
            for msg in reversed(recent_messages):  # Chronological order
                role = "User" if msg.is_from_user else "Assistant"
                context_messages.append(f"{role}: {msg.text}")
            
            return context_messages
        except Exception as e:
            logger.error(f"Error getting conversation context: {e}")
            return []
    
    @staticmethod
    def optimize_context_window(prompt: str, user_settings=None, max_tokens: int = None) -> str:
        """Optimize prompt to fit within context window limits"""
        try:
            # Determine max tokens
            if max_tokens is None:
                max_tokens = user_settings.max_tokens if user_settings else 2048
            
            # Rough estimation: 1 token ≈ 4 characters
            max_chars = max_tokens * 3  # Leave room for response
            
            if len(prompt) <= max_chars:
                return prompt
            
            # If too long, prioritize recent context and current query
            lines = prompt.split('\n')
            system_instruction = []
            context_lines = []
            current_query = []
            
            in_context = False
            for line in lines:
                if "Conversation context:" in line:
                    in_context = True
                    continue
                elif "User:" in line and in_context:
                    in_context = False
                    current_query.append(line)
                elif in_context:
                    context_lines.append(line)
                elif not in_context and not current_query:
                    system_instruction.append(line)
                else:
                    current_query.append(line)
            
            # Rebuild with truncated context if necessary
            system_part = '\n'.join(system_instruction)
            query_part = '\n'.join(current_query)
            
            remaining_chars = max_chars - len(system_part) - len(query_part) - 50  # Buffer
            
            if remaining_chars > 100 and context_lines:
                # Keep most recent context that fits
                context_str = ''
                for line in reversed(context_lines):
                    test_str = line + '\n' + context_str
                    if len(test_str) <= remaining_chars:
                        context_str = test_str
                    else:
                        break
                
                if context_str:
                    return f"{system_part}\n\nConversation context:\n{context_str.strip()}\n\n{query_part}"
            
            return f"{system_part}\n\n{query_part}"
            
        except Exception as e:
            logger.error(f"Error optimizing context window: {e}")
            return prompt  # Return original on error