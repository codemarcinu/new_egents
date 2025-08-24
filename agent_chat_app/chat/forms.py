from django import forms
from .models import UserSettings
from .services import OllamaService


class UserSettingsForm(forms.ModelForm):
    """Form for user chat settings"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Dynamically populate model choices
        try:
            models = OllamaService.get_available_models()
            model_choices = [(model['name'], f"{model['display_name']} ({model['size_human']})") for model in models]
        except:
            # Fallback if service fails
            model_choices = [
                ('gemma2:2b', 'Gemma2 2B'),
                ('gemma2:9b', 'Gemma2 9B'),
            ]
        
        self.fields['preferred_model'] = forms.ChoiceField(
            choices=model_choices,
            widget=forms.Select(attrs={'class': 'form-select'}),
            help_text="Select your preferred AI model"
        )
        
        # Style other fields
        self.fields['system_instruction'].widget = forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 4,
            'placeholder': 'Enter custom system instruction for the AI...'
        })
        self.fields['max_tokens'].widget = forms.NumberInput(attrs={
            'class': 'form-control',
            'min': 100,
            'max': 8192,
            'step': 100
        })
        self.fields['temperature'].widget = forms.NumberInput(attrs={
            'class': 'form-control',
            'min': 0.0,
            'max': 1.0,
            'step': 0.1
        })
    
    class Meta:
        model = UserSettings
        fields = ['preferred_model', 'system_instruction', 'max_tokens', 'temperature']


class DocumentUploadForm(forms.Form):
    """Form for uploading documents for RAG processing"""
    file = forms.FileField(
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.pdf,.docx,.xlsx,.txt'
        }),
        help_text='Supported formats: PDF, DOCX, XLSX, TXT (max 10MB)'
    )
    
    def clean_file(self):
        file = self.cleaned_data['file']
        
        # Check file size (10MB limit)
        if file.size > 10 * 1024 * 1024:
            raise forms.ValidationError('File size cannot exceed 10MB.')
        
        # Check file extension
        allowed_extensions = ['.pdf', '.docx', '.xlsx', '.txt']
        file_ext = '.' + file.name.split('.')[-1].lower()
        if file_ext not in allowed_extensions:
            raise forms.ValidationError(
                f'Unsupported file type. Allowed: {", ".join(allowed_extensions)}'
            )
        
        return file