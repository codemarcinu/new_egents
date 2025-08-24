from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView
from .models import Receipt


@login_required
def receipt_upload_view(request):
    """View for receipt upload interface."""
    return render(request, 'receipts/receipt_upload.html')


@login_required  
def receipt_list_view(request):
    """Simple list view for receipts."""
    receipts = Receipt.objects.filter(user=request.user).order_by('-created_at')[:10]
    context = {
        'receipts': receipts
    }
    return render(request, 'receipts/receipt_list.html', context)
