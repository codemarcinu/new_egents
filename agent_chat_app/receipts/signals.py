"""
Django signals for receipt processing.
Future signals for automated tasks and notifications.
"""

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Receipt, InventoryItem


@receiver(post_save, sender=Receipt)
def receipt_status_changed(sender, instance, created, **kwargs):
    """Handle receipt status changes."""
    if not created and instance.status == 'completed':
        # Could trigger additional processing here
        pass


@receiver(post_save, sender=InventoryItem)
def inventory_updated(sender, instance, created, **kwargs):
    """Handle inventory updates."""
    # Could check for low stock alerts here
    pass