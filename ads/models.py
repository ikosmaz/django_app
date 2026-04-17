from django.db import models
from django.db.models import Avg, Count
from django.core.validators import MinLengthValidator
from django.conf import settings
from django.contrib.auth import get_user_model

from ads.crypto_utils import decrypt_text, encrypt_text
from PIL import Image, ImageOps #thumbnail maker
from django.core.files.base import ContentFile
from io import BytesIO
import os

from django.db.models.signals import post_delete, post_save #To delete images for deleted ads
from django.dispatch import receiver

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    icon = models.CharField(
        max_length=50,
        blank=True,
        help_text="Font Awesome class, e.g. fa-car"
    )

    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name

class Ad(models.Model) :
    title = models.CharField(
            max_length=200,
            validators=[MinLengthValidator(2, "Title must be greater than 2 characters")]
    )
    price = models.DecimalField(max_digits=7, decimal_places=2, null=True)
    text = models.TextField()
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    comments = models.ManyToManyField(settings.AUTH_USER_MODEL, through='Comment', related_name='comments_owned')

    #picture = models.BinaryField(null=True, blank=True, editable=True)
    picture = models.ImageField(upload_to='ads/',null=True, blank=True, editable=True)
    thumbnail = models.ImageField(upload_to='ads/thumbnails/',null=True, blank=True, editable=True)
    THUMB_SIZE = (150, 150)  # Resize target
    MAX_IMAGE_BYTES = 1 * 1024 * 1024  # Store original image compressed to <= 1MB
    content_type = models.CharField(max_length=256, null=True, blank=True, help_text='The MIMEType of the file')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    favorites = models.ManyToManyField(settings.AUTH_USER_MODEL, through='Fav', related_name='favorite_ads')
    city = models.CharField(max_length=100, blank=True, null=True)
    category = models.ForeignKey(Category,on_delete=models.PROTECT,related_name="ads")
    #category = models.ForeignKey(Category,on_delete=models.PROTECT,null=True,blank=True,)

    like_count = models.PositiveIntegerField(default=0)


    @property
    def rating_stats(self):
        return self.ratings.aggregate(
            avg=Avg("stars"),
            count=Count("id"),
        )

    @property
    def average_rating(self):
        return round(self.rating_stats["avg"] or 0, 1)

    @property
    def total_ratings(self):
        return self.rating_stats["count"]


    def _normalize_city(self):
        if self.city is None:
            return
        cleaned = " ".join(str(self.city).split())
        self.city = cleaned.title() if cleaned else None

    def _compress_picture_to_limit(self):
        if not self.picture:
            return

        self.picture.open()
        img = Image.open(self.picture)
        img = ImageOps.exif_transpose(img).convert("RGB")

        quality = 90
        min_quality = 35
        min_dimension = 500
        buffer = BytesIO()

        while True:
            buffer.seek(0)
            buffer.truncate(0)
            img.save(buffer, format="JPEG", quality=quality, optimize=True)
            size = buffer.tell()

            if size <= self.MAX_IMAGE_BYTES:
                break

            if quality > min_quality:
                quality = max(min_quality, quality - 10)
                continue

            if min(img.size) <= min_dimension:
                break

            img.thumbnail((int(img.width * 0.9), int(img.height * 0.9)), Image.LANCZOS)

        pic_name = os.path.splitext(os.path.basename(self.picture.name))[0] or "ad_image"
        self.picture.save(f"{pic_name}.jpg", ContentFile(buffer.getvalue()), save=False)
        self.content_type = "image/jpeg"

    def sync_cover_from_photos(self):
        cover = self.photos.filter(is_cover=True).order_by('sort_order', 'id').first()
        if cover is None:
            cover = self.photos.order_by('sort_order', 'id').first()
            if cover:
                self.photos.filter(id=cover.id).update(is_cover=True)

        if cover:
            Ad.objects.filter(pk=self.pk).update(
                picture=cover.image.name,
                thumbnail=cover.thumbnail.name if cover.thumbnail else None,
                content_type='image/jpeg',
            )
        else:
            Ad.objects.filter(pk=self.pk).update(
                picture=None,
                thumbnail=None,
                content_type=None,
            )

    def save(self, *args, **kwargs):
        self._normalize_city()

        if self.pk:
           old = Ad.objects.get(pk=self.pk)
        else:
            old = None

        old_picture_name = old.picture.name if (old and old.picture) else None
        old_thumbnail_name = old.thumbnail.name if (old and old.thumbnail) else None
        new_picture_name = self.picture.name if self.picture else None
        picture_changed = (old_picture_name != new_picture_name) if old else bool(self.picture)

        if picture_changed and self.picture:
            self._compress_picture_to_limit()

        if picture_changed:
            self.thumbnail = None
            if not self.picture:
                self.content_type = None

        # First save: store new image
        super().save(*args, **kwargs)

        # If updating and picture changed → delete old files
        if old and picture_changed:
            current_picture_name = self.picture.name if self.picture else None
            current_thumbnail_name = self.thumbnail.name if self.thumbnail else None

            if old_picture_name and old_picture_name != current_picture_name and "no_image" not in old_picture_name:
                self.picture.storage.delete(old_picture_name)

            if old_thumbnail_name and old_thumbnail_name != current_thumbnail_name and "no_image" not in old_thumbnail_name:
                self.thumbnail.storage.delete(old_thumbnail_name)

        # Generate thumbnail if missing or replaced
        if self.picture and (picture_changed or not self.thumbnail):
            self.make_thumbnail()

    def make_thumbnail(self):

        if not self.picture:
            self.thumbnail = None
            return


        img = Image.open(self.picture)
        img = img.convert('RGB')
        img = ImageOps.exif_transpose(img) #Fix rotation
        img.thumbnail(self.THUMB_SIZE)

        buffer = BytesIO()
        img.save(buffer, format='JPEG', quality=90)

        thumb_name = f"thumb_{self.id}_{os.path.basename(self.picture.name)}"

        self.thumbnail.save(
            thumb_name,
            ContentFile(buffer.getvalue()),
            save=False
        )

        super().save(update_fields=['thumbnail'])


    # Shows up in the admin list
    def __str__(self):
        return self.title


