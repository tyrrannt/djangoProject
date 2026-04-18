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
import json
from typing import Any, Dict
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q, Prefetch
from django.http import JsonResponse, Http404
from django.utils.translation import gettext_lazy as _
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import (
    CreateView, DeleteView, DetailView, ListView, UpdateView, View, FormView
)
from django.utils.decorators import method_decorator
from core import logger

from .models import (
    PasswordGroup, EncryptedPassword, PasswordHistory, SharedPassword, UserKeyHash
)
from .forms import EncryptedPasswordForm, UserKeySetupForm, PasswordGroupForm
from .services import PasswordService


class KeySetupRequiredMixin(LoginRequiredMixin):
    """
    Mixin, проверяющий наличие установленной ключевой фразы у пользователя.
    Перенаправляет на страницу настройки, если UserKeyHash отсутствует.
    """

    def dispatch(self, request, *args, **kwargs):
        # 1. Явная проверка аутентификации ДО любой логики
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        # 2. Проверяем наличие обратной связи OneToOne (related_name="encryption_key_hash")
        if not hasattr(request.user, 'encryption_key_hash'):
            messages.warning(
                request,
                "Для работы менеджера паролей необходимо задать ключевую фразу. 1"
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
    is_create_view = False  # Маркер для представлений создания

    def _check_access(self, obj) -> str:
        """Возвращает уровень доступа: 'edit', 'read' или 'none'."""
        user = self.request.user
        if obj.owner == user:
            return 'edit'

        if user.is_superuser:
            return 'admin'

        # Проверяем общий доступ через shared_access
        try:
            if hasattr(obj, 'shared_access') and obj.shared_access:
                if user in obj.shared_access.shared_with.all():
                    # Предполагается, что permissions - это JSONField
                    permissions = obj.shared_access.permissions or {}
                    return permissions.get(str(user.pk), 'read')
        except Exception:
            pass
        return 'none'

    def get_access_object(self):
        """Получает объект для проверки доступа."""
        if hasattr(self, 'get_object'):
            try:
                return self.get_object()
            except AttributeError:
                return None
        return None

    def dispatch(self, request, *args, **kwargs):
        # 1. Явная проверка аутентификации ДО любой логики
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        # 2. Для представлений создания пропускаем проверку объекта
        if getattr(self, 'is_create_view', False):
            return super().dispatch(request, *args, **kwargs)

        # 3. Проверка прав на существующий объект
        obj = self.get_access_object()

        # Если объект найден, проверяем доступ
        if obj:
            access_level = self._check_access(obj)

            if access_level == 'none':
                raise PermissionDenied("У вас нет доступа к этой записи.")

            # Для изменяющих HTTP-методов требуем право 'edit' или 'admin'
            if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
                # Разрешаем POST только если это 'edit'/'admin'
                # ИЛИ если это конкретное действие 'reveal' при наличии права 'read'
                is_reveal_path = request.resolver_match.url_name == 'password_reveal'

                if access_level not in ('edit', 'admin'):
                    if not (access_level == 'read' and is_reveal_path):
                        raise PermissionDenied("Недостаточно прав для изменения записи.")

            # 4. Продолжение стандартного потока Django
        return super().dispatch(request, *args, **kwargs)


# =============================================================================
# Ключевая фраза
# =============================================================================
class KeySetupView(FormView):
    """Настройка или обновление ключевой фразы пользователя."""
    form_class = UserKeySetupForm
    template_name = 'password_manager/key_setup.html'
    success_url = reverse_lazy('password_manager:password_list')

    def form_valid(self, form):
        form.save(self.request.user)
        messages.success(self.request, "Ключевая фраза успешно установлена.")
        return super().form_valid(form)

    def get(self, request, *args, **kwargs):
        # Если фраза уже установлена, перенаправляем в список паролей
        if hasattr(request.user, 'encryption_key_hash') and request.user.encryption_key_hash:
            return redirect('password_manager:password_list')
        return super().get(request, *args, **kwargs)


# =============================================================================
# Группы паролей (CRUD)
# =============================================================================
class GroupTreeDataView(LoginRequiredMixin, View):
    """API для получения групп в формате дерева jsTree"""

    def get(self, request):
        # Получаем корневые группы (без родителя)
        root_groups = PasswordGroup.objects.filter(
            owner=request.user,
            parent_group__isnull=True
        )

        # Строим дерево
        tree_data = []
        for group in root_groups:
            tree_data.append(self._build_node(group))

        return JsonResponse(tree_data, safe=False)

    def _build_node(self, group):
        """Рекурсивное построение узла дерева"""
        node = {
            'id': str(group.id),
            'text': group.name,
            'children': [],
            'type': 'group',
            'li_attr': {'data-group-id': group.id},
            'a_attr': {'href': '#'}
        }

        # Получаем дочерние группы
        children = group.children.all()
        if children.exists():
            for child in children:
                node['children'].append(self._build_node(child))
        else:
            node['children'] = True  # Для динамической загрузки

        return node


class GroupListView(LoginRequiredMixin, ListView):
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
    form_class = PasswordGroupForm
    template_name = 'password_manager/group_form.html'
    success_url = reverse_lazy('password_manager:group_list')

    def get_form_kwargs(self):
        """Передаем текущего пользователя в форму."""
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)


class GroupUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = PasswordGroup
    form_class = PasswordGroupForm
    template_name = 'password_manager/group_form.html'
    success_url = reverse_lazy('password_manager:group_list')

    def get_form_kwargs(self):
        """Передаем текущего пользователя в форму."""
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_queryset(self):
        # Запрещаем редактирование групп, не принадлежащих пользователю
        return PasswordGroup.objects.filter(owner=self.request.user)

    def test_func(self):
        """
        Проверяем, что пользователь является владельцем группы.
        """
        group = self.get_object()
        return group.owner == self.request.user

    def handle_no_permission(self):
        """
        Обработка случая, когда пользователь пытается редактировать чужую группу.
        """
        if self.request.user.is_authenticated:
            raise PermissionDenied(_("У вас нет прав для редактирования этой группы."))
        return super().handle_no_permission()


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
        # user = self.request.user
        # base_qs = EncryptedPassword.objects.select_related('owner', 'group')
        #
        # shared_qs = EncryptedPassword.objects.filter(
        #     shared_access__shared_with=user
        # ).select_related('owner', 'group')
        #
        # return (base_qs | shared_qs).distinct().prefetch_related(
        #     'shared_access',
        #     'shared_access__shared_with'
        # ).order_by('-created_at')
        user = self.request.user
        # 1. Если админ - берем все, иначе только свои/общие
        if user.is_superuser:
            base_qs = EncryptedPassword.objects.all()
        else:
            base_qs = EncryptedPassword.objects.filter(
                Q(owner=user) | Q(shared_access__shared_with=user)
            )

        # 2. Оптимизация
        return base_qs.select_related('owner', 'group').prefetch_related(
            'shared_access',
            'shared_access__shared_with'
        ).distinct().order_by('-created_at')


class PasswordCreateView(KeySetupRequiredMixin, PasswordAccessMixin, CreateView):
    model = EncryptedPassword
    form_class = EncryptedPasswordForm
    template_name = 'password_manager/password_form.html'
    success_url = reverse_lazy('password_manager:password_list')
    is_create_view = True  # Маркер, что это представление создания

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        """Обработка валидной формы."""
        response = super().form_valid(form)
        messages.success(self.request, _('Пароль успешно сохранен.'))
        return response

    def form_invalid(self, form):
        """Обработка невалидной формы."""
        messages.error(self.request, _('Пожалуйста, исправьте ошибки в форме.'))
        return super().form_invalid(form)


class PasswordUpdateView(PasswordAccessMixin, UserPassesTestMixin, UpdateView):
    model = EncryptedPassword
    form_class = EncryptedPasswordForm
    template_name = 'password_manager/password_form.html'
    success_url = reverse_lazy('password_manager:password_list')

    def get_queryset(self):
        # Доступ только для пользователей с правом 'edit'
        user = self.request.user
        if user.is_superuser:
            return EncryptedPassword.objects.all()

        return EncryptedPassword.objects.filter(
            Q(owner=user) | Q(shared_access__shared_with=user)
        ).distinct()

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        kwargs['user'] = self.request.user
        return kwargs

    def test_func(self):
        """Проверяем, что пользователь является владельцем пароля."""
        password = self.get_object()
        user = self.request.user

        return password.owner == user

    def form_valid(self, form):
        messages.success(self.request, _('Пароль успешно обновлен.'))
        return super().form_valid(form)


class PasswordDeleteView(PasswordAccessMixin, DeleteView):
    model = EncryptedPassword
    template_name = 'password_manager/confirm_delete.html'
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

        # Добавляем общий доступ
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
        """Получаем историю изменений для конкретного пароля."""
        self.password_id = self.kwargs.get('pk')
        # Получаем запись пароля для проверки прав
        self.password_entry = get_object_or_404(EncryptedPassword, pk=self.password_id)

        # Проверяем права доступа
        if self.password_entry.owner != self.request.user:
            # Проверяем общий доступ
            has_access = False
            try:
                if hasattr(self.password_entry, 'shared_access') and self.password_entry.shared_access:
                    if self.request.user in self.password_entry.shared_access.shared_with.all():
                        has_access = True
            except Exception:
                pass

            if not has_access:
                raise PermissionDenied("У вас нет доступа к истории этого пароля.")

        # Возвращаем историю изменений
        return PasswordHistory.objects.filter(
            original_record=self.password_entry
        ).order_by('-changed_at')

    def get_context_data(self, **kwargs):
        """Добавляем ID оригинальной записи в контекст."""
        context = super().get_context_data(**kwargs)
        context['original_record_id'] = self.password_id
        return context


