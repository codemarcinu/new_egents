import django_filters
from django.utils import timezone
from django.db import models
from datetime import timedelta
from agent_chat_app.logviewer.models import LogEntry, LogLevel


class LogEntryFilter(django_filters.FilterSet):
    level = django_filters.ChoiceFilter(choices=LogLevel.choices)
    logger_name = django_filters.CharFilter(lookup_expr='icontains')
    message = django_filters.CharFilter(lookup_expr='icontains')
    search = django_filters.CharFilter(method='filter_search')
    
    # Date range filters
    date_from = django_filters.DateTimeFilter(field_name='timestamp', lookup_expr='gte')
    date_to = django_filters.DateTimeFilter(field_name='timestamp', lookup_expr='lte')
    
    # Quick date filters
    last_hour = django_filters.BooleanFilter(method='filter_last_hour')
    last_day = django_filters.BooleanFilter(method='filter_last_day')
    last_week = django_filters.BooleanFilter(method='filter_last_week')

    class Meta:
        model = LogEntry
        fields = ['level', 'logger_name', 'message', 'search', 'date_from', 'date_to']

    def filter_search(self, queryset, name, value):
        """Search across multiple fields"""
        if value:
            return queryset.filter(
                models.Q(message__icontains=value) |
                models.Q(logger_name__icontains=value) |
                models.Q(module__icontains=value) |
                models.Q(function__icontains=value)
            )
        return queryset

    def filter_last_hour(self, queryset, name, value):
        if value:
            return queryset.filter(timestamp__gte=timezone.now() - timedelta(hours=1))
        return queryset

    def filter_last_day(self, queryset, name, value):
        if value:
            return queryset.filter(timestamp__gte=timezone.now() - timedelta(days=1))
        return queryset

    def filter_last_week(self, queryset, name, value):
        if value:
            return queryset.filter(timestamp__gte=timezone.now() - timedelta(weeks=1))
        return queryset