class AdPhoto(models.Model):
    ad = models.ForeignKey(Ad, on_delete=models.CASCADE, related_name='photos')
    image = models.ImageField(upload_to='ads/')
    thumbnail = models.ImageField(upload_to='ads/thumbnails/', null=True, blank=True, editable=True)
    is_cover = models.BooleanField(default=False)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    THUMB_SIZE = (150, 150)
    MAX_IMAGE_BYTES = 1 * 1024 * 1024

    class Meta:
        ordering = ['sort_order', 'id']

    def _compress_image_to_limit(self):
        if not self.image:
            return

        self.image.open()
        img = Image.open(self.image)
        img = ImageOps.exif_transpose(img).convert("RGB")

        quality = 90
        min_quality = 35
        min_dimension = 500
        buffer = BytesIO()

        while True:
            buffer.seek(0)
            buffer.truncate(0)
            img.save(buffer, format="JPEG", quality=quality, optimize=True)
            size = buffer.tell()

            if size <= self.MAX_IMAGE_BYTES:
                break

            if quality > min_quality:
                quality = max(min_quality, quality - 10)
                continue

            if min(img.size) <= min_dimension:
                break

            img.thumbnail((int(img.width * 0.9), int(img.height * 0.9)), Image.LANCZOS)

        img_name = os.path.splitext(os.path.basename(self.image.name))[0] or "ad_photo"
        self.image.save(f"{img_name}.jpg", ContentFile(buffer.getvalue()), save=False)

    def make_thumbnail(self):
        if not self.image:
            self.thumbnail = None
            return

        self.image.open()
        img = Image.open(self.image)
        img = ImageOps.exif_transpose(img).convert('RGB')
        img.thumbnail(self.THUMB_SIZE)

        buffer = BytesIO()
        img.save(buffer, format='JPEG', quality=90)

        thumb_name = f"thumb_{self.id}_{os.path.basename(self.image.name)}"
        self.thumbnail.save(thumb_name, ContentFile(buffer.getvalue()), save=False)

    def save(self, *args, **kwargs):
        if self.pk:
            old = AdPhoto.objects.get(pk=self.pk)
        else:
            old = None

        old_image_name = old.image.name if (old and old.image) else None
        old_thumbnail_name = old.thumbnail.name if (old and old.thumbnail) else None
        new_image_name = self.image.name if self.image else None
        image_changed = (old_image_name != new_image_name) if old else bool(self.image)

        if image_changed and self.image:
            self._compress_image_to_limit()
            self.thumbnail = None

        super().save(*args, **kwargs)

        if image_changed and self.image and not self.thumbnail:
            self.make_thumbnail()
            super().save(update_fields=['thumbnail'])

        if old and image_changed:
            current_image_name = self.image.name if self.image else None
            current_thumbnail_name = self.thumbnail.name if self.thumbnail else None

            if old_image_name and old_image_name != current_image_name and "no_image" not in old_image_name:
                self.image.storage.delete(old_image_name)

            if old_thumbnail_name and old_thumbnail_name != current_thumbnail_name and "no_image" not in old_thumbnail_name:
                self.thumbnail.storage.delete(old_thumbnail_name)

        if self.is_cover:
            AdPhoto.objects.filter(ad=self.ad).exclude(pk=self.pk).filter(is_cover=True).update(is_cover=False)
        elif not AdPhoto.objects.filter(ad=self.ad, is_cover=True).exists():
            AdPhoto.objects.filter(pk=self.pk).update(is_cover=True)
            self.is_cover = True

        self.ad.sync_cover_from_photos()

    def __str__(self):
        return f"Photo #{self.id} for Ad #{self.ad_id}"

