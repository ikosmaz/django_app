from ads.models import Ad, AdPhoto, Comment, Fav, CommentFav, Message, AdRating, Category, UserProfile
from ads.owner import OwnerListView, OwnerDetailView, OwnerCreateView, OwnerUpdateView, OwnerDeleteView
from django.views import View
from django.views.generic import ListView
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.uploadedfile import InMemoryUploadedFile
from ads.forms import CreateForm, CommentForm, MessageForm, NewUserForm, AvatarForm
from django.contrib.humanize.templatetags.humanize import naturaltime
from ads.utils import dump_queries
from django.db.models import Q

from django.contrib.auth import login, authenticate, logout
from django.contrib import messages
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.paginator import Paginator
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.core import signing
from django.core.signing import BadSignature, SignatureExpired
from django.db.models import Avg, Count, FloatField, Case, When, IntegerField
from django.db.models.functions import Coalesce
from django.db.models import Subquery, OuterRef
from django.db import transaction
from django.conf import settings
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode, url_has_allowed_host_and_scheme
from .forms import LoginForm, PriceFilterForm
from django.contrib.auth.decorators import login_required

# Create your views here.
def _send_activation_email(request, user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    activate_path = reverse('ads:activate_account', kwargs={'uidb64': uid, 'token': token})
    protocol = 'https' if request.is_secure() else 'http'
    activation_link = f"{protocol}://{request.get_host()}{activate_path}"

    context = {
        'user': user,
        'activation_link': activation_link,
        'app_name': settings.APP_NAME,
    }
    subject = render_to_string('registration/activation_email_subject.txt', context).strip()
    body = render_to_string('registration/activation_email.txt', context)

    send_mail(
        subject=subject,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )


def _send_account_deletion_email(request, user):
    delete_token = signing.dumps({'uid': user.pk}, salt='account-delete')
    delete_path = reverse('ads:account_delete_confirm', kwargs={'signed_token': delete_token})
    protocol = 'https' if request.is_secure() else 'http'
    delete_link = f"{protocol}://{request.get_host()}{delete_path}"

    context = {
        'user': user,
        'delete_link': delete_link,
        'app_name': settings.APP_NAME,
    }
    subject = render_to_string('registration/account_delete_email_subject.txt', context).strip()
    body = render_to_string('registration/account_delete_email.txt', context)

    send_mail(
        subject=subject,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )


def _get_safe_next_url(request, fallback_url):
    next_url = request.POST.get('next') or request.GET.get('next')
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return fallback_url


def register_request(request):
    if request.method == "POST":
        form = NewUserForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    user = form.save(commit=False)
                    user.is_active = False
                    user.save()
                    _send_activation_email(request, user)
            except Exception:
                messages.error(
                    request,
                    "Could not send confirmation email. Please check email settings and try again.",
                )
                return render(
                    request=request,
                    template_name="registration/register.html",
                    context={"register_form": form},
                )

            return render(
                request=request,
                template_name="registration/activation_sent.html",
                context={"email": user.email},
            )
        messages.error(request, "Unsuccessful registration. Please fix the errors below.")
    else:
        form = NewUserForm()
    return render(request=request, template_name="registration/register.html", context={"register_form": form})


def activate_account(request, uidb64, token):
    UserModel = get_user_model()
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = UserModel.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, UserModel.DoesNotExist):
        user = None

    if user and default_token_generator.check_token(user, token):
        if not user.is_active:
            user.is_active = True
            user.save(update_fields=['is_active'])
        return render(request, "registration/activation_success.html")

    if user and user.is_active:
        return render(request, "registration/activation_success.html", {"already_active": True})

    return render(request, "registration/activation_invalid.html", status=400)


