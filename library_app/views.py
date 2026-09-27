import uuid
from datetime import datetime
from typing import Any, Optional, Dict

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.http import (
    JsonResponse,
    HttpResponse,
    HttpRequest,
    HttpResponseForbidden,
    HttpResponseNotFound,
    HttpResponseServerError,
    HttpResponseBadRequest,
)
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView

from administration_app.models import PortalProperty
from customers_app.models import DataBaseUser
from djangoProject import settings
from hrdepartment_app.models import DocumentAcknowledgment
from library_app.forms import (
    HelpItemAddForm,
    HelpItemUpdateForm,
    DocumentFormAddForm,
    DocumentFormUpdateForm, PoemForm, CompanyEventForm,
)
from library_app.models import HelpTopic, HelpCategory, DocumentForm, Contest, Poem, Vote, CompanyEvent

from core import logger


def index(request):
    # return render(request, 'library_app/base.html')
    return redirect("/users/login/")


def check_session_cookie_secure(request):
    if settings.SESSION_COOKIE_SECURE:
        return HttpResponse("SESSION_COOKIE_SECURE is enabled.")
    else:
        return HttpResponse("SESSION_COOKIE_SECURE is not enabled.")


def show_400(request: HttpRequest, exception: Any = None) -> HttpResponse:
    """Обработчик ошибки HTTP 400 (Bad Request).

    Отображает брендированную страницу при некорректных параметрах запроса или сбое валидации.

    Args:
        request (HttpRequest): Объект HTTP-запроса.
        exception (Any, optional): Исключение, вызвавшее ошибку 400.

    Returns:
        HttpResponse: Срендеренная страница ошибки со статусом 400.
    """
    logger.warning(
        f"400 Bad Request: {request.path} | User: {getattr(request, 'user', 'Anonymous')} | "
        f"Exception: {exception}"
    )
    context = {
        "title": "400 Некорректный запрос",
        "error_code": "400",
        "error_name": "Bad Request",
        "error_title": "Некорректный запрос",
        "error_description": "Сервер не смог обработать входящий запрос из-за неверного синтаксиса, некорректных параметров или поврежденных данных.",
        "request_path": getattr(request, "path", ""),
        "exception_msg": str(exception) if exception else "",
    }
    return render(request, "library_app/400.html", context, status=400)


def show_403(request: HttpRequest, exception: Any = None) -> HttpResponse:
    """Обработчик ошибки HTTP 403 (Forbidden).

    Отображает брендированную страницу ограничения прав доступа с предложением действий.

    Args:
        request (HttpRequest): Объект HTTP-запроса.
        exception (Any, optional): Исключение PermissionDenied или описание причины.

    Returns:
        HttpResponse: Срендеренная страница ошибки со статусом 403.
    """
    logger.warning(
        f"403 Forbidden: {request.path} | User: {getattr(request, 'user', 'Anonymous')} | "
        f"Exception: {exception}"
    )
    context = {
        "title": "403 Доступ ограничен",
        "error_code": "403",
        "error_name": "Access Forbidden",
        "error_title": "Доступ ограничен",
        "error_description": "У вашей учетной записи недостаточно прав для просмотра этого раздела или выполнения данной операции.",
        "request_path": getattr(request, "path", ""),
        "exception_msg": str(exception) if exception else "",
    }
    return render(request, "library_app/403.html", context, status=403)


def csrf_failure(request: HttpRequest, reason: str = "") -> HttpResponse:
    """Обработчик ошибки проверки CSRF токена.

    Отображает дружелюбную страницу с понятным объяснением и кнопкой быстрого обновления страницы.

    Args:
        request (HttpRequest): Объект HTTP-запроса.
        reason (str, optional): Техническая причина отклонения CSRF-токена.

    Returns:
        HttpResponse: Срендеренная страница ошибки со статусом 403.
    """
    logger.warning(
        f"403 CSRF Failure: {request.path} | User: {getattr(request, 'user', 'Anonymous')} | "
        f"Reason: {reason}"
    )
    context = {
        "title": "Срок действия формы истек",
        "error_code": "CSRF",
        "error_name": "Token Expired",
        "error_title": "Срок действия формы истек",
        "error_description": "Защитный токен формы устарел или был сброшен из-за длительного ожидания. Пожалуйста, обновите страницу и отправьте форму заново.",
        "request_path": getattr(request, "path", ""),
        "reason": reason,
    }
    return render(request, "library_app/csrf_failure.html", context, status=403)


