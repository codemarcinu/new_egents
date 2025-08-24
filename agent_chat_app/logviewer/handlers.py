import logging
import json
import asyncio
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync, sync_to_async
from django.utils import timezone


class DatabaseLogHandler(logging.Handler):
    """
    Custom logging handler that saves log records to database
    and broadcasts to WebSocket clients.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.channel_layer = get_channel_layer()
        self._shutting_down = False

    def emit(self, record):
        # Skip processing if shutting down
        if self._shutting_down:
            return
            
        try:
            # Check if we're in an async context
            try:
                loop = asyncio.get_running_loop()
                # We're in an async context, schedule the async version
                asyncio.create_task(self._async_emit(record))
            except RuntimeError:
                # No event loop running, safe to use sync operations
                self._sync_emit(record)
                
        except Exception as e:
            # Don't let logging errors break the application
            # Only call handleError if we're not shutting down to prevent shutdown loops
            if not self._shutting_down:
                try:
                    self.handleError(record)
                except Exception:
                    # Ultimate fallback - just pass
                    pass
    
    def close(self):
        """Override close to mark as shutting down"""
        self._shutting_down = True
        super().close()
    
    def _sync_emit(self, record):
        """Synchronous version of emit"""
        if self._shutting_down:
            return
        try:
            # Create log entry in database
            log_entry = self._create_log_entry(record)
            
            # Broadcast to WebSocket clients if channel layer is available
            if log_entry and self.channel_layer and not self._shutting_down:
                self._broadcast_log_entry(log_entry)
        except Exception:
            pass
    
    async def _async_emit(self, record):
        """Asynchronous version of emit"""
        if self._shutting_down:
            return
        try:
            # Create log entry in database using sync_to_async
            log_entry = await self._async_create_log_entry(record)
            
            # Broadcast to WebSocket clients if channel layer is available
            if log_entry and self.channel_layer and not self._shutting_down:
                await self._async_broadcast_only(log_entry)
        except Exception:
            pass

    def _create_log_entry(self, record):
        """Create a LogEntry from a LogRecord"""
        if self._shutting_down:
            return None
            
        try:
            # Import here to avoid circular dependency
            from agent_chat_app.logviewer.models import LogEntry, LogLevel
        except ImportError:
            # Module might be unloaded during shutdown
            return None
        
        # Normalize log level
        level = record.levelname.upper()
        if level not in [choice[0] for choice in LogLevel.choices]:
            if level in ['WARN']:
                level = 'WARNING'
            elif level in ['FATAL']:
                level = 'CRITICAL'
            else:
                level = 'INFO'

        # Extract metadata
        metadata = {}
        if hasattr(record, 'pathname'):
            metadata['pathname'] = record.pathname
        if hasattr(record, 'lineno'):
            metadata['lineno'] = record.lineno
        if hasattr(record, 'funcName'):
            metadata['funcName'] = record.funcName
        if hasattr(record, 'exc_info') and record.exc_info:
            metadata['exception'] = self.format(record)

        # Create log entry
        try:
            log_entry = LogEntry.objects.create(
                timestamp=timezone.make_aware(timezone.datetime.fromtimestamp(record.created)),
                level=level,
                logger_name=record.name,
                message=record.getMessage()[:5000],  # Truncate very long messages
                module=getattr(record, 'module', record.name.split('.')[-1])[:200],
                function=getattr(record, 'funcName', '')[:200],
                line_number=getattr(record, 'lineno', None),
                process_id=getattr(record, 'process', None),
                thread_id=getattr(record, 'thread', None),
                metadata=metadata
            )
            return log_entry
        except Exception:
            # Database might be unavailable during shutdown
            return None

    async def _async_create_log_entry(self, record):
        """Async version of _create_log_entry using sync_to_async"""
        return await sync_to_async(self._create_log_entry)(record)

    def _broadcast_log_entry(self, log_entry):
        """Broadcast log entry to WebSocket clients"""
        try:
            # Import here to avoid circular dependency
            from agent_chat_app.logviewer.api.serializers import LogEntryListSerializer
            
            # Serialize log entry
            serializer = LogEntryListSerializer(log_entry)
            
            # Check if we're in an async context
            try:
                loop = asyncio.get_running_loop()
                # We're in an async context, create a task instead
                asyncio.create_task(self._async_broadcast(log_entry, serializer.data))
            except RuntimeError:
                # No event loop running, safe to use async_to_sync
                async_to_sync(self.channel_layer.group_send)(
                    'log_stream',
                    {
                        'type': 'log_entry',
                        'log': serializer.data
                    }
                )
        except Exception:
            # Silently fail to prevent logging loops
            pass
    
    async def _async_broadcast(self, log_entry, serialized_data):
        """Async helper for broadcasting when already in async context"""
        try:
            await self.channel_layer.group_send(
                'log_stream',
                {
                    'type': 'log_entry',
                    'log': serialized_data
                }
            )
        except Exception:
            # Silently fail to prevent logging loops
            pass

    async def _async_broadcast_only(self, log_entry):
        """Async-only broadcast method for log entry"""
        try:
            # Import here to avoid circular dependency
            from agent_chat_app.logviewer.api.serializers import LogEntryListSerializer
            
            # Serialize log entry using sync_to_async
            serializer = LogEntryListSerializer(log_entry)
            
            await self.channel_layer.group_send(
                'log_stream',
                {
                    'type': 'log_entry',
                    'log': serializer.data
                }
            )
        except Exception:
            # Silently fail to prevent logging loops
            pass