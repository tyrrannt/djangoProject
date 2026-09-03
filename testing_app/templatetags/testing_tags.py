"""Шаблонные теги и фильтры для модуля тестирования персонала testing_app."""

from django import template

register = template.Library()


@register.filter(name="is_testing_manager")
def is_testing_manager(user) -> bool:
    """Проверяет, обладает ли пользователь правами ответственного за тестирование или администратора.

    Правами обладают только суперпользователи и члены группы 'Ответственные за тестирование'.
    Обычные сотрудники (включая staff) без членства в группе правами не обладают.

    Args:
        user: Экземпляр пользователя.

    Returns:
        bool: True, если пользователь суперпользователь или входит в группу 'Ответственные за тестирование'.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name="Ответственные за тестирование").exists()


@register.inclusion_tag("testing_app/includes/testing_nav.html", takes_context=True)
def render_testing_nav(context, active_tab: str = ""):
    """Отображает верхнюю сквозную навигационную панель подсистемы тестирования.

    Позволяет быстро переключаться между разделами:
    - Мои тестирования (Личный кабинет сотрудника);
    - Дашборд руководителя (Аналитика и онлайн-мониторинг);
    - Мероприятия (Приказы);
    - Банк вопросов;
    - Импорт тестов из Excel;
    - Категории вопросов.

    Args:
        context: Контекст родительского шаблона.
        active_tab (str): Идентификатор текущей активной вкладки.

    Returns:
        dict: Контекст для рендеринга навигации.
    """
    request = context.get("request")
    user = request.user if request else None
    is_manager = is_testing_manager(user)

    return {
        "user": user,
        "is_manager": is_manager,
        "active_tab": active_tab,
    }
