from django import forms
from ads.models import Ad, Comment, Message, Category, UserProfile
from PIL import Image, ImageOps, UnidentifiedImageError
from io import BytesIO
from django.core.files.base import ContentFile
import os

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
class MultiImageInput(forms.FileInput):
    allow_multiple_selected = True


class CreateForm(forms.ModelForm):
    photos = forms.Field(
        required=False,
        label='Upload photos (max 5)',
        widget=MultiImageInput(attrs={'multiple': True, 'accept': 'image/*'}),
    )
    cover_photo_id = forms.ChoiceField(
        required=False,
        label='Cover photo for ad list',
        choices=[('', 'Auto (first photo)')],
    )

    # Hint: this will need to be changed for use in the ads application
    category = forms.ModelChoiceField(
        queryset=Category.objects.filter(is_active=True),
        empty_label="Select category",)

    class Meta:
        model = Ad
        fields = ['title', 'price', 'category', 'city', 'text']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['photos'].widget.attrs['multiple'] = True
        instance = getattr(self, "instance", None)
        choices = [('', 'Auto (first photo)')]
        if instance and instance.pk:
            for idx, photo in enumerate(instance.photos.order_by('-is_cover', 'sort_order', 'id'), start=1):
                label = f"Photo {idx}"
                if photo.is_cover:
                    label += " (current cover)"
                choices.append((str(photo.id), label))
        self.fields['cover_photo_id'].choices = choices

    def get_delete_photo_ids(self):
        raw_ids = self.data.getlist('delete_photo_ids')
        parsed_ids = []
        for raw_id in raw_ids:
            try:
                photo_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if photo_id not in parsed_ids:
                parsed_ids.append(photo_id)

        instance = getattr(self, "instance", None)
        if not (instance and instance.pk and parsed_ids):
            return []

        return list(
            instance.photos.filter(id__in=parsed_ids).values_list('id', flat=True)
        )

    def clean(self):
        cleaned_data = super().clean()
        uploaded = self.files.getlist('photos')
        deleted_photo_ids = self.get_delete_photo_ids()

        for f in uploaded:
            content_type = getattr(f, 'content_type', '') or ''
            if not content_type.startswith('image/'):
                self.add_error('photos', f"{f.name} is not an image file. Please upload only images, such as .jpg, .jpeg, .png.")
                continue
            try:
                img = Image.open(f)
                img.verify()
                f.seek(0)
            except (UnidentifiedImageError, OSError, ValueError):
                self.add_error('photos', f"{f.name} is not a valid image.")

        instance = getattr(self, "instance", None)
        existing_count = (
            instance.photos.exclude(id__in=deleted_photo_ids).count()
            if instance and instance.pk
            else 0
        )
        if existing_count + len(uploaded) > 5:
            self.add_error('photos', "Maximum 5 photos per ad.")

        cover_photo_id = cleaned_data.get('cover_photo_id')
        if cover_photo_id and instance and instance.pk:
            if not instance.photos.filter(id=cover_photo_id).exists():
                self.add_error('cover_photo_id', "Selected cover photo does not belong to this ad.")
            else:
                try:
                    cover_photo_id_int = int(cover_photo_id)
                except (TypeError, ValueError):
                    self.add_error('cover_photo_id', "Invalid cover photo selection.")
                else:
                    if cover_photo_id_int in deleted_photo_ids:
                        self.add_error('cover_photo_id', "Selected cover photo is marked for deletion.")
        return cleaned_data

    # Keep content_type from uploaded file; image compression is handled in Ad.save().
    def save(self, commit=True):
        instance = super(CreateForm, self).save(commit=False)

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


class AvatarForm(forms.ModelForm):
    remove_avatar = forms.BooleanField(required=False, label="Use default avatar")
    crop_x = forms.FloatField(required=False, widget=forms.HiddenInput())
    crop_y = forms.FloatField(required=False, widget=forms.HiddenInput())
    crop_w = forms.FloatField(required=False, widget=forms.HiddenInput())
    crop_h = forms.FloatField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = UserProfile
        fields = ['avatar']
        widgets = {
            'avatar': forms.ClearableFileInput(attrs={'accept': 'image/*'})
        }

    def clean_avatar(self):
        avatar = self.cleaned_data.get('avatar')
        if not avatar:
            return avatar

        content_type = getattr(avatar, 'content_type', '') or ''
        if not content_type.startswith('image/'):
            raise forms.ValidationError("Please upload an image file (jpg, jpeg, png, webp).")

        try:
            img = Image.open(avatar)
            img.verify()
            avatar.seek(0)
        except (UnidentifiedImageError, OSError, ValueError):
            raise forms.ValidationError("Uploaded file is not a valid image.")

        return avatar

    def save(self, commit=True):
        instance = super().save(commit=False)
        avatar = self.cleaned_data.get('avatar')

        crop_x = self.cleaned_data.get('crop_x')
        crop_y = self.cleaned_data.get('crop_y')
        crop_w = self.cleaned_data.get('crop_w')
        crop_h = self.cleaned_data.get('crop_h')

        if avatar and all(v is not None for v in [crop_x, crop_y, crop_w, crop_h]) and crop_w > 0 and crop_h > 0:
            avatar.open()
            img = Image.open(avatar)
            img = ImageOps.exif_transpose(img).convert("RGB")

            left = max(0, int(crop_x))
            top = max(0, int(crop_y))
            right = min(img.width, int(crop_x + crop_w))
            bottom = min(img.height, int(crop_y + crop_h))

            if right > left and bottom > top:
                cropped = img.crop((left, top, right, bottom))
                buffer = BytesIO()
                cropped.save(buffer, format="JPEG", quality=95, optimize=True)
                avatar_name = os.path.splitext(os.path.basename(avatar.name))[0] or f"avatar_{instance.user_id}"
                instance.avatar.save(f"{avatar_name}_crop.jpg", ContentFile(buffer.getvalue()), save=False)

        if commit:
            instance.save()
        return instance

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
