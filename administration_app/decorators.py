from functools import wraps
from django.core.exceptions import PermissionDenied

def group_required(group_name):
    """Проверяет, состоит ли пользователь в указанной группе Django, иначе возвращает 403 ошибку.

    Декоратор для представлений Django, который ограничивает доступ к представлению
    только пользователями, принадлежащими к группе с заданным именем. Используется
    для контроля доступа на уровне представлений (views). Проверка выполняется через
    связь Many-to-Many между моделью User и Group в Django (auth.Group).

    Декоратор оборачивает исходную функцию представления и проверяет
    наличие у пользователя (request.user) группы с именем `group_name`.
    Если пользователь не состоит в группе, вызывается исключение PermissionDenied,
    которое приведёт к ответу HTTP 403 Forbidden.

    Args:
        group_name (str): Название группы Django (из таблицы auth_group),
            которая требуется для доступа к представлению.

    Returns:
        callable: Обёрнутая функция представления, защищённая проверкой прав доступа.

    Raises:
        PermissionDenied: Если пользователь не состоит в группе с именем `group_name`.
            Выбрасывается явно, что приводит к HTTP 403 ответу.

    Example:
        @group_required('Managers')
        def admin_dashboard(request):
            return render(request, 'admin_panel.html')

        В этом случае доступ к `admin_dashboard` будет разрешён только
        пользователям из группы "Managers".
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if request.user.groups.filter(name=group_name).exists():
                return view_func(request, *args, **kwargs)
            raise PermissionDenied
        return _wrapped_view
    return decorator