from django import forms
from ads.models import Ad, Comment, Message, Category
from django.core.files.uploadedfile import InMemoryUploadedFile
from ads.humanize import naturalsize

from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import get_user_model

# Remember me button to work.
class LoginForm(AuthenticationForm):
    remember_me = forms.BooleanField(
        required=False,
        initial=False,
        label="Remember me"
    )


class PriceFilterForm(forms.Form):
    min_price = forms.IntegerField(min_value=0, required=False, widget=forms.NumberInput(attrs={
            "placeholder": "Min price",
            "class": "form-control",
            "inputmode": "numeric",
            "pattern": "[0-9]*",
        })
)
    max_price = forms.IntegerField(min_value=0, required=False, widget=forms.NumberInput(attrs={
            "placeholder": "Max price",
            "class": "form-control",
            "inputmode": "numeric",
            "pattern": "[0-9]*",
        })
)

    def clean(self):
        cleaned_data = super().clean()
        min_price = cleaned_data.get("min_price")
        max_price = cleaned_data.get("max_price")

        if min_price is not None and max_price is not None:
            if max_price < min_price:
                cleaned_data["min_price"] = max_price
                cleaned_data["max_price"] = min_price

        return cleaned_data


# Create the form class.
class CreateForm(forms.ModelForm):
    max_upload_limit = 3 * 1024 * 1024
    max_upload_limit_text = naturalsize(max_upload_limit)

    picture = forms.ImageField(required=False, label='Upload image ≤ ' + max_upload_limit_text + ' (JPG or PNG)')
    upload_field_name = 'picture'

    # Hint: this will need to be changed for use in the ads application
    category = forms.ModelChoiceField(
        queryset=Category.objects.filter(is_active=True),
        empty_label="Select category",)

    class Meta:
        model = Ad
        fields = ['title', 'price', 'category', 'city', 'text', 'picture']  # Picture is



    # Validate the size of the picture
    def clean(self):
        cleaned_data = super().clean()
        pic = cleaned_data.get('picture')

        if pic and pic.size > self.max_upload_limit:
            self.add_error('picture', "File must be ≤ "+self.max_upload_limit_text)
            return cleaned_data

    # Convert uploaded File object to a picture
    def save(self, commit=True):
        instance = super(CreateForm, self).save(commit=False)

        # We only need to adjust picture if it is a freshly uploaded file
        f = instance.picture   # Make a copy
        if isinstance(f, InMemoryUploadedFile):  # Extract data from the form to the model
            bytearr = f.read()
            instance.content_type = f.content_type
            instance.picture = bytearr  # Overwrite with the actual image data

        if commit:
            instance.save()

        return instance

class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['text']
        labels = {
            'text': '',
        }
        widgets = {
            'text': forms.Textarea(attrs={
                'rows': 2,
                'id': 'comment-textarea',
                'placeholder': 'Logged in users can comment here...'
            })
        }


class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ['encrypted_text']
        labels = {
            'encrypted_text': '',
        }
        widgets = {
            'encrypted_text': forms.Textarea(attrs={
                'rows': 2,
                'placeholder': 'Write your message...',
                'class': 'message-input',
            })
        }

    def clean_encrypted_text(self):
        text = self.cleaned_data['encrypted_text'].strip()
        if len(text) < 1:
            raise forms.ValidationError('Message must be at least 1 character.')
        return text

User = get_user_model()
class NewUserForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("A user with that email already exists.")
        return email


    def save(self, commit=True):
        user = super(NewUserForm, self).save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
        return user

# https://docs.djangoproject.com/en/3.0/topics/http/file-uploads/
# https://stackoverflow.com/questions/2472422/django-file-upload-size-limit
# https://stackoverflow.com/questions/32007311/how-to-change-data-in-django-modelform
# https://docs.djangoproject.com/en/3.0/ref/forms/validation/#cleaning-and-validating-fields-that-depend-on-each-other
