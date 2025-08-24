from django.urls import re_path
from . import consumers

# Import receipt consumers  
from agent_chat_app.receipts import consumers as receipt_consumers
# Import log viewer consumers
from agent_chat_app.logviewer import consumers as log_consumers

websocket_urlpatterns = [
    # Chat WebSocket routes
    re_path(r"ws/chat/(?P<conversation_id>\d+)/$", consumers.ChatConsumer.as_asgi()),
    
    # Receipt processing WebSocket routes
    re_path(r'ws/receipt/(?P<receipt_id>\d+)/$', receipt_consumers.ReceiptProgressConsumer.as_asgi()),
    re_path(r'ws/inventory/$', receipt_consumers.InventoryNotificationConsumer.as_asgi()),
    re_path(r'ws/notifications/$', receipt_consumers.GeneralNotificationConsumer.as_asgi()),
    
    # Log viewer WebSocket routes
    re_path(r'ws/logs/$', log_consumers.LogStreamConsumer.as_asgi()),
]