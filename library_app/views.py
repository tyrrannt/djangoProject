from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError
from django.db.models import Q
from django.http import JsonResponse, HttpResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from loguru import logger

from administration_app.models import PortalProperty
from customers_app.models import DataBaseUser
from djangoProject import settings
from hrdepartment_app.models import DocumentAcknowledgment
from library_app.forms import (
    HelpItemAddForm,
    HelpItemUpdateForm,
    DocumentFormAddForm,
    DocumentFormUpdateForm, PoemForm, VoteConfirmationForm, CompanyEventForm,
)
from library_app.models import HelpTopic, HelpCategory, DocumentForm, Contest, Poem, Vote, CompanyEvent


# Create your views here.
# logger.add("debug.json", format=config('LOG_FORMAT'), level=config('LOG_LEVEL'),
#            rotation=config('LOG_ROTATION'), compression=config('LOG_COMPRESSION'),
#            serialize=config('LOG_SERIALIZE'))


def index(request):
    # return render(request, 'library_app/base.html')
    return redirect("/users/login/")


def check_session_cookie_secure(request):
    if settings.SESSION_COOKIE_SECURE:
        return HttpResponse("SESSION_COOKIE_SECURE is enabled.")
    else:
        return HttpResponse("SESSION_COOKIE_SECURE is not enabled.")


def show_403(request, exception=None):
    return render(request, "library_app/403.html")


def show_404(request, exception=None):
    return render(request, "library_app/404.html")


def show_500(request, exception=None):
    return render(request, "library_app/500.html")


class HelpList(LoginRequiredMixin, ListView):
    model = HelpTopic

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context["help_category"] = HelpCategory.objects.all()
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Справка"
        return context

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            helptopic_list = HelpTopic.objects.all()
            data = [helptopic_item.get_data() for helptopic_item in helptopic_list]
            response = {"data": data}
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)


class HelpItem(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = HelpTopic
    permission_required = "library_app.view_helptopic"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // {self.get_object()}"
        return context


class HelpItemAdd(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
    model = HelpTopic
    form_class = HelpItemAddForm
    permission_required = "library_app.add_helptopic"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Добавить справку"
        return context


class HelpItemUpdate(PermissionRequiredMixin, LoginRequiredMixin, UpdateView):
    model = HelpTopic
    form_class = HelpItemUpdateForm
    permission_required = "library_app.change_helptopic"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Редактирование: {self.get_object()}"
        return context


class DocumentFormList(LoginRequiredMixin, ListView):
    model = DocumentForm

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context["help_category"] = DocumentForm.objects.all()
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Бланки документов"
        return context

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            if self.request.user.is_superuser or self.request.user.is_staff:
                dcumentform_list = DocumentForm.objects.all()
            else:
                dcumentform_list = DocumentForm.objects.filter(
                    Q(division__code__icontains=self.request.user.user_work_profile.divisions.code) |
                    Q(division=None))
            data = [
                dcumentform_item.get_data() for dcumentform_item in dcumentform_list
            ]
            response = {"data": data}
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)


@method_decorator(never_cache, name='dispatch')
class DocumentFormItem(PermissionRequiredMixin, LoginRequiredMixin, DetailView):
    model = DocumentForm
    permission_required = "library_app.view_documentform"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // {self.get_object()}"
        return context


class DocumentFormAdd(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
    model = DocumentForm
    form_class = DocumentFormAddForm
    permission_required = "library_app.add_documentform"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Добавить бланк"
        return context

    def get_success_url(self):
        return reverse_lazy("library_app:blank_list")

    def get_form_kwargs(self):
        """
        Передаем в форму текущего пользователя. В форме переопределяем метод __init__
        :return: PK текущего пользователя
        """
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user.pk})
        return kwargs


class DocumentFormUpdate(PermissionRequiredMixin, LoginRequiredMixin, UpdateView):
    model = DocumentForm
    form_class = DocumentFormUpdateForm
    template_name = "library_app/documentform_form_update.html"
    permission_required = "library_app.change_documentform"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Редактирование: {self.get_object()}"
        return context

    def get_success_url(self):
        return reverse("library_app:blank", kwargs={"pk": self.object.pk})

    def get_form_kwargs(self):
        """
        Передаем в форму текущего пользователя. В форме переопределяем метод __init__
        :return: PK текущего пользователя
        """
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user.pk})
        return kwargs


@login_required
def video(request):
    types_count = ''

    return render(request, 'library_app/video.html', context={'types_count': types_count})


