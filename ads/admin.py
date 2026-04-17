from django.contrib import admin
from ads.models import Ad, CommentFav, Fav, Message, Category, UserProfile

# Register your models here.

class PicAdmin(admin.ModelAdmin):
    exclude = ('thumbnail', 'content_type')


admin.site.register(Ad, PicAdmin)

admin.site.register(Fav)

admin.site.register(CommentFav)
admin.site.register(Message)
admin.site.register(UserProfile)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "icon", "is_active", "sort_order")
    list_editable = ("icon", "is_active", "sort_order")
    search_fields = ("name",)
