import csv
import json
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.db import models
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter

from agent_chat_app.logviewer.models import LogEntry
from agent_chat_app.logviewer.api.serializers import LogEntrySerializer, LogEntryListSerializer
from agent_chat_app.logviewer.api.filters import LogEntryFilter


class LogViewerRateThrottle(UserRateThrottle):
    """Custom throttle for log viewer API"""
    scope = 'logs'


class LogEntryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing log entries.
    
    Supports filtering by:
    - level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    - logger_name: Logger name (case-insensitive contains)
    - message: Message content (case-insensitive contains)
    - search: Search across message, logger_name, module, and function
    - date_from: Filter logs from this date
    - date_to: Filter logs until this date
    - last_hour: Show only logs from last hour
    - last_day: Show only logs from last day
    - last_week: Show only logs from last week
    """
    
    queryset = LogEntry.objects.all()
    serializer_class = LogEntrySerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    throttle_classes = [LogViewerRateThrottle]
    
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = LogEntryFilter
    ordering_fields = ['timestamp', 'level', 'logger_name']
    ordering = ['-timestamp']

    def get_serializer_class(self):
        """Use optimized serializer for list view"""
        if self.action == 'list':
            return LogEntryListSerializer
        return LogEntrySerializer

    @action(detail=False, methods=['get'])
    def export_csv(self, request):
        """Export filtered logs as CSV"""
        # Apply the same filters as list view
        queryset = self.filter_queryset(self.get_queryset())
        
        # Limit export to prevent abuse
        queryset = queryset[:10000]
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="logs_export_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'ID', 'Timestamp', 'Level', 'Logger Name', 'Message', 'Module', 
            'Function', 'Line Number', 'Process ID', 'Thread ID'
        ])
        
        for log in queryset:
            writer.writerow([
                log.id,
                log.timestamp.isoformat(),
                log.level,
                log.logger_name,
                log.message,
                log.module,
                log.function,
                log.line_number,
                log.process_id,
                log.thread_id,
            ])
        
        return response

    @action(detail=False, methods=['get'])
    def export_json(self, request):
        """Export filtered logs as JSON"""
        # Apply the same filters as list view
        queryset = self.filter_queryset(self.get_queryset())
        
        # Limit export to prevent abuse
        queryset = queryset[:10000]
        
        serializer = LogEntrySerializer(queryset, many=True)
        
        response = HttpResponse(
            json.dumps(serializer.data, indent=2, default=str),
            content_type='application/json'
        )
        response['Content-Disposition'] = f'attachment; filename="logs_export_{timezone.now().strftime("%Y%m%d_%H%M%S")}.json"'
        
        return response

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get log statistics"""
        queryset = self.filter_queryset(self.get_queryset())
        
        # Count by level
        from agent_chat_app.logviewer.models import LogLevel
        level_stats = {}
        for level, _ in LogLevel.choices:
            level_stats[level] = queryset.filter(level=level).count()
        
        # Count by logger
        logger_stats = (
            queryset.values('logger_name')
            .annotate(count=models.Count('id'))
            .order_by('-count')[:10]
        )
        
        return Response({
            'total_logs': queryset.count(),
            'level_stats': level_stats,
            'top_loggers': list(logger_stats),
        })