@login_required
def avatar_change(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = AvatarForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            remove_avatar = form.cleaned_data.get('remove_avatar')
            uploaded_avatar = form.cleaned_data.get('avatar')

            if remove_avatar:
                if profile.avatar:
                    profile.avatar.delete(save=False)
                profile.avatar = None
                profile.save(update_fields=['avatar'])
                messages.success(request, "Avatar reset to default.")
            elif uploaded_avatar:
                form.save()
                messages.success(request, "Avatar updated.")
            else:
                messages.info(request, "No file selected. Current avatar unchanged.")

            return redirect('ads:avatar_change')
    else:
        form = AvatarForm(instance=profile)

    return render(
        request,
        "registration/avatar_form.html",
        {
            "form": form,
        },
    )


@login_required
def account_edit(request):
    return render(request, "registration/account_edit.html")


@login_required
def account_delete(request):
    if request.method != "POST":
        return render(request, "registration/delete_account.html")

    user = request.user
    if not user.email:
        messages.error(request, "No email found on your account. Add an email first, then try again.")
        return redirect("ads:account_edit")

    try:
        _send_account_deletion_email(request, user)
    except Exception:
        messages.error(
            request,
            "Could not send account deletion email. Please check email settings and try again.",
        )
        return redirect("ads:account_delete")

    messages.success(
        request,
        "Deletion link sent to your email. Click that link to permanently delete your account.",
    )
    return redirect("ads:account_edit")


def account_delete_confirm(request, signed_token=None, uidb64=None, token=None):
    UserModel = get_user_model()
    user = None
    token_state = "invalid"  # invalid | valid_user | valid_missing
    signed_token_value = request.POST.get('token') or signed_token or request.GET.get('token')

    if signed_token_value:
        try:
            payload = signing.loads(
                signed_token_value,
                salt='account-delete',
                max_age=getattr(settings, 'PASSWORD_RESET_TIMEOUT', 60 * 60 * 24),
            )
            uid = payload.get('uid')
            if uid is not None:
                user = UserModel.objects.filter(pk=uid).first()
                token_state = "valid_user" if user else "valid_missing"
        except (BadSignature, SignatureExpired):
            token_state = "invalid"
    elif uidb64 and token:
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            legacy_user = UserModel.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, UserModel.DoesNotExist):
            legacy_user = None

        if legacy_user and default_token_generator.check_token(legacy_user, token):
            user = legacy_user
            token_state = "valid_user"

    if token_state == "invalid":
        return render(request, "registration/account_delete_invalid.html", status=400)

    if request.method != "POST":
        if token_state == "valid_missing":
            return render(request, "registration/account_delete_confirmed.html", {"already_deleted": True})
        return render(
            request,
            "registration/account_delete_verify.html",
            {"signed_token": signed_token_value},
        )

    if token_state == "valid_missing":
        return render(request, "registration/account_delete_confirmed.html", {"already_deleted": True})

    if user:
        if request.user.is_authenticated and request.user.pk == user.pk:
            logout(request)
        user.delete()
        return render(request, "registration/account_delete_confirmed.html")
    return render(request, "registration/account_delete_invalid.html", status=400)


@login_required
def messages_inbox(request):
    user = request.user
    all_messages = list(
        Message.objects
        .filter(Q(ad__owner=user) | Q(sender=user) | Q(recipient=user))
        .select_related('sender', 'recipient', 'ad', 'ad__owner', 'parent')
        .order_by('-created_at')
    )

    ad_map = {}
    ad_order = []
    unread_ids = []

    for msg in all_messages:
        ad = msg.ad
        ad_entry = ad_map.get(ad.id)
        if ad_entry is None:
            ad_entry = {
                'ad': ad,
                'threads': {},
                'thread_order': [],
                'has_unread': False,
            }
            ad_map[ad.id] = ad_entry
            ad_order.append(ad.id)

        other_user = msg.sender if msg.sender != user else msg.recipient
        thread_entry = ad_entry['threads'].get(other_user.id)
        if thread_entry is None:
            thread_entry = {
                'user': other_user,
                'messages': [],
                'reply_target_message_id': None,
                'has_unread': False,
            }
            ad_entry['threads'][other_user.id] = thread_entry
            ad_entry['thread_order'].append(other_user.id)

        thread_entry['messages'].append(msg)

        if (
            user == ad.owner
            and msg.sender_id == other_user.id
            and thread_entry['reply_target_message_id'] is None
        ):
            thread_entry['reply_target_message_id'] = msg.id

        if msg.recipient_id == user.id and not msg.is_read:
            thread_entry['has_unread'] = True
            ad_entry['has_unread'] = True
            unread_ids.append(msg.id)

    ad_threads = []
    for ad_id in ad_order:
        ad_entry = ad_map[ad_id]
        ad_threads.append({
            'ad': ad_entry['ad'],
            'threads': [ad_entry['threads'][user_id] for user_id in ad_entry['thread_order']],
            'has_unread': ad_entry['has_unread'],
        })

    if unread_ids:
        Message.objects.filter(id__in=unread_ids, recipient=user, is_read=False).update(is_read=True)

    return render(
        request,
        "ads/messages_inbox.html",
        {
            "ad_threads": ad_threads,
            "message_form": MessageForm(),
        },
    )