@receiver(post_delete, sender=Ad)
def delete_ad_images(sender, instance, **kwargs):
    # delete main picture
    if instance.picture and "no_image" not in instance.picture.name:
        instance.picture.delete(save=False)

    # delete thumbnail
    if instance.thumbnail and "no_image" not in instance.thumbnail.name:
        instance.thumbnail.delete(save=False)


@receiver(post_delete, sender=AdPhoto)
def delete_ad_photo_files(sender, instance, **kwargs):
    image_name = instance.image.name if instance.image else None
    thumbnail_name = instance.thumbnail.name if instance.thumbnail else None

    if image_name and "no_image" not in image_name:
        instance.image.storage.delete(image_name)
    if thumbnail_name and "no_image" not in thumbnail_name:
        instance.thumbnail.storage.delete(thumbnail_name)

    if instance.ad_id:
        ad = Ad.objects.filter(pk=instance.ad_id).first()
        if ad:
            ad.sync_cover_from_photos()


class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    AVATAR_SIZE = (400, 400)

    def _compress_avatar(self):
        if not self.avatar:
            return

        self.avatar.open()
        img = Image.open(self.avatar)
        img = ImageOps.exif_transpose(img).convert("RGB")
        img = ImageOps.fit(img, self.AVATAR_SIZE, method=Image.LANCZOS)

        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=95, optimize=True)
        avatar_name = os.path.splitext(os.path.basename(self.avatar.name))[0] or f"avatar_{self.user_id}"
        self.avatar.save(f"{avatar_name}.jpg", ContentFile(buffer.getvalue()), save=False)

    def save(self, *args, **kwargs):
        if self.pk:
            old = UserProfile.objects.filter(pk=self.pk).first()
        else:
            old = None

        old_avatar_name = old.avatar.name if (old and old.avatar) else None
        new_avatar_name = self.avatar.name if self.avatar else None
        avatar_changed = (old_avatar_name != new_avatar_name) if old else bool(self.avatar)

        if avatar_changed and self.avatar:
            self._compress_avatar()

        super().save(*args, **kwargs)

        if old and avatar_changed and old_avatar_name:
            current_avatar_name = self.avatar.name if self.avatar else None
            if old_avatar_name != current_avatar_name and "no_image" not in old_avatar_name:
                self.avatar.storage.delete(old_avatar_name)

    def __str__(self):
        return f"Profile for {self.user.username}"


@receiver(post_save, sender=get_user_model())
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)


@receiver(post_delete, sender=UserProfile)
def delete_user_profile_avatar(sender, instance, **kwargs):
    avatar_name = instance.avatar.name if instance.avatar else None
    if avatar_name and "no_image" not in avatar_name:
        instance.avatar.storage.delete(avatar_name)

class AdRating(models.Model):
    ad = models.ForeignKey(Ad, on_delete=models.CASCADE, related_name="ratings")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    stars = models.PositiveSmallIntegerField(default=0)  # 1..5
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('ad', 'user')  # only one rating per user


class Comment(models.Model) :
    text = models.TextField(validators=[MinLengthValidator(3, "Comment must be greater than 3 characters")])
    ad = models.ForeignKey(Ad, on_delete=models.CASCADE)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    favorites = models.ManyToManyField(settings.AUTH_USER_MODEL, through='CommentFav', related_name='favorite_comments')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Shows up in the admin list
    def __str__(self):
        if len(self.text) < 15 :
            return self.text
        return self.text[:11] + ' ...'
class Fav(models.Model) :
    ad = models.ForeignKey(Ad, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    # https://docs.djangoproject.com/en/3.0/ref/models/options/#unique-together
    class Meta:
        unique_together = ('ad', 'user')

    def __str__(self) :
        return '%s likes %s'%(self.user.username, self.ad.title[:10])


class CommentFav(models.Model):
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('comment', 'user')

    def __str__(self):
        return '%s likes comment %s' % (self.user.username, self.comment.id)


class Message(models.Model):
    ad = models.ForeignKey(Ad, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_messages')
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_messages')
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='replies')
    encrypted_text = models.TextField()
    is_read = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'Message #{self.id} about ad #{self.ad_id}'

    @property
    def text(self):
        return decrypt_text(self.encrypted_text)

    def set_text(self, plain_text):
        self.encrypted_text = encrypt_text(plain_text)
