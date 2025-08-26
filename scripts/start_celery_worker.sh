#!/bin/bash
"""
Start Celery worker with autoscaling and monitoring.
"""

# Navigate to project directory
cd "$(dirname "$0")/.."

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Set environment variables
export DJANGO_SETTINGS_MODULE="config.settings.local"

# Default values - can be overridden with environment variables
CELERY_WORKER_CONCURRENCY=${CELERY_WORKER_CONCURRENCY:-}
CELERY_WORKER_AUTOSCALER=${CELERY_WORKER_AUTOSCALER:-"10,3"}
CELERY_WORKER_PREFETCH_MULTIPLIER=${CELERY_WORKER_PREFETCH_MULTIPLIER:-4}
CELERY_LOG_LEVEL=${CELERY_LOG_LEVEL:-"INFO"}

echo "🚀 Starting Celery Worker with Autoscaling"
echo "📊 Autoscaler: ${CELERY_WORKER_AUTOSCALER} (max,min)"
echo "📦 Prefetch: ${CELERY_WORKER_PREFETCH_MULTIPLIER}"
echo "📋 Log Level: ${CELERY_LOG_LEVEL}"

# Start celery worker with autoscaling
celery -A config.celery_app worker \
    --loglevel=${CELERY_LOG_LEVEL} \
    --autoscale=${CELERY_WORKER_AUTOSCALER} \
    --prefetch-multiplier=${CELERY_WORKER_PREFETCH_MULTIPLIER} \
    --max-tasks-per-child=${CELERY_WORKER_MAX_TASKS_PER_CHILD:-1000} \
    --max-memory-per-child=${CELERY_WORKER_MAX_MEMORY_PER_CHILD:-200000} \
    --queues=default,receipt_processing,chat_tasks,user_tasks,high_priority \
    --hostname=worker@%h \
    --time-limit=300 \
    --soft-time-limit=240