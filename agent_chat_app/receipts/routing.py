"""
WebSocket routing for receipts app.
"""

from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/receipt/(?P<receipt_id>\d+)/$', consumers.ReceiptProgressConsumer.as_asgi()),
    re_path(r'ws/inventory/$', consumers.InventoryNotificationConsumer.as_asgi()),
    re_path(r'ws/notifications/$', consumers.GeneralNotificationConsumer.as_asgi()),
]