def login_request(request):
	if request.method == "POST":
		form = AuthenticationForm(request, data=request.POST)
		if form.is_valid():
			#username = form.cleaned_data.get('username')
			#password = form.cleaned_data.get('password')
			#user = authenticate(username=username, password=password)
			user = form.get_user()

			# ✅ REMEMBER ME LOGIC
			if not request.POST.get("remember_me"):
			    request.session.set_expiry(0)  # expire on browser close
			else:
			    request.session.set_expiry(None)  # default expiry

			if user is not None:
				login(request, user)
				messages.info(request, f"You are now logged in as {user.username}.")
				return redirect("ads:all")
			else:
				messages.error(request,"Invalid username or password.")
		else:
			messages.error(request,"Invalid username or password.")
	form = AuthenticationForm()
	return render(request=request, template_name="accounts/login.html", context={"login_form":form})


@login_required
def rate_ad(request, ad_id, stars):
    ad = get_object_or_404(Ad, id=ad_id)

    # update or create rating
    if request.user == ad.owner:
        return HttpResponseForbidden("You cannot rate your own ad.")
    AdRating.objects.update_or_create(ad=ad, user=request.user, defaults={'stars': stars})

    return JsonResponse({
        "average": ad.average_rating,
        "total": ad.total_ratings,
    })


class AdListView(OwnerListView):
    model = Ad
    template_name = "ads/ad_list.html"

    def get(self, request):
        ads = Ad.objects.all()
        favorites = list()
        strval = request.GET.get("search", False)
        number_of_ads = Ad.objects.count()


        # ---- SEARCH OR DEFAULT LIST ----
        if strval:
            query = Q(title__icontains=strval)
            query.add(Q(text__icontains=strval), Q.OR)
            ads = ads.filter(query).order_by('-updated_at')


        # FILTERS
        city = request.GET.get("city")
        category_id = request.GET.get("category")

        min_price = None
        max_price = None
        price_form = PriceFilterForm(request.GET or None)
        if price_form.is_valid():
            min_price = price_form.cleaned_data.get("min_price")
            max_price = price_form.cleaned_data.get("max_price")

        sort = request.GET.get("sort")

        if city:
            ads = ads.filter(city=city)

        if category_id:
            ads = ads.filter(category_id=category_id)

        if min_price is not None:
            ads = ads.filter(price__gte=min_price)

        if max_price is not None:
            ads = ads.filter(price__lte=max_price)

        # --- ✅ ANNOTATIONS
        ads = ads.annotate(all_comments_count=Count("comment", distinct=True),
        average_rating_db=Coalesce(Avg("ratings__stars", distinct=True),0.0,output_field=FloatField(),),
        total_ratings_db=Count("ratings", distinct=True),)

        if request.user.is_authenticated:
            user_rating_sub = AdRating.objects.filter(ad=OuterRef("pk"),user=request.user).values("stars")[:1]
            ads = ads.annotate(user_rating=Subquery(user_rating_sub))


        # SORT
        if sort == "rating":
            ads = ads.order_by("-average_rating_db")
        elif sort == "newest":
            ads = ads.order_by("-updated_at")
        elif sort == "price_desc":
            ads = ads.order_by("-price")
        elif sort == "price_asc":
            ads = ads.order_by("price")
        else:
            ads = ads.order_by("-updated_at")

        # --- PAGINATOR 6 PER PAGE CAN BE CHANGED---
        number_per_page = 6
        paginator = Paginator(ads, number_per_page)
        page_number = request.GET.get("page")
        page_obj = paginator.get_page(page_number)

        # Natural time for each ad shown on this page
        for obj in page_obj:
            obj.natural_updated = naturaltime(obj.updated_at)

        # ---- FAVORITES SECTION ----
        if request.user.is_authenticated:
            rows = request.user.favorite_ads.values('id')
            favorites = [row['id'] for row in rows]
            favorites_count = len(favorites)
            my_ads_count = Ad.objects.filter(owner=request.user).count()
        else:
            favorites = []
            favorites_count = 0
            my_ads_count = 0


        # CITY + CATEGORY CHOICES
        cities = Ad.objects.exclude(city__isnull=True).exclude(city__exact="").values_list("city", flat=True).distinct()
        categories = Category.objects.filter(is_active=True)
        total_ads = ads.count()
        pagination_query_params = request.GET.copy()
        pagination_query_params.pop("page", None)
        pagination_query = pagination_query_params.urlencode()


        ctx = {
            'ad_list': page_obj.object_list,
            'page_obj': page_obj,
            'favorites': favorites,
            'favorites_count': favorites_count,
            'my_ads_count': my_ads_count,
            'total_ads': total_ads,
            'search': strval,
            'cities': cities,
            'categories': categories,
            'number_of_ads':number_of_ads,
            'price_form': price_form,
            'number_per_page': number_per_page,
            'pagination_query': pagination_query,
        }

        retval = render(request, self.template_name, ctx)
        dump_queries()
        return retval



