import re
import logging
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings

from agent_chat_app.logviewer.models import LogEntry, LogLevel


class Command(BaseCommand):
    help = 'Import logs from Django log file into database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--log-file',
            type=str,
            default=str(settings.BASE_DIR / 'logs' / 'django.log'),
            help='Path to log file (default: logs/django.log)'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing log entries before import'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Limit number of log entries to import'
        )

    def handle(self, *args, **options):
        log_file = Path(options['log_file'])
        
        if not log_file.exists():
            self.stdout.write(
                self.style.ERROR(f'Log file not found: {log_file}')
            )
            return

        if options['clear']:
            count = LogEntry.objects.count()
            LogEntry.objects.all().delete()
            self.stdout.write(
                self.style.SUCCESS(f'Cleared {count} existing log entries')
            )

        # Pattern to parse Django log format: 
        # LEVEL TIMESTAMP module process thread message
        log_pattern = re.compile(
            r'^(?P<level>\w+)\s+'
            r'(?P<timestamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3})\s+'
            r'(?P<module>\S+)\s+'
            r'(?P<process>\d+)\s+'
            r'(?P<thread>\d+)\s+'
            r'(?P<message>.*)$'
        )

        imported_count = 0
        error_count = 0
        limit = options['limit']

        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            current_entry = None
            
            for line_num, line in enumerate(f, 1):
                if limit and imported_count >= limit:
                    break
                    
                line = line.rstrip('\n')
                if not line:
                    continue

                # Try to match log entry pattern
                match = log_pattern.match(line)
                
                if match:
                    # Save previous entry if exists
                    if current_entry:
                        try:
                            self._save_log_entry(current_entry)
                            imported_count += 1
                            if imported_count % 100 == 0:
                                self.stdout.write(f'Imported {imported_count} entries...')
                        except Exception as e:
                            error_count += 1
                            if error_count <= 5:  # Only show first 5 errors
                                self.stdout.write(
                                    self.style.WARNING(f'Error saving entry: {e}')
                                )

                    # Start new entry
                    current_entry = {
                        'level': match.group('level'),
                        'timestamp': match.group('timestamp'),
                        'module': match.group('module'),
                        'process': int(match.group('process')),
                        'thread': int(match.group('thread')),
                        'message': match.group('message'),
                        'raw_line': line,
                        'line_number': line_num,
                    }
                else:
                    # This is a continuation of the previous log entry
                    if current_entry:
                        current_entry['message'] += '\n' + line

            # Save the last entry
            if current_entry:
                try:
                    self._save_log_entry(current_entry)
                    imported_count += 1
                except Exception as e:
                    error_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully imported {imported_count} log entries'
            )
        )
        
        if error_count > 0:
            self.stdout.write(
                self.style.WARNING(f'Encountered {error_count} errors')
            )

    def _save_log_entry(self, entry_data):
        """Save a log entry to database"""
        # Parse timestamp
        try:
            dt = datetime.strptime(entry_data['timestamp'], '%Y-%m-%d %H:%M:%S,%f')
            timestamp = timezone.make_aware(dt)
        except ValueError:
            # Fallback timestamp
            timestamp = timezone.now()

        # Normalize log level
        level = entry_data['level'].upper()
        if level not in [choice[0] for choice in LogLevel.choices]:
            if level in ['WARN']:
                level = 'WARNING'
            elif level in ['FATAL']:
                level = 'CRITICAL'
            else:
                level = 'INFO'  # Default fallback

        # Extract logger name from module if possible
        module = entry_data['module']
        logger_name = module.split('.')[-1] if module else 'django'

        # Create log entry
        LogEntry.objects.create(
            timestamp=timestamp,
            level=level,
            logger_name=logger_name,
            message=entry_data['message'][:5000],  # Truncate very long messages
            module=module[:200],
            process_id=entry_data['process'],
            thread_id=entry_data['thread'],
            metadata={
                'line_number': entry_data['line_number'],
                'raw_line': entry_data['raw_line'][:1000],  # Store truncated raw line
            }
        )