"""
URL configuration for receipts app.
"""

from django.urls import path
from .api.views import (
    ReceiptUploadAPIView, ReceiptStatusAPIView, ReceiptDetailAPIView,
    ReceiptListAPIView, ProductSearchAPIView, InventoryListAPIView,
    InventoryUpdateAPIView, receipt_stats_view, inventory_summary_view,
    receipt_delete_view
)
from .views import receipt_upload_view, receipt_list_view

app_name = 'receipts'

urlpatterns = [
    # Template views
    path('', receipt_list_view, name='receipt-list'),
    path('upload/', receipt_upload_view, name='receipt-upload'),
    
    # Receipt processing endpoints  
    path('api/upload/', ReceiptUploadAPIView.as_view(), name='receipt-upload-api'),
    path('api/<int:receipt_id>/status/', ReceiptStatusAPIView.as_view(), name='receipt-status'),
    path('api/<int:pk>/', ReceiptDetailAPIView.as_view(), name='receipt-detail'),
    path('api/<int:receipt_id>/delete/', receipt_delete_view, name='receipt-delete'),
    path('api/', ReceiptListAPIView.as_view(), name='receipt-list-api'),
    
    # Product and inventory endpoints
    path('api/products/search/', ProductSearchAPIView.as_view(), name='product-search'),
    path('api/inventory/', InventoryListAPIView.as_view(), name='inventory-list'),
    path('api/inventory/update/', InventoryUpdateAPIView.as_view(), name='inventory-update'),
    
    # Statistics endpoints
    path('api/stats/', receipt_stats_view, name='receipt-stats'),
    path('api/inventory/summary/', inventory_summary_view, name='inventory-summary'),
]