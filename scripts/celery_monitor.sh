#!/bin/bash
"""
Celery monitoring and status script.
"""

# Navigate to project directory
cd "$(dirname "$0")/.."

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Set environment variables
export DJANGO_SETTINGS_MODULE="config.settings.local"

echo "🔍 Celery Monitoring Dashboard"
echo "=============================="

# Function to show worker status
show_worker_status() {
    echo ""
    echo "📊 Worker Status:"
    celery -A config.celery_app status
}

# Function to show active tasks
show_active_tasks() {
    echo ""
    echo "🔄 Active Tasks:"
    celery -A config.celery_app active
}

# Function to show queue inspection
show_queue_inspection() {
    echo ""
    echo "📋 Queue Inspection:"
    celery -A config.celery_app inspect active
    echo ""
    echo "🔢 Queue Lengths:"
    celery -A config.celery_app inspect reserved
}

# Function to show stats
show_stats() {
    echo ""
    echo "📈 Worker Statistics:"
    celery -A config.celery_app inspect stats
}

# Function to show registered tasks
show_registered_tasks() {
    echo ""
    echo "📝 Registered Tasks:"
    celery -A config.celery_app inspect registered
}

# Parse command line arguments
case "$1" in
    "status")
        show_worker_status
        ;;
    "active")
        show_active_tasks
        ;;
    "queues")
        show_queue_inspection
        ;;
    "stats")
        show_stats
        ;;
    "tasks")
        show_registered_tasks
        ;;
    "all"|"")
        show_worker_status
        show_active_tasks
        show_queue_inspection
        ;;
    "help"|"-h"|"--help")
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  status    - Show worker status"
        echo "  active    - Show active tasks"
        echo "  queues    - Show queue inspection"
        echo "  stats     - Show detailed statistics"
        echo "  tasks     - Show registered tasks"
        echo "  all       - Show status, active tasks, and queues (default)"
        echo "  help      - Show this help message"
        ;;
    *)
        echo "Unknown command: $1"
        echo "Use '$0 help' for available commands"
        exit 1
        ;;
esac