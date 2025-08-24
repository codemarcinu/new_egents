import json
from django.db import models
from django.utils import timezone


class LogLevel(models.TextChoices):
    DEBUG = 'DEBUG', 'Debug'
    INFO = 'INFO', 'Info'
    WARNING = 'WARNING', 'Warning'
    ERROR = 'ERROR', 'Error'
    CRITICAL = 'CRITICAL', 'Critical'


class LogEntry(models.Model):
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    level = models.CharField(
        max_length=20,
        choices=LogLevel.choices,
        default=LogLevel.INFO,
        db_index=True
    )
    logger_name = models.CharField(max_length=200, db_index=True)
    message = models.TextField()
    module = models.CharField(max_length=200, blank=True)
    function = models.CharField(max_length=200, blank=True)
    line_number = models.PositiveIntegerField(null=True, blank=True)
    process_id = models.PositiveIntegerField(null=True, blank=True)
    thread_id = models.BigIntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['-timestamp', 'level']),
            models.Index(fields=['logger_name', '-timestamp']),
        ]

    def __str__(self):
        return f"{self.timestamp} - {self.level} - {self.logger_name}: {self.message[:100]}"

    @property
    def formatted_metadata(self):
        """Return formatted JSON metadata for display"""
        if self.metadata:
            return json.dumps(self.metadata, indent=2)
        return "{}"
