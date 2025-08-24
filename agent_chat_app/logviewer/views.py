from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView


@method_decorator([login_required, staff_member_required], name='dispatch')
class LogViewerView(TemplateView):
    template_name = 'logviewer/logs.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'page_title': 'Log Viewer',
            'log_levels': ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        })
        return context
