"""
URL configuration for receipts API endpoints.
"""

from django.urls import path
from . import views

app_name = 'receipts-api'

urlpatterns = [
    # Receipt upload and processing
    path('upload/', views.ReceiptUploadAPIView.as_view(), name='receipt-upload'),
    path('<int:receipt_id>/status/', views.ReceiptStatusAPIView.as_view(), name='receipt-status'),
    path('<int:pk>/', views.ReceiptDetailAPIView.as_view(), name='receipt-detail'),
    path('', views.ReceiptListAPIView.as_view(), name='receipt-list'),
    path('<int:receipt_id>/delete/', views.receipt_delete_view, name='receipt-delete'),
    
    # Product and inventory management
    path('products/search/', views.ProductSearchAPIView.as_view(), name='product-search'),
    path('inventory/', views.InventoryListAPIView.as_view(), name='inventory-list'),
    path('inventory/update/', views.InventoryUpdateAPIView.as_view(), name='inventory-update'),
    path('inventory/summary/', views.inventory_summary_view, name='inventory-summary'),
    
    # Statistics
    path('stats/', views.receipt_stats_view, name='receipt-stats'),
]