class ManageSharedAccessView(PasswordAccessMixin, View):
    """
    Управление общими правами доступа.
    Поддерживает GET (форма) и POST (добавление/удаление прав).
    """
    template_name = 'password_manager/share_form.html'

    def get(self, request, pk):
        """
        Отображает форму управления доступом.
        """
        password_record = get_object_or_404(EncryptedPassword, pk=pk)

        # Проверяем, что пользователь - владелец
        if password_record.owner != request.user:
            messages.error(request, _("Только владелец может управлять доступом."))
            return redirect('password_manager:password_detail', pk=pk)

        # Получаем или создаем объект SharedPassword
        shared_access, created = SharedPassword.objects.get_or_create(
            encrypted_password=password_record
        )

        # Получаем список пользователей с доступом
        users_with_access = shared_access.shared_with.all()

        # Получаем права для каждого пользователя
        user_permissions = []
        for user in users_with_access:
            user_permissions.append({
                'user': user,
                'permission': shared_access.permissions.get(str(user.id), 'read')
            })

        context = {
            'password_record': password_record,
            'shared_access': shared_access,
            'users_with_access': user_permissions,
            'available_users': self.get_available_users(request.user, users_with_access),
        }

        return render(request, self.template_name, context)

    def get_available_users(self, current_user, users_with_access):
        """
        Получает список пользователей, которым можно предоставить доступ.
        """
        from customers_app.models import DataBaseUser

        # Исключаем владельца и уже имеющих доступ
        excluded_users = [current_user.id]
        excluded_users.extend([user.id for user in users_with_access])

        return DataBaseUser.objects.exclude(id__in=excluded_users)

    @transaction.atomic
    def post(self, request, pk):
        """
        Обрабатывает POST запросы: добавление, обновление или удаление прав.
        """
        password_record = get_object_or_404(EncryptedPassword, pk=pk)

        # Проверяем, что пользователь - владелец
        if password_record.owner != request.user:
            messages.error(request, _("Только владелец может управлять доступом."))
            return redirect('password_manager:password_detail', pk=pk)

        action = request.POST.get('action', 'add')

        if action == 'add':
            return self.add_access(request, password_record)
        elif action == 'update':
            return self.update_access(request, password_record)
        elif action == 'remove':
            return self.remove_access(request, password_record)
        else:
            messages.error(request, _("Неизвестное действие."))
            return redirect('password_manager:password_share', pk=pk)

    def add_access(self, request, password_record):
        """
        Добавляет доступ для пользователя.
        """
        user_id = request.POST.get('user_id')
        permission = request.POST.get('permission', 'read')

        if not user_id:
            messages.error(request, _("Не выбран пользователь."))
            return redirect('password_manager:password_share', pk=password_record.pk)

        if permission not in ('read', 'edit'):
            messages.error(request, _("Недопустимый уровень доступа."))
            return redirect('password_manager:password_share', pk=password_record.pk)

        try:
            from customers_app.models import DataBaseUser
            user = DataBaseUser.objects.get(id=user_id)
        except DataBaseUser.DoesNotExist:
            messages.error(request, _("Пользователь не найден."))
            return redirect('password_manager:password_share', pk=password_record.pk)

        # Получаем или создаем объект SharedPassword
        shared, created = SharedPassword.objects.get_or_create(
            encrypted_password=password_record
        )

        # Обновляем права доступа
        permissions = shared.permissions or {}
        permissions[str(user_id)] = permission
        shared.permissions = permissions
        shared.shared_with.add(user)
        shared.save()

        messages.success(
            request,
            _("Пользователю '%(user)s' предоставлен доступ (%(permission)s).") % {
                'user': user.get_full_name() or user.username,
                'permission': _('чтение') if permission == 'read' else _('редактирование')
            }
        )

        return redirect('password_manager:password_share', pk=password_record.pk)

    def update_access(self, request, password_record):
        """
        Обновляет уровень доступа для пользователя.
        """
        user_id = request.POST.get('user_id')
        permission = request.POST.get('permission', 'read')

        if not user_id:
            messages.error(request, _("Не указан пользователь."))
            return redirect('password_manager:password_share', pk=password_record.pk)

        if permission not in ('read', 'edit'):
            messages.error(request, _("Недопустимый уровень доступа."))
            return redirect('password_manager:password_share', pk=password_record.pk)

        try:
            shared = SharedPassword.objects.get(encrypted_password=password_record)
        except SharedPassword.DoesNotExist:
            messages.error(request, _("Общий доступ не настроен."))
            return redirect('password_manager:password_share', pk=password_record.pk)

        # Проверяем, что пользователь есть в списке
        if not shared.shared_with.filter(id=user_id).exists():
            messages.error(request, _("Пользователь не имеет доступа."))
            return redirect('password_manager:password_share', pk=password_record.pk)

        # Обновляем права
        permissions = shared.permissions or {}
        permissions[str(user_id)] = permission
        shared.permissions = permissions
        shared.save()

        messages.success(request, _("Уровень доступа обновлен."))
        return redirect('password_manager:password_share', pk=password_record.pk)

    def remove_access(self, request, password_record):
        """
        Удаляет доступ для пользователя.
        """
        user_id = request.POST.get('user_id')

        if not user_id:
            messages.error(request, _("Не указан пользователь."))
            return redirect('password_manager:password_share', pk=password_record.pk)

        try:
            shared = SharedPassword.objects.get(encrypted_password=password_record)
        except SharedPassword.DoesNotExist:
            messages.error(request, _("Общий доступ не настроен."))
            return redirect('password_manager:password_share', pk=password_record.pk)

        # Удаляем пользователя
        shared.shared_with.remove(user_id)

        # Удаляем права из словаря
        permissions = shared.permissions or {}
        if str(user_id) in permissions:
            del permissions[str(user_id)]
        shared.permissions = permissions
        shared.save()

        messages.success(request, _("Доступ пользователя удален."))
        return redirect('password_manager:password_share', pk=password_record.pk)


