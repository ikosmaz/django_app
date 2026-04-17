from hashlib import md5
from django import template

# https://brobin.me/blog/2016/07/super-simple-django-gravatar/

# A "gravatar" is a globally recognized avatar that is based on email address
# People must register their email address and then upload a gravatar
# If an email address has no gravatar, a generic image is put in its place

# To use the gravatar filter in a template include
# {% load app_tags %}

register = template.Library()


@register.filter(name='gravatar')
def gravatar(user, size=35):
    try:
        size = int(size)
    except (TypeError, ValueError):
        size = 35

    email_value = ''
    if user and hasattr(user, 'email') and user.email:
        email_value = str(user.email).strip().lower()

    email = email_value.encode('utf-8')
    email_hash = md5(email).hexdigest()
    url = "//www.gravatar.com/avatar/{0}?s={1}&d=identicon&r=PG"
    return url.format(email_hash, size)


@register.filter(name='avatar_url')
def avatar_url(user, size=35):
    if user and getattr(user, 'is_authenticated', False):
        profile = getattr(user, 'profile', None)
        if profile is None:
            try:
                profile = user.profile
            except Exception:
                profile = None
        if profile and profile.avatar:
            return profile.avatar.url

    return gravatar(user, size=size)