def show_404(request: HttpRequest, exception: Any = None) -> HttpResponse:
    """Обработчик ошибки HTTP 404 (Not Found).

    Отображает брендированную страницу отсутствия запрашиваемого ресурса с навигацией.

    Args:
        request (HttpRequest): Объект HTTP-запроса.
        exception (Any, optional): Исключение Http404 или описание.

    Returns:
        HttpResponse: Срендеренная страница ошибки со статусом 404.
    """
    logger.warning(
        f"404 Not Found: {request.path} | User: {getattr(request, 'user', 'Anonymous')} | "
        f"Exception: {exception}"
    )
    context = {
        "title": "404 Страница не найдена",
        "error_code": "404",
        "error_name": "Page Not Found",
        "error_title": "Страница не найдена",
        "error_description": "Запрашиваемый адрес не существует на сервере, документ был перемещен или в ссылке допущена опечатка.",
        "request_path": getattr(request, "path", ""),
    }
    return render(request, "library_app/404.html", context, status=404)


def show_500(request: HttpRequest, exception: Any = None) -> HttpResponse:
    """Обработчик ошибки HTTP 500 (Internal Server Error).

    Отображает защищенную автономную брендированную страницу ошибки сервера
    с уникальным идентификатором инцидента для передачи в техподдержку.

    Args:
        request (HttpRequest): Объект HTTP-запроса.
        exception (Any, optional): Необработанное исключение.

    Returns:
        HttpResponse: Срендеренная страница ошибки со статусом 500.
    """
    incident_id = f"BARKOL-500-{uuid.uuid4().hex[:8].upper()}"
    logger.error(
        f"500 Internal Server Error [{incident_id}]: {getattr(request, 'path', 'unknown')} | "
        f"User: {getattr(request, 'user', 'Anonymous')} | Exception: {exception}",
        exc_info=True,
    )
    context = {
        "title": "500 Ошибка сервера",
        "error_code": "500",
        "error_name": "Internal Server Error",
        "error_title": "Внутренняя ошибка сервера",
        "error_description": "Произошел непредвиденный системный сбой при обработке вашего запроса. Инженеры уже уведомлены, и подробности инцидента зафиксированы в системном журнале.",
        "incident_id": incident_id,
        "request_path": getattr(request, "path", ""),
    }
    try:
        from django.template.loader import render_to_string
        content = render_to_string("library_app/500.html", context)
        return HttpResponseServerError(content)
    except Exception as render_exc:
        logger.critical(f"Failed to render 500 template: {render_exc}")
        return HttpResponseServerError(
            f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>500 Ошибка сервера</title></head>"
            f"<body style='font-family:sans-serif;text-align:center;padding:50px;background:#f8fafc;color:#002b49;'>"
            f"<h1>500 Внутренняя ошибка сервера</h1>"
            f"<p>Код инцидента: <b>{incident_id}</b></p>"
            f"<p>Технические службы уведомлены о сбое.</p></body></html>",
            content_type="text/html; charset=utf-8",
        )


def show_503(request: HttpRequest, exception: Any = None) -> HttpResponse:
    """Обработчик ошибки HTTP 503 (Service Unavailable / Maintenance).

    Отображает брендированную страницу регламентных работ и технического обслуживания с автообновлением.

    Args:
        request (HttpRequest): Объект HTTP-запроса.
        exception (Any, optional): Исключение или описание режима обслуживания.

    Returns:
        HttpResponse: Срендеренная страница ошибки со статусом 503.
    """
    logger.info(
        f"503 Service Unavailable: {getattr(request, 'path', '')} | User: {getattr(request, 'user', 'Anonymous')}"
    )
    context = {
        "title": "503 Техническое обслуживание",
        "error_code": "503",
        "error_name": "Service Unavailable",
        "error_title": "Техническое обслуживание",
        "error_description": "На портале проводятся плановые регламентные работы или обновление системных компонентов. Доступ будет автоматически восстановлен через несколько минут.",
        "request_path": getattr(request, "path", ""),
    }
    try:
        from django.template.loader import render_to_string
        content = render_to_string("library_app/503.html", context)
        response = HttpResponse(content, status=503)
        response["Retry-After"] = "30"
        return response
    except Exception as render_exc:
        logger.critical(f"Failed to render 503 template: {render_exc}")
        return HttpResponse("<h1>503 Техническое обслуживание</h1>", status=503)