class PasswordRevealView(PasswordAccessMixin, View):
    """
    Безопасное получение расшифрованного пароля по требованию.
    Принимает ключевую фразу через POST, проверяет хеш и возвращает plain-текст.
    """

    def get_object(self):
        """Получает объект пароля для проверки доступа."""
        return get_object_or_404(EncryptedPassword, pk=self.kwargs.get('pk'))

    def post(self, request, *args, **kwargs):
        obj = self.get_object()
        passphrase = None

        # 1. Извлечение фразы
        if request.content_type == 'application/json':
            try:
                data = json.loads(request.body)
                passphrase = data.get('passphrase')
            except json.JSONDecodeError:
                return JsonResponse({'error': 'Неверный формат JSON'}, status=400)
        else:
            passphrase = request.POST.get('passphrase')

        # 2. Логика расшифровки
        try:
            if request.user.is_superuser:
                # АДМИН: Фраза может быть любой (или пустой),
                # так как используется системный MASTER_KEY
                ciphertext = obj.admin_encrypted_copy or obj.encrypted_password
                decrypted_password = PasswordService.admin_decrypt(ciphertext)
            else:
                # ПОЛЬЗОВАТЕЛЬ: Обязательная проверка фразы
                if not passphrase:
                    return JsonResponse({'error': 'Ключевая фраза обязательна.'}, status=400)

                if not PasswordService.verify_passphrase(request.user, passphrase):
                    return JsonResponse({'error': 'Неверная ключевая фраза.'}, status=403)

                if obj.owner == request.user:
                    # Владелец расшифровывает свою запись
                    decrypted_password = PasswordService.decrypt_with_passphrase(
                        obj.encrypted_password, request.user, passphrase
                    )
                else:
                    # ПОЛЬЗОВАТЕЛЬ С ОБЩИМ ДОСТУПОМ:
                    # Так как запись зашифрована не его ключом, используем admin_encrypted_copy
                    if obj.admin_encrypted_copy:
                        decrypted_password = PasswordService.admin_decrypt(obj.admin_encrypted_copy)
                    else:
                        return JsonResponse(
                            {'error': 'Доступ ограничен. Запись не подготовлена для совместной работы.'},
                            status=400)

            return JsonResponse({
                'success': True,
                'password': decrypted_password,
                'login': obj.login,
                'url': obj.url,
                'resource_type': obj.get_resource_type_display()
            })

        except PermissionError as e:
            # Ошибка, если MASTER_KEY не настроен в .env
            return JsonResponse({'error': f'PermissionError - {str(e)}'}, status=500)
        except ValueError as e:
            return JsonResponse({'error': 'Ошибка дешифрования: неверный ключ или данные повреждены.'}, status=400)
        except Exception as e:
            logger.error(f"Error decrypting password: {str(e)}", exc_info=True)
            return JsonResponse({'error': 'Ошибка расшифровки пароля.'}, status=500)