class AdDetailView(OwnerDetailView):
    model = Ad
    template_name = "ads/ad_detail.html"

    def get(self, request, pk) :
        x = get_object_or_404(Ad, id=pk)
        comments = Comment.objects.filter(ad=x).select_related('owner').order_by('-updated_at')
        comment_form = CommentForm()
        message_form = MessageForm()
        message_threads = []
        ad_unread_messages_count = 0
        other_ads = Ad.objects.filter(owner=x.owner).exclude(id=x.id).order_by('-updated_at')
        ad_photos = x.photos.order_by('-is_cover', 'sort_order', 'id')

        interested_ads = (
            Ad.objects
            .filter(Q(category=x.category) | Q(city=x.city))
            .exclude(id=x.id)
            .annotate(
                match_group=Case(
                    When(category=x.category, then=0),
                    When(city=x.city, then=1),
                    default=2,
                    output_field=IntegerField(),
                ),
                average_rating_db=Coalesce(
                    Avg("ratings__stars", distinct=True),
                    0.0,
                    output_field=FloatField(),
                ),
            )
        )
        if request.user.is_authenticated:
            interested_ads = interested_ads.exclude(owner=x.owner)
        interested_ads = interested_ads.order_by("match_group", "-average_rating_db", "-like_count", "-updated_at")[:10]

        favorites = []
        comment_favorites = []
        ad_user_rating = None
        all_comments_count = comments.count()
        liked_comments_count = 0
        comment_filter = request.GET.get('comments', 'all')

        if request.user.is_authenticated:
            favorites = [row['id'] for row in request.user.favorite_ads.values('id')]
            if request.user != x.owner:
                ad_user_rating = (
                    AdRating.objects
                    .filter(ad=x, user=request.user)
                    .values_list('stars', flat=True)
                    .first()
                )
            comment_favorites = [
                row['id'] for row in request.user.favorite_comments.filter(ad=x).values('id')
            ]
            liked_comments_count = len(comment_favorites)
            if comment_filter == 'liked':
                comments = comments.filter(id__in=comment_favorites)

            message_query = Message.objects.filter(ad=x).select_related('sender', 'recipient', 'ad', 'parent')
            if request.user == x.owner:
                ad_messages = list(message_query.order_by('-created_at'))
            else:
                ad_messages = list(message_query.filter(
                    Q(sender=request.user) | Q(recipient=request.user)
                ).order_by('-created_at'))

            thread_map = {}
            thread_order = []
            for msg in ad_messages:
                other_user = msg.sender if msg.sender != request.user else msg.recipient
                if other_user.id not in thread_map:
                    thread_map[other_user.id] = {
                        'user': other_user,
                        'messages': [],
                        'reply_target_message_id': None,
                    }
                    thread_order.append(other_user.id)
                thread_map[other_user.id]['messages'].append(msg)
                # Use latest incoming message from this sender as reply target.
                if (
                    request.user == x.owner
                    and msg.sender_id == other_user.id
                    and thread_map[other_user.id]['reply_target_message_id'] is None
                ):
                    thread_map[other_user.id]['reply_target_message_id'] = msg.id

            message_threads = [thread_map[user_id] for user_id in thread_order]
            ad_unread_messages_count = sum(
                1 for m in ad_messages if (m.recipient_id == request.user.id and not m.is_read)
            )

            Message.objects.filter(
                id__in=[m.id for m in ad_messages],
                recipient=request.user,
                is_read=False
            ).update(is_read=True)
        else:
            comment_filter = 'all'

        context = {
            'ad': x,
            'comments': comments,
            'comment_form': comment_form,
            'favorites': favorites,
            'ad_user_rating': ad_user_rating,
            'comment_favorites': comment_favorites,
            'comment_filter': comment_filter,
            'all_comments_count': all_comments_count,
            'liked_comments_count': liked_comments_count,
            'message_threads': message_threads,
            'ad_unread_messages_count': ad_unread_messages_count,
            'message_form': message_form,
            'other_ads': other_ads,
            'ad_photos': ad_photos,
            'interested_ads': interested_ads,
        }
        return render(request, self.template_name, context)


