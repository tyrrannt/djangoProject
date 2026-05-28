# tasks_app/api_views.py
from rest_framework import viewsets, permissions
from django.db.models import Q
from .models import Task, Category
from .serializers import TaskSerializer, CategorySerializer

class TaskViewSet(viewsets.ModelViewSet):
    """
    ViewSet для управления задачами с поддержкой прав доступа и фильтрации.

    Позволяет аутентифицированным пользователям просматривать, создавать, редактировать
    и удалять задачи, которые они создали или с которыми были поделены.
    Использует стандартные действия DRF ModelViewSet с кастомизацией логики доступа
    на уровне queryset и создания объектов.

    Примеры использования:
        - GET /api/tasks/ — список задач, принадлежащих пользователю или общих с ним
        - POST /api/tasks/ — создание новой задачи (автоматически привязывается к текущему пользователю)
        - PATCH /api/tasks/1/ — частичное обновление задачи (только если пользователь — владелец или в shared_with)

    Права доступа:
        - Только аутентифицированные пользователи могут взаимодействовать с задачами.
        - Просмотр, редактирование и удаление ограничены владельцем или получателями доступа.

    Attributes:
        serializer_class (TaskSerializer): Сериализатор для преобразования задач в JSON.
        permission_classes (list): Требует аутентификацию для всех действий.

    """

    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Возвращает QuerySet задач, доступных текущему пользователю.

        Формирует список задач, где пользователь является:
            - автором (поле `user`)
            - или указан в поле `shared_with` (ManyToMany)

        Используется `distinct()`, так как одна задача может попасть в выборку дважды
        (например, если пользователь и владелец, и в списке shared_with).
        Результат сортируется по дате создания — от новых к старым.

        Логика фильтрации выполняется на уровне БД, что эффективно и безопасно.

        Returns:
            QuerySet: Отфильтрованный QuerySet объектов Task, доступных пользователю.
                     Тип: django.db.models.QuerySet[Task]

        Пример результата:
            <QuerySet [<Task: Помыть кота>, <Task: Сделать отчёт>]>

        Note:
            Вызывается автоматически DRF для всех действий, кроме создания.
            Гарантирует, что пользователь не увидит чужие задачи, если они не были с ним поделены.
        """
        user = self.request.user
        return Task.objects.filter(
            Q(user=user) | Q(shared_with=user)
        ).distinct().order_by('-created_at')

    def perform_create(self, serializer):
        """Сохраняет новую задачу, присваивая текущего пользователя как автора.

        Автоматически устанавливает `user` в сериализаторе равным `request.user`.
        Это предотвращает попытки создания задач от имени другого пользователя
        через подмену данных в запросе.

        Args:
            serializer (TaskSerializer): Валидированный сериализатор с данными задачи.
                                         Содержит поля: title, description, shared_with и др.

        Side effects:
            - Создаёт новую запись в БД (INSERT INTO tasks_task).
            - Поле `user` устанавливается принудительно, игнорируя переданное значение.
            - Вызывает сигналы Django (post_save), если они подключены.

        Raises:
            ValidationError: Если данные в сериализаторе не прошли валидацию
                             (например, пустой заголовок, если он required).
            PermissionDenied: Не выбрасывается напрямую, но предотвращается на уровне permission_classes.

        Пример входных данных:
            {
                "title": "Купить молоко",
                "description": "Обязательно пастеризованное",
                "shared_with": [1, 2]
            }

        После вызова:
            - `serializer.save(user=request.user)` → задача сохраняется с `user=запросивший_пользователь`
        """
        serializer.save(user=self.request.user)

class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ReadOnly ViewSet for task categories.
    """
    queryset = Category.objects.all().order_by('name')
    serializer_class = CategorySerializer
    permission_classes = [permissions.IsAuthenticated]
