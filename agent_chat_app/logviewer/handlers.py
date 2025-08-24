import logging
import json
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.utils import timezone


class DatabaseLogHandler(logging.Handler):
    """
    Custom logging handler that saves log records to database
    and broadcasts to WebSocket clients.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.channel_layer = get_channel_layer()

    def emit(self, record):
        try:
            # Create log entry in database
            log_entry = self._create_log_entry(record)
            
            # Broadcast to WebSocket clients if channel layer is available
            if self.channel_layer:
                self._broadcast_log_entry(log_entry)
                
        except Exception as e:
            # Don't let logging errors break the application
            self.handleError(record)

    def _create_log_entry(self, record):
        """Create a LogEntry from a LogRecord"""
        # Import here to avoid circular dependency
        from agent_chat_app.logviewer.models import LogEntry, LogLevel
        
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

    def _broadcast_log_entry(self, log_entry):
        """Broadcast log entry to WebSocket clients"""
        try:
            # Import here to avoid circular dependency
            from agent_chat_app.logviewer.api.serializers import LogEntryListSerializer
            
            # Serialize log entry
            serializer = LogEntryListSerializer(log_entry)
            
            # Send to WebSocket group
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