class AdCreateView(OwnerCreateView):
    model = Ad
    #fields = ['title','price','text', 'picture']
    template_name = 'ads/ad_form.html'
    success_url = reverse_lazy('ads:all')

    def get(self, request, pk=None):
        form = CreateForm()
        ctx = {'form': form, 'ad': None, 'ad_photos': []}
        return render(request, self.template_name, ctx)

    def post(self, request, pk=None):
        form = CreateForm(request.POST, request.FILES or None)

        if not form.is_valid():
            ctx = {'form': form, 'ad': None, 'ad_photos': []}
            return render(request, self.template_name, ctx)

        # Add owner to the model before saving
        ad = form.save(commit=False)
        ad.owner = self.request.user
        ad.save()

        uploaded_photos = request.FILES.getlist('photos')
        created_photo_ids = []
        current_count = ad.photos.count()
        for idx, image in enumerate(uploaded_photos):
            photo = AdPhoto.objects.create(
                ad=ad,
                image=image,
                sort_order=current_count + idx,
                is_cover=False,
            )
            created_photo_ids.append(photo.id)

        cover_photo_id = form.cleaned_data.get('cover_photo_id')
        if cover_photo_id:
            ad.photos.filter(is_cover=True).update(is_cover=False)
            ad.photos.filter(id=cover_photo_id).update(is_cover=True)
        elif created_photo_ids and not ad.photos.filter(is_cover=True).exists():
            ad.photos.filter(id=created_photo_ids[0]).update(is_cover=True)

        ad.sync_cover_from_photos()
        return redirect(self.success_url)



class AdUpdateView(OwnerUpdateView):
    model = Ad
    template_name = 'ads/ad_form.html'
    success_url = reverse_lazy('ads:all')

    def get(self, request, pk):
        ad = get_object_or_404(Ad, id=pk, owner=self.request.user)
        form = CreateForm(instance=ad)
        ctx = {'form': form, 'ad': ad, 'ad_photos': ad.photos.order_by('-is_cover', 'sort_order', 'id')}
        return render(request, self.template_name, ctx)

    def post(self, request, pk=None):
        ad = get_object_or_404(Ad, id=pk, owner=self.request.user)
        form = CreateForm(request.POST, request.FILES, instance=ad)

        if not form.is_valid():
            ctx = {'form': form, 'ad': ad, 'ad_photos': ad.photos.order_by('-is_cover', 'sort_order', 'id')}
            return render(request, self.template_name, ctx)

        ad = form.save(commit=False)
        ad.save()

        delete_photo_ids = form.get_delete_photo_ids()
        if delete_photo_ids:
            ad.photos.filter(id__in=delete_photo_ids).delete()

        uploaded_photos = request.FILES.getlist('photos')
        created_photo_ids = []
        current_count = ad.photos.count()
        for idx, image in enumerate(uploaded_photos):
            photo = AdPhoto.objects.create(
                ad=ad,
                image=image,
                sort_order=current_count + idx,
                is_cover=False,
            )
            created_photo_ids.append(photo.id)

        cover_photo_id = form.cleaned_data.get('cover_photo_id')
        if cover_photo_id and ad.photos.filter(id=cover_photo_id).exists():
            ad.photos.filter(is_cover=True).update(is_cover=False)
            ad.photos.filter(id=cover_photo_id).update(is_cover=True)
        elif created_photo_ids and not ad.photos.filter(is_cover=True).exists():
            ad.photos.filter(id=created_photo_ids[0]).update(is_cover=True)

        ad.sync_cover_from_photos()

        return redirect(self.success_url)


class AdDeleteView(OwnerDeleteView):
    model = Ad
    template_name = "ads/ad_confirm_delete.html"

