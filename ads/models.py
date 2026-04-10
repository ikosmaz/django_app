from django.db import models
from django.db.models import Avg, Count
from django.core.validators import MinLengthValidator
from django.conf import settings

from ads.crypto_utils import decrypt_text, encrypt_text

from PIL import Image, ImageOps #thumbnail maker
from django.core.files.base import ContentFile
from io import BytesIO
import os

from django.db.models.signals import post_delete #To delete images for deleted ads
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
    THUMB_SIZE = (300, 300)  # Resize target
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


    def save(self, *args, **kwargs):
        if self.pk:
           old = Ad.objects.get(pk=self.pk)
        else:
            old = None

        # First save: store new image
        super().save(*args, **kwargs)

        # If updating and picture changed → delete old one
        if old:
            if old.picture and old.picture != self.picture:
                old.picture.delete(save=False)

            if old.thumbnail and old.thumbnail != self.thumbnail:
                old.thumbnail.delete(save=False)

        # Generate thumbnail if missing or replaced
        if self.picture and not self.thumbnail:
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

@receiver(post_delete, sender=Ad)
def delete_ad_images(sender, instance, **kwargs):
    # delete main picture
    if instance.picture and "no_image" not in instance.picture.name:
        instance.picture.delete(save=False)

    # delete thumbnail
    if instance.thumbnail and "no_image" not in instance.thumbnail.name:
        instance.thumbnail.delete(save=False)

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
