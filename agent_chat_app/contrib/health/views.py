import logging
import time
from django.http import JsonResponse
from django.db import connection
from django.conf import settings
from django.core.cache import cache
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
import redis

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["GET"])
def health_check(request):
    """
    System health check endpoint for load balancers and monitoring systems.
    Returns HTTP 200 for healthy systems, HTTP 503 for unhealthy systems.
    """
    start_time = time.time()
    health_data = {
        'status': 'healthy',
        'timestamp': time.time(),
        'version': '1.0.0',
        'checks': {}
    }
    
    overall_healthy = True
    
    # Database health check
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        health_data['checks']['database'] = {
            'status': 'healthy',
            'message': 'Database connection successful'
        }
        logger.debug("Database health check passed")
    except Exception as e:
        health_data['checks']['database'] = {
            'status': 'unhealthy',
            'message': f'Database connection failed: {str(e)}'
        }
        overall_healthy = False
        logger.error(f"Database health check failed: {e}")
    
    # Redis health check
    try:
        r = redis.from_url(settings.REDIS_URL)
        r.ping()
        health_data['checks']['redis'] = {
            'status': 'healthy',
            'message': 'Redis connection successful'
        }
        logger.debug("Redis health check passed")
    except Exception as e:
        health_data['checks']['redis'] = {
            'status': 'unhealthy',
            'message': f'Redis connection failed: {str(e)}'
        }
        overall_healthy = False
        logger.error(f"Redis health check failed: {e}")
    
    # Cache health check
    try:
        test_key = 'health_check_test'
        test_value = 'test_value'
        cache.set(test_key, test_value, timeout=10)
        retrieved_value = cache.get(test_key)
        
        if retrieved_value == test_value:
            health_data['checks']['cache'] = {
                'status': 'healthy',
                'message': 'Cache operations successful'
            }
            cache.delete(test_key)
        else:
            raise Exception("Cache retrieve test failed")
        
        logger.debug("Cache health check passed")
    except Exception as e:
        health_data['checks']['cache'] = {
            'status': 'unhealthy',
            'message': f'Cache operations failed: {str(e)}'
        }
        overall_healthy = False
        logger.error(f"Cache health check failed: {e}")
    
    # Calculate response time
    response_time = (time.time() - start_time) * 1000  # Convert to ms
    health_data['response_time_ms'] = round(response_time, 2)
    
    # Set overall status
    health_data['status'] = 'healthy' if overall_healthy else 'unhealthy'
    
    # Return appropriate HTTP status code
    status_code = 200 if overall_healthy else 503
    
    return JsonResponse(health_data, status=status_code)


@api_view(['GET'])
@permission_classes([AllowAny])
@extend_schema(
    description="Basic readiness probe for Kubernetes deployments",
    tags=['Health']
)
def readiness_probe(request):
    """
    Readiness probe endpoint for Kubernetes.
    Checks if the application is ready to accept traffic.
    """
    try:
        # Quick database check
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        
        return Response({
            'status': 'ready',
            'timestamp': time.time()
        }, status=200)
    except Exception as e:
        logger.error(f"Readiness probe failed: {e}")
        return Response({
            'status': 'not_ready',
            'error': str(e),
            'timestamp': time.time()
        }, status=503)


@api_view(['GET'])
@permission_classes([AllowAny])
@extend_schema(
    description="Basic liveness probe for Kubernetes deployments",
    tags=['Health']
)
def liveness_probe(request):
    """
    Liveness probe endpoint for Kubernetes.
    Simple endpoint to check if the application is alive.
    """
    return Response({
        'status': 'alive',
        'timestamp': time.time()
    }, status=200)


@api_view(['GET'])
@permission_classes([AllowAny])
@extend_schema(
    description="Detailed system status including component health",
    tags=['Health']
)
def system_status(request):
    """
    Detailed system status endpoint for monitoring dashboards.
    Provides comprehensive health information about all system components.
    """
    start_time = time.time()
    
    status_data = {
        'application': {
            'name': 'Agent Chat App',
            'version': '1.0.0',
            'environment': settings.DEBUG and 'development' or 'production',
            'debug_mode': settings.DEBUG,
        },
        'system': {
            'timestamp': time.time(),
            'uptime_seconds': time.time() - start_time,  # This would be actual uptime in production
        },
        'components': {}
    }
    
    # Database status with connection info
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT version()")
            db_version = cursor.fetchone()[0] if hasattr(connection.vendor, 'cursor') else 'Unknown'
        
        status_data['components']['database'] = {
            'status': 'healthy',
            'vendor': connection.vendor,
            'version': db_version if 'db_version' in locals() else 'Unknown',
            'connection_count': len(connection.queries) if settings.DEBUG else 'N/A'
        }
    except Exception as e:
        status_data['components']['database'] = {
            'status': 'unhealthy',
            'error': str(e)
        }
    
    # Redis status with info
    try:
        r = redis.from_url(settings.REDIS_URL)
        redis_info = r.info()
        
        status_data['components']['redis'] = {
            'status': 'healthy',
            'version': redis_info.get('redis_version', 'Unknown'),
            'used_memory_human': redis_info.get('used_memory_human', 'Unknown'),
            'connected_clients': redis_info.get('connected_clients', 0),
        }
    except Exception as e:
        status_data['components']['redis'] = {
            'status': 'unhealthy',
            'error': str(e)
        }
    
    # Cache status
    try:
        cache_backend = cache._cache.__class__.__name__
        status_data['components']['cache'] = {
            'status': 'healthy',
            'backend': cache_backend,
        }
        
        # Test cache operations
        test_key = 'system_status_test'
        cache.set(test_key, 'test', timeout=5)
        cache.get(test_key)
        cache.delete(test_key)
        
    except Exception as e:
        status_data['components']['cache'] = {
            'status': 'unhealthy',
            'error': str(e)
        }
    
    # Calculate overall health
    healthy_components = [
        comp for comp in status_data['components'].values()
        if comp.get('status') == 'healthy'
    ]
    total_components = len(status_data['components'])
    
    status_data['overall'] = {
        'status': 'healthy' if len(healthy_components) == total_components else 'degraded',
        'healthy_components': len(healthy_components),
        'total_components': total_components,
        'response_time_ms': round((time.time() - start_time) * 1000, 2)
    }
    
    return Response(status_data)