def stream_file(request, pk):
    ad = get_object_or_404(Ad, id=pk)
    response = HttpResponse()
    response['Content-Type'] = ad.content_type
    response['Content-Length'] = len(ad.picture)
    response.write(ad.picture)
    return response

class CommentCreateView(LoginRequiredMixin, View):
    def post(self, request, pk) :
        ad = get_object_or_404(Ad, id=pk)
        form = CommentForm(request.POST)
        if form.is_valid():
            Comment.objects.create(
                text=form.cleaned_data['text'],
                owner=request.user,
                ad=ad
            )
        return redirect(reverse_lazy('ads:ad_detail', args=[pk]))

class CommentDeleteView(OwnerDeleteView):
    model = Comment
    template_name = "ads/ad_comment_delete.html"

    # https://stackoverflow.com/questions/26290415/deleteview-with-a-dynamic-success-url-dependent-on-id
    def get_success_url(self):
        ad = self.object.ad
        return reverse_lazy('ads:ad_detail', args=[ad.id])


class MessageCreateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        ad = get_object_or_404(Ad, id=pk)
        fallback_url = f"{reverse('ads:ad_detail', args=[pk])}#messages-panel"

        if ad.owner == request.user:
            return redirect(_get_safe_next_url(request, fallback_url))

        form = MessageForm(request.POST)
        if form.is_valid():
            message = Message(
                ad=ad,
                sender=request.user,
                recipient=ad.owner,
            )
            message.set_text(form.cleaned_data['encrypted_text'])
            message.save()

        return redirect(_get_safe_next_url(request, fallback_url))


class MessageReplyView(LoginRequiredMixin, View):
    def post(self, request, pk):
        source_message = get_object_or_404(Message.objects.select_related('ad', 'sender'), id=pk)
        ad = source_message.ad
        fallback_url = f"{reverse('ads:ad_detail', args=[ad.id])}#messages-panel"

        if request.user != ad.owner or source_message.sender == request.user:
            return HttpResponseForbidden('Only the ad owner can reply to incoming messages.')

        form = MessageForm(request.POST)
        if form.is_valid():
            reply = Message(
                ad=ad,
                sender=request.user,
                recipient=source_message.sender,
                parent=source_message,
            )
            reply.set_text(form.cleaned_data['encrypted_text'])
            reply.save()

        return redirect(_get_safe_next_url(request, fallback_url))


class MessageUpdateView(LoginRequiredMixin, View):
    template_name = "ads/message_edit.html"

    def get(self, request, pk):
        message_obj = get_object_or_404(Message.objects.select_related('ad', 'sender'), id=pk)
        if message_obj.sender_id != request.user.id:
            return HttpResponseForbidden("Only the sender can edit this message.")
        if message_obj.is_read:
            return HttpResponseForbidden("Only unread messages can be edited.")

        fallback_url = f"{reverse('ads:ad_detail', args=[message_obj.ad_id])}#messages-panel"
        cancel_url = _get_safe_next_url(request, fallback_url)
        form = MessageForm(initial={'encrypted_text': message_obj.text})
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "message_obj": message_obj,
                "cancel_url": cancel_url,
            },
        )

    def post(self, request, pk):
        message_obj = get_object_or_404(Message.objects.select_related('ad', 'sender'), id=pk)
        if message_obj.sender_id != request.user.id:
            return HttpResponseForbidden("Only the sender can edit this message.")
        if message_obj.is_read:
            return HttpResponseForbidden("Only unread messages can be edited.")

        fallback_url = f"{reverse('ads:ad_detail', args=[message_obj.ad_id])}#messages-panel"
        redirect_url = _get_safe_next_url(request, fallback_url)
        form = MessageForm(request.POST)
        if form.is_valid():
            message_obj.set_text(form.cleaned_data['encrypted_text'])
            message_obj.save()
            return redirect(redirect_url)

        return render(
            request,
            self.template_name,
            {
                "form": form,
                "message_obj": message_obj,
                "cancel_url": redirect_url,
            },
        )