class HelpList(LoginRequiredMixin, ListView):
    model = HelpTopic

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context["help_category"] = HelpCategory.objects.all()
        context["title"] = f"Справка"
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
        context["title"] = f"{self.get_object()}"
        return context


class HelpItemAdd(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
    model = HelpTopic
    form_class = HelpItemAddForm
    permission_required = "library_app.add_helptopic"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = f"Добавить справку"
        return context


class HelpItemUpdate(PermissionRequiredMixin, LoginRequiredMixin, UpdateView):
    model = HelpTopic
    form_class = HelpItemUpdateForm
    permission_required = "library_app.change_helptopic"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = f"Редактирование: {self.get_object()}"
        return context


class DocumentFormList(LoginRequiredMixin, ListView):
    model = DocumentForm

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context["help_category"] = DocumentForm.objects.all()
        context["title"] = f"Бланки документов"
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
        context["title"] = f"{self.get_object()}"
        return context


class DocumentFormAdd(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
    model = DocumentForm
    form_class = DocumentFormAddForm
    permission_required = "library_app.add_documentform"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = f"Добавить бланк"
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
        context["title"] = f"Редактирование: {self.get_object()}"
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
    admin_user = DataBaseUser.objects.get(pk=52)
    poems = Poem.objects.filter(contest=contest).order_by('?').exclude(user__is_active=False)
    if request.method == 'POST':
        poem_id = request.POST.get('poem')
        poem = get_object_or_404(Poem, id=poem_id)
        try:
            if Vote.objects.filter(user=request.user).exists():
                raise Exception('Вы уже голосовали')
            Vote.objects.create(user=request.user, poem=poem)
            return render(request, 'library_app/vote_success.html',
                          {'poem': poem, 'admin_user': admin_user, 'poem_count': len(poems), 'vote_count': vote_count,
                           'vote_days': vote_days})
        except Exception as _ex:
            my_vote = Vote.objects.get(user=request.user)
            return render(request, 'library_app/vote_success.html',
                          {'poem': poem, 'admin_user': admin_user, 'poem_count': len(poems), 'vote_count': vote_count,
                           'my_vote': my_vote, 'vote_days': vote_days})

    return render(request, 'library_app/vote.html', {'poems': poems})


@login_required
def vote_success(request):
    admin_user = DataBaseUser.objects.get(pk=52)
    return render(request, 'library_app/vote_success.html', {'admin_user': admin_user})


@login_required
def results(request):
    contest = Contest.objects.latest('start_date')
    poems = Poem.objects.filter(contest=contest)
    votes = Vote.objects.filter(poem__in=poems)

    # Подсчет голосов для каждого стиха
    vote_count = {}
    for vote in votes:
        vote_count[vote.poem.id] = vote_count.get(vote.poem.id, 0) + 1

    # Сортировка стихов по количеству голосов в порядке убывания
    sorted_poems = sorted(poems, key=lambda x: vote_count.get(x.id, 0), reverse=True)

    # Группировка стихов по местам с учетом количества голосов
    grouped_poems = []
    current_votes = None
    users_vote = {}
    for poem in poems:
        users_vote[poem.pk] = Vote.objects.filter(poem=poem)

    for poem in sorted_poems:
        votes = vote_count.get(poem.id, 0)
        if votes != current_votes:
            # Если количество голосов изменилось, добавляем новое место
            current_votes = votes
            grouped_poems.append({
                'votes': votes,  # Количество голосов для текущего места
                'poems': {}  # Словарь стихов для текущего места
            })
        # Добавляем стих в словарь текущего места
        grouped_poems[-1]['poems'][poem.id] = poem
    return render(request, 'library_app/results.html', {'grouped_poems': grouped_poems, 'users_vote': users_vote})


class CompanyEventListView(LoginRequiredMixin, ListView):
    model = CompanyEvent
    context_object_name = 'events'

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            provisions_list = CompanyEvent.objects.all().order_by('-event_date')
            data = [provisions_item.get_data() for provisions_item in provisions_list]
            response = {"data": data}
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context["title"] = f"Мероприятия компании"
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
        list_agree = DocumentAcknowledgment.objects.filter(document_type=content_type_id,
                                                           document_id=document_id).order_by('user')
        context['list_agree'] = list_agree
        context['agree'] = agree
        context['title'] = f"{self.get_object()}"
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