@login_required
def submit_poem(request):
    contest = Contest.objects.latest('start_date')
    if not contest.is_submission_open():
        return render(request, 'library_app/contest_closed.html')

    try:
        poem = Poem.objects.get(user=request.user, contest=contest)
    except Poem.DoesNotExist:
        poem = None

    if request.method == 'POST':
        form = PoemForm(request.POST, instance=poem)
        if form.is_valid():
            poem = form.save(commit=False)
            poem.user = request.user
            poem.contest = contest
            poem.save()
            return redirect('library_app:submit_poem')
    else:
        form = PoemForm(instance=poem)

    return render(request, 'library_app/submit_poem.html', {'form': form})


@login_required
def vote(request):
    contest = Contest.objects.latest('start_date')
    vote_count = Vote.objects.all().count()

    vote_days = contest.voting_end_date.day - datetime.today().day
    if not request.user.is_superuser:
        if not contest.is_voting_open():
            return render(request, 'library_app/voting_closed.html')
    admin_user = DataBaseUser.objects.get(pk=314)
    poems = Poem.objects.filter(contest=contest).order_by('?')
    if request.method == 'POST':
        poem_id = request.POST.get('poem')
        poem = get_object_or_404(Poem, id=poem_id)
        try:
            if Vote.objects.filter(user=request.user).exists():
                raise Exception('Вы уже голосовали')
            Vote.objects.create(user=request.user, poem=poem)
            return render(request, 'library_app/vote_success.html', {'poem': poem, 'admin_user': admin_user, 'poem_count': len(poems), 'vote_count': vote_count, 'vote_days': vote_days})
        except Exception as _ex:
            my_vote = Vote.objects.get(user=request.user)
            return render(request, 'library_app/vote_success.html', {'poem': poem, 'admin_user': admin_user, 'poem_count': len(poems), 'vote_count': vote_count, 'my_vote': my_vote, 'vote_days': vote_days})

    return render(request, 'library_app/vote.html', {'poems': poems})


@login_required
def vote_success(request):
    admin_user = DataBaseUser.objects.get(pk=314)
    return render(request, 'library_app/vote_success.html', {'admin_user': admin_user})


@login_required
def results(request):
    contest = Contest.objects.latest('start_date')
    poems = Poem.objects.filter(contest=contest)
    votes = Vote.objects.filter(poem__in=poems)

    # Подсчет голосов
    vote_count = {}
    for vote in votes:
        if vote.poem.id in vote_count:
            vote_count[vote.poem.id] += 1
        else:
            vote_count[vote.poem.id] = 1

    # Сортировка по количеству голосов
    sorted_poems = sorted(poems, key=lambda x: vote_count.get(x.id, 0), reverse=True)

    return render(request, 'library_app/results.html', {'poems': sorted_poems[:3]})


@login_required
def video_conference(request, room_name):
    return render(request, 'library_app/video_conference.html', {'room_name': room_name})


@login_required
def audio_conference(request, room_name):
    return render(request, 'library_app/audio_conference.html', {'room_name': room_name})


class CompanyEventListView(LoginRequiredMixin, ListView):
    model = CompanyEvent
    context_object_name = 'events'

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            provisions_list = CompanyEvent.objects.all().order_by('event_date')
            data = [provisions_item.get_data() for provisions_item in provisions_list]
            response = {"data": data}
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Мероприятия компании"
        return context


class CompanyEventDetailView(LoginRequiredMixin, DetailView):
    model = CompanyEvent
    context_object_name = 'event'

    def get_context_data(self, **kwargs):
        # context = super().get_context_data(**kwargs)
        context = super().get_context_data(object_list=None, **kwargs)
        content_type_id = ContentType.objects.get_for_model(self.object).id
        document_id = self.object.id
        user = self.request.user
        agree = DocumentAcknowledgment.objects.filter(document_type=content_type_id, document_id=document_id,
                                                      user=user).exists()
        list_agree = DocumentAcknowledgment.objects.filter(document_type=content_type_id, document_id=document_id).order_by('user')
        context['list_agree'] = list_agree
        context['agree'] = agree
        context['title'] = f"{PortalProperty.objects.all().last().portal_name} // Просмотр - {self.get_object()}"
        return context


class CompanyEventUpdateView(PermissionRequiredMixin, LoginRequiredMixin, UpdateView):
    model = CompanyEvent
    form_class = CompanyEventForm
    permission_required = "library_app.change_companyevent"
    success_url = reverse_lazy('library_app:event_list')


class CompanyEventDeleteView(PermissionRequiredMixin, LoginRequiredMixin, DeleteView):
    model = CompanyEvent
    permission_required = "library_app.delete_companyevent"
    success_url = reverse_lazy('library_app:event_list')


class CompanyEventCreateView(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
    model = CompanyEvent
    form_class = CompanyEventForm
    permission_required = "library_app.add_companyevent"
    success_url = reverse_lazy('library_app:event_list')