class MessageDeleteView(LoginRequiredMixin, View):
    def get(self, request, pk):
        message_obj = get_object_or_404(Message.objects.select_related('ad', 'sender'), id=pk)
        if message_obj.sender_id != request.user.id:
            return HttpResponseForbidden("Only the sender can delete this message.")

        fallback_url = f"{reverse('ads:ad_detail', args=[message_obj.ad_id])}#messages-panel"
        return redirect(_get_safe_next_url(request, fallback_url))

    def post(self, request, pk):
        message_obj = get_object_or_404(Message.objects.select_related('ad', 'sender'), id=pk)
        if message_obj.sender_id != request.user.id:
            return HttpResponseForbidden("Only the sender can delete this message.")

        fallback_url = f"{reverse('ads:ad_detail', args=[message_obj.ad_id])}#messages-panel"
        next_url = _get_safe_next_url(request, fallback_url)
        message_obj.delete()
        return redirect(next_url)

# csrf exemption in class based views
# https://stackoverflow.com/questions/16458166/how-to-disable-djangos-csrf-validation
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.db.utils import IntegrityError

@method_decorator(csrf_exempt, name='dispatch')
class AddFavoriteView(LoginRequiredMixin, View):
    def post(self, request, pk) :
        print("Add PK",pk)
        t = get_object_or_404(Ad, id=pk)
        fav = Fav(user=request.user, ad=t)
        try:
            fav.save()  # In case of duplicate key
        except IntegrityError as e:
            pass

        t.like_count = Fav.objects.filter(ad=t).count()
        t.save(update_fields=['like_count'])

        return JsonResponse({"like_count": t.like_count})


@method_decorator(csrf_exempt, name='dispatch')
class DeleteFavoriteView(LoginRequiredMixin, View):
    def post(self, request, pk) :
        print("Delete PK",pk)
        t = get_object_or_404(Ad, id=pk)
        try:
            fav = Fav.objects.get(user=request.user, ad=t).delete()
        except Fav.DoesNotExist as e:
            pass

        t.like_count = Fav.objects.filter(ad=t).count()
        t.save(update_fields=['like_count'])


        return JsonResponse({"like_count": t.like_count})



@method_decorator(csrf_exempt, name='dispatch')
class AddCommentFavoriteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        comment = get_object_or_404(Comment, id=pk)
        fav = CommentFav(user=request.user, comment=comment)
        try:
            fav.save()
        except IntegrityError:
            pass
        return HttpResponse()


@method_decorator(csrf_exempt, name='dispatch')
class DeleteCommentFavoriteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        comment = get_object_or_404(Comment, id=pk)
        try:
            CommentFav.objects.get(user=request.user, comment=comment).delete()
        except CommentFav.DoesNotExist:
            pass
        return HttpResponse()


class FavoriteListView(LoginRequiredMixin, ListView):
    model = Ad
    template_name = 'ads/ad_list.html'
    context_object_name = 'ad_list'

    def get_queryset(self):
        return (
            Ad.objects
            .filter(fav__user=self.request.user)
            .annotate(
                average_rating_db=Coalesce(
                    Avg("ratings__stars"),
                    0.0,
                    output_field=FloatField()
                ),
                total_ratings_db=Count("ratings"),
            )
            .order_by("-updated_at")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # favorites_count for the badge
        rows = self.request.user.favorite_ads.values('id')
        ctx['favorites_count'] = len(rows)
        ctx['my_ads_count'] = Ad.objects.filter(owner=self.request.user).count()

        # also include the list of favorite IDs, same as in AdListView
        ctx['favorites'] = [row['id'] for row in rows]

        # search param placeholder (your template expects it)
        ctx['search'] = ""

        for obj in ctx['ad_list']:
            obj.natural_updated = naturaltime(obj.updated_at)

        return ctx


class MyAdListView(LoginRequiredMixin, ListView):
    model = Ad
    template_name = 'ads/ad_list.html'
    context_object_name = 'ad_list'

    def get_queryset(self):
        return (
            Ad.objects
            .filter(owner=self.request.user)
            .annotate(
                average_rating_db=Coalesce(
                    Avg("ratings__stars"),
                    0.0,
                    output_field=FloatField()
                ),
                total_ratings_db=Count("ratings"),
            )
            .order_by("-updated_at")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        rows = self.request.user.favorite_ads.values('id')
        ctx['favorites_count'] = len(rows)
        ctx['my_ads_count'] = ctx['ad_list'].count() if hasattr(ctx['ad_list'], 'count') else len(ctx['ad_list'])
        ctx['favorites'] = [row['id'] for row in rows]
        ctx['search'] = ""

        for obj in ctx['ad_list']:
            obj.natural_updated = naturaltime(obj.updated_at)

        return ctx
