from rest_framework import serializers
from agent_chat_app.logviewer.models import LogEntry, LogLevel


class LogEntrySerializer(serializers.ModelSerializer):
    formatted_metadata = serializers.ReadOnlyField()

    class Meta:
        model = LogEntry
        fields = [
            'id', 'timestamp', 'level', 'logger_name', 'message', 'module',
            'function', 'line_number', 'process_id', 'thread_id', 'metadata',
            'formatted_metadata', 'created_at'
        ]
        read_only_fields = ['id', 'created_at', 'formatted_metadata']


class LogEntryListSerializer(serializers.ModelSerializer):
    """Optimized serializer for list view with fewer fields"""
    
    class Meta:
        model = LogEntry
        fields = ['id', 'timestamp', 'level', 'logger_name', 'message', 'module']
        read_only_fields = fields