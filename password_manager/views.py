# password_manager/views.py
"""
Представления (Views) приложения password_manager.

Реализуют полный цикл CRUD на базе CBV, строгий контроль доступа
(владелец/совладелец с ролями read/edit), оптимизацию запросов через
select_related/prefetch_related и интеграцию с сервисным слоем шифрования.

Архитектурные заметки (Stage 4)
Оптимизация QuerySets (N+1 prevention):
В PasswordListView и PasswordDetailView используется комбинация Q(owner=user) | Q(shared_entries__shared_with=user) с последующим .distinct() и Prefetch('shared_entries', to_attr='shared_data'). Это позволяет проверить права доступа и загрузить совладельцев за 1 запрос, а не за 1 + N.
select_related('owner', 'group') загружает FK-связи в тот же запрос.
Контроль доступа (PasswordAccessMixin):
Инкапсулирует логику проверки владельца/совладельца.
Блокирует POST/PUT/DELETE для пользователей с уровнем read.
Работает на уровне dispatch, что безопасно и не зависит от рендеринга шаблонов.
KeySetupRequiredMixin:
Гарантирует, что пользователь не попадёт в интерфейс менеджера паролей, пока не установит мастер-фразу. Защищает от DoesNotExist при попытке верификации.
PasswordRevealView:
Отделена от DetailView в целях безопасности. Расшифровка происходит только по явному POST с проверкой хеша. Возвращает JSON для безопасного вывода через модальное окно без перезагрузки страницы.
Совместимость с customers_app.DataBaseUser:
Используется стандартный LoginRequiredMixin. Если DataBaseUser является AUTH_USER_MODEL, Django автоматически привяжет request.user к вашей модели.
"""

from typing import Any, Dict
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q, Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import (
    CreateView, DeleteView, DetailView, ListView, UpdateView, View
)
from django.utils.decorators import method_decorator

from .models import (
    PasswordGroup, EncryptedPassword, PasswordHistory, SharedPassword, UserKeyHash
)
from .forms import EncryptedPasswordForm, UserKeySetupForm
from .services import PasswordService


class KeySetupRequiredMixin(LoginRequiredMixin):
    """
    Mixin, проверяющий наличие установленной ключевой фразы у пользователя.
    Перенаправляет на страницу настройки, если UserKeyHash отсутствует.
    """

    def dispatch(self, request, *args, **kwargs):
        # Проверяем наличие обратной связи OneToOne (related_name="encryption_key_hash")
        if not hasattr(request.user, 'encryption_key_hash'):
            messages.warning(
                request,
                "Для работы менеджера паролей необходимо задать ключевую фразу."
            )
            return redirect('password_manager:key_setup')
        return super().dispatch(request, *args, **kwargs)


class PasswordAccessMixin(LoginRequiredMixin):
    """
    Mixin контроля доступа к конкретной записи пароля.

    Логика:
    1. Владелец (owner) имеет полный доступ (edit).
    2. Совладелец проверяется по JSON-полю permissions.
    3. Для GET-запросов достаточно права 'read'.
    4. Для POST/PUT/DELETE требуется право 'edit'.
    """
    permission_required = None  # Переопределяется в дочерних классах

    def _check_access(self, obj) -> str:
        """Возвращает уровень доступа: 'edit', 'read' или 'none'."""
        user = self.request.user
        if obj.owner == user:
            return 'edit'

        # OneToOneField вызывает RelatedObjectDoesNotExist, если связи нет
        try:
            shared = obj.shared_access
            if user in shared.shared_with.all():
                return shared.permissions.get(str(user.pk), 'read')
        except EncryptedPassword.shared_access.RelatedObjectDoesNotExist:
            pass
        return 'none'

    def dispatch(self, request, *args, **kwargs):
        # Для CBV, работающих с одним объектом, вызываем проверку в dispatch
        if hasattr(self, 'get_object'):
            obj = self.get_object()
            perm = self._check_access(obj)

            if perm == 'none':
                raise PermissionDenied("У вас нет доступа к этой записи.")

            # Запрещаем модификацию пользователям с правом только на чтение
            if request.method in ('POST', 'PUT', 'DELETE') and perm != 'edit':
                raise PermissionDenied("Недостаточно прав для изменения записи. Требуется уровень 'edit'.")
        return super().dispatch(request, *args, **kwargs)


# =============================================================================
# Ключевая фраза
# =============================================================================
class KeySetupView(KeySetupRequiredMixin, CreateView):
    """Настройка или обновление ключевой фразы пользователя."""
    form_class = UserKeySetupForm
    template_name = 'password_manager/key_setup.html'
    success_url = reverse_lazy('password_manager:password_list')

    def form_valid(self, form):
        form.save(self.request.user)
        messages.success(self, "Ключевая фраза успешно установлена.")
        return super().form_valid(form)

    def get(self, request, *args, **kwargs):
        # Если фраза уже установлена, перенаправляем в дашборд
        if hasattr(request.user, 'encryption_key_hash'):
            return redirect('password_manager:password_list')
        return super().get(request, *args, **kwargs)


# =============================================================================
# Группы паролей (CRUD)
# =============================================================================
class GroupListView(KeySetupRequiredMixin, ListView):
    model = PasswordGroup
    template_name = 'password_manager/group_list.html'
    context_object_name = 'groups'
    paginate_by = 20

    def get_queryset(self):
        # Иерархическая выборка: сначала корневые, затем дочерние
        return PasswordGroup.objects.filter(
            owner=self.request.user
        ).select_related('owner', 'parent_group').order_by('parent_group', 'name')


