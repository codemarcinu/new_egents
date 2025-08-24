import pytest
from django.conf import settings
from django.test import override_settings
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.core.cache import cache

from .factories import UserFactory

User = get_user_model()


# Test database settings
@pytest.fixture(autouse=True, scope='session')
def test_settings():
    """Override settings for testing"""
    with override_settings(
        # Use in-memory database for faster tests
        DATABASES={
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': ':memory:',
            }
        },
        # Use dummy cache for tests
        CACHES={
            'default': {
                'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
            }
        },
        # Disable migrations for faster test setup
        MIGRATION_MODULES={
            'chat': None,
            'users': None,
            'receipts': None,
            'sites': None,
        },
        # Test-specific settings
        PASSWORD_HASHERS=[
            'django.contrib.auth.hashers.MD5PasswordHasher',  # Faster for tests
        ],
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        CELERY_TASK_ALWAYS_EAGER=True,  # Execute tasks synchronously in tests
        CELERY_TASK_EAGER_PROPAGATES=True,
        # Disable logging during tests
        LOGGING={
            'version': 1,
            'disable_existing_loggers': False,
            'handlers': {
                'console': {
                    'class': 'logging.NullHandler',
                },
            },
            'root': {
                'handlers': ['console'],
            },
            'loggers': {
                'django': {
                    'handlers': ['console'],
                    'propagate': False,
                },
                'agent_chat_app': {
                    'handlers': ['console'],
                    'propagate': False,
                },
            },
        },
    ):
        yield


@pytest.fixture
def api_client():
    """Provide a DRF API client"""
    return APIClient()


@pytest.fixture
def user():
    """Create a test user"""
    return UserFactory()


@pytest.fixture
def authenticated_client(api_client, user):
    """Provide an authenticated API client"""
    api_client.force_authenticate(user=user)
    api_client.user = user  # Store user reference for easy access
    return api_client


@pytest.fixture
def admin_user():
    """Create an admin test user"""
    return UserFactory(is_staff=True, is_superuser=True)


@pytest.fixture
def authenticated_admin_client(api_client, admin_user):
    """Provide an authenticated admin API client"""
    api_client.force_authenticate(user=admin_user)
    api_client.user = admin_user
    return api_client


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear cache before each test"""
    cache.clear()


@pytest.fixture
def mock_redis(monkeypatch):
    """Mock Redis for tests that don't need real Redis"""
    class MockRedis:
        def __init__(self, *args, **kwargs):
            self.data = {}
        
        def ping(self):
            return True
        
        def set(self, key, value, ex=None):
            self.data[key] = value
            
        def get(self, key):
            return self.data.get(key)
        
        def delete(self, key):
            self.data.pop(key, None)
        
        def info(self):
            return {
                'redis_version': '7.0.0',
                'used_memory_human': '1.00M',
                'connected_clients': 1,
            }
    
    import redis
    monkeypatch.setattr(redis, 'from_url', MockRedis)
    return MockRedis


@pytest.fixture
def sample_pdf_content():
    """Provide sample PDF content for document tests"""
    return b'%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000010 00000 n \n0000000053 00000 n \n0000000102 00000 n \ntrailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n161\n%%EOF'


@pytest.fixture
def sample_text_content():
    """Provide sample text content for document tests"""
    return "This is a sample text document.\n\nIt contains multiple paragraphs with various content.\n\nThis can be used for testing document processing and chunking functionality."


# Pytest Django configuration
@pytest.fixture(scope='session')
def django_db_setup():
    """Override Django DB setup for tests"""
    pass


# Custom markers
def pytest_configure(config):
    """Configure custom pytest markers"""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests (deselect with '-m \"not integration\"')"
    )
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "external: marks tests that require external services"
    )


# Pytest collection configuration
def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers based on test names"""
    for item in items:
        # Mark integration tests
        if "integration" in item.name.lower() or "integration" in str(item.fspath).lower():
            item.add_marker(pytest.mark.integration)
        
        # Mark slow tests
        if "slow" in item.name.lower() or any(keyword in item.name.lower() for keyword in ['large', 'bulk', 'stress']):
            item.add_marker(pytest.mark.slow)
        
        # Mark external service tests
        if any(keyword in item.name.lower() for keyword in ['redis', 'database', 'external']):
            item.add_marker(pytest.mark.external)