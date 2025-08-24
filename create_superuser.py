#!/usr/bin/env python
import os
import sys
import django

# Add the project directory to the path
sys.path.append('/home/marcin/agent_chat_app')

# Set the Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')

# Setup Django
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

# Create superuser if it doesn't exist
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
    print("Superuser 'admin' created successfully!")
else:
    print("Superuser 'admin' already exists.")