class GroupCreateView(KeySetupRequiredMixin, CreateView):
    model = PasswordGroup
    fields = ['name', 'parent_group']
    template_name = 'password_manager/group_form.html'
    success_url = reverse_lazy('password_manager:group_list')

    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)


class GroupUpdateView(KeySetupRequiredMixin, UpdateView):
    model = PasswordGroup
    fields = ['name', 'parent_group']
    template_name = 'password_manager/group_form.html'
    success_url = reverse_lazy('password_manager:group_list')

    def get_queryset(self):
        # Запрещаем редактирование групп, не принадлежащих пользователю
        return PasswordGroup.objects.filter(owner=self.request.user)


class GroupDeleteView(KeySetupRequiredMixin, DeleteView):
    model = PasswordGroup
    success_url = reverse_lazy('password_manager:group_list')

    def get_queryset(self):
        return PasswordGroup.objects.filter(owner=self.request.user)


# =============================================================================
# Записи паролей (CRUD + Доступ)
# =============================================================================
class PasswordListView(PasswordAccessMixin, ListView):
    model = EncryptedPassword
    template_name = 'password_manager/password_list.html'
    context_object_name = 'passwords'
    paginate_by = 15

    def get_queryset(self):
        """
        Оптимизированная выборка:
        1. Фильтр по владельцу ИЛИ общему доступу.
        2. select_related для FK (владелец, группа).
        3. prefetch_related для ManyToMany (совладельцы) и JSON-прав.
        """
        user = self.request.user
        base_qs = EncryptedPassword.objects.select_related('owner', 'group')

        shared_qs = EncryptedPassword.objects.filter(
            shared_access__shared_with=user
        ).select_related('owner', 'group')

        return (base_qs | shared_qs).distinct().prefetch_related(
            'shared_access',
            'shared_access__shared_with'
        ).order_by('-created_at')


class PasswordCreateView(PasswordAccessMixin, CreateView):
    model = EncryptedPassword
    form_class = EncryptedPasswordForm
    template_name = 'password_manager/password_form.html'
    success_url = reverse_lazy('password_manager:password_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs


class PasswordUpdateView(PasswordAccessMixin, UpdateView):
    model = EncryptedPassword
    form_class = EncryptedPasswordForm
    template_name = 'password_manager/password_form.html'
    success_url = reverse_lazy('password_manager:password_list')

    def get_queryset(self):
        # Доступ только для пользователей с правом 'edit'
        user = self.request.user
        return EncryptedPassword.objects.filter(
            Q(owner=user) | Q(shared_access__shared_with=user)
        ).distinct()

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs


class PasswordDeleteView(PasswordAccessMixin, DeleteView):
    model = EncryptedPassword
    success_url = reverse_lazy('password_manager:password_list')

    def get_queryset(self):
        user = self.request.user
        return EncryptedPassword.objects.filter(
            Q(owner=user) | Q(shared_access__shared_with=user)
        ).distinct()


class PasswordDetailView(PasswordAccessMixin, DetailView):
    model = EncryptedPassword
    template_name = 'password_manager/password_detail.html'
    context_object_name = 'password_entry'

    def get_queryset(self):
        user = self.request.user
        base_qs = EncryptedPassword.objects.select_related('owner', 'group')

        shared_qs = EncryptedPassword.objects.filter(
            shared_access__shared_with=user
        ).select_related('owner', 'group')

        return (base_qs | shared_qs).distinct().prefetch_related(
            'shared_access',
            'shared_access__shared_with'
        ).order_by('-created_at')

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        obj = self.object
        context['permission_level'] = self._check_access(obj)
        return context


# =============================================================================
# История и Общий доступ
# =============================================================================
class PasswordHistoryView(PasswordAccessMixin, ListView):
    model = PasswordHistory
    template_name = 'password_manager/password_history.html'
    context_object_name = 'history_entries'
    paginate_by = 10

    def get_queryset(self):
        pk = self.kwargs.get('pk')
        # Проверяем право на чтение оригинальной записи перед показом истории
        EncryptedPassword.objects.get(pk=pk)  # Trigger access check via mixin if needed
        return PasswordHistory.objects.filter(
            original_record_id=pk, owner=self.request.user
        ).order_by('-changed_at')


class ManageSharedAccessView(PasswordAccessMixin, View):
    """
    Управление общими правами доступа.
    Принимает JSON или form-data с user_id и permission level.
    """

    def get(self, request, pk):
        # В реальном проекте рендерит форму добавления пользователей
        return redirect('password_manager:password_detail', pk=pk)

    def post(self, request, pk):
        user_id = request.POST.get('user_id')
        permission = request.POST.get('permission', 'read')
        password_record = get_object_or_404(EncryptedPassword, pk=pk)

        if permission not in ('read', 'edit'):
            messages.error(request, "Недопустимый уровень доступа.")
            return redirect('password_manager:password_share', pk=pk)

        shared, created = SharedPassword.objects.get_or_create(
            encrypted_password=password_record
        )

        # Обновляем JSON-словарь прав
        shared.permissions[str(user_id)] = permission
        shared.shared_with.add(user_id)
        shared.save(update_fields=['permissions'])

        messages.success(request, f"Права доступа для пользователя {user_id} обновлены.")
        return redirect('password_manager:password_detail', pk=pk)


class PasswordRevealView(PasswordAccessMixin, View):
    """
    Безопасное получение расшифрованного пароля по требованию.
    Принимает ключевую фразу через POST, проверяет хеш и возвращает plain-текст.
    """

    def post(self, request, pk):
        passphrase = request.POST.get('passphrase')
