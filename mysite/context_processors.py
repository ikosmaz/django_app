from django.conf import settings as django_settings


def settings(request):
    context = {
        'settings': django_settings,
        'menu_unread_messages_count': 0,
        'menu_messages': [],
    }

    if request.user.is_authenticated:
        from ads.models import Message

        context['menu_unread_messages_count'] = Message.objects.filter(
            recipient=request.user,
            is_read=False
        ).count()
        context['menu_messages'] = list(
            Message.objects.filter(recipient=request.user)
            .select_related('sender', 'ad')
            .order_by('is_read', '-created_at')
        )

    return context
