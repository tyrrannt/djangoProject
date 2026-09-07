"""Представления Django REST Framework (API ViewSets) для модуля tasks_app."""

import datetime
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from customers_app.models import DataBaseUser
from tasks_app.models import Category, SubTask, Task, TaskAssignment, TaskComment, TaskHistory, TaskRole, TaskStatus
from tasks_app.serializers import (
    CategorySerializer,
    DisciplineReportSummarySerializer,
    SubTaskSerializer,
    TaskAssignmentSerializer,
    TaskCommentSerializer,
    TaskHistorySerializer,
    TaskSerializer,
)
from tasks_app.services import CommentService, ReportService, SubTaskService, TaskService


class TaskViewSet(viewsets.ModelViewSet):
    """ViewSet для управления задачами с поддержкой прав доступа, фильтрации и Workflow."""

    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Возвращает задачи, доступные текущему пользователю."""
        user = self.request.user
        qs = Task.objects.filter(
            Q(user=user) |
            Q(responsible=user) |
            Q(assignees=user) |
            Q(observers=user) |
            Q(shared_with=user)
        ).distinct()

        division_id = self.request.query_params.get('division')
        if division_id and division_id.isdigit():
            qs = qs.filter(
                Q(user__user_work_profile__divisions_id=int(division_id)) |
                Q(responsible__user_work_profile__divisions_id=int(division_id)) |
                Q(assignees__user_work_profile__divisions_id=int(division_id))
            ).distinct()

        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)

        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        """Сохраняет новую задачу с текущим пользователем в качестве автора."""
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'], url_path='start')
    def start_task(self, request, pk=None):
        """Переводит задачу в статус 'В работе' (IN_PROGRESS)."""
        task = self.get_object()
        try:
            task = TaskService.start_task(task, request.user)
            return Response(TaskSerializer(task).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='submit-review')
    def submit_review(self, request, pk=None):
        """Отправляет задачу на проверку (ON_REVIEW)."""
        task = self.get_object()
        comment = request.data.get('comment', '')
        try:
            task = TaskService.submit_for_review(task, request.user, comment=comment)
            return Response(TaskSerializer(task).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='accept')
    def accept_task(self, request, pk=None):
        """Принимает выполнение задачи (COMPLETED) с поддержкой ЭЦП."""
        task = self.get_object()
        eds_signature = request.data.get('eds_signature')
        comment = request.data.get('comment', '')
        bypass_eds = request.data.get('bypass_eds', False) in ['true', '1', True]
        try:
            task = TaskService.accept_task(
                task, request.user, eds_signature=eds_signature, comment=comment, bypass_eds=bypass_eds
            )
            return Response(TaskSerializer(task).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='return')
    def return_task(self, request, pk=None):
        """Возвращает задачу на доработку (RETURNED)."""
        task = self.get_object()
        reason = request.data.get('reason', '')
        try:
            task = TaskService.return_task(task, request.user, reason=reason)
            return Response(TaskSerializer(task).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='cancel')
    def cancel_task(self, request, pk=None):
        """Отменяет задачу (CANCELLED)."""
        task = self.get_object()
        reason = request.data.get('reason', '')
        try:
            task = TaskService.cancel_task(task, request.user, reason=reason)
            return Response(TaskSerializer(task).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='delegate')
    def delegate(self, request, pk=None):
        """Делегирует или назначает задачу сотруднику."""
        task = self.get_object()
        assigned_to_id = request.data.get('assigned_to_id')
        role = request.data.get('role', TaskRole.ASSIGNEE)
        comment = request.data.get('comment', '')

        if not assigned_to_id:
            return Response({'error': 'assigned_to_id обязателен'}, status=status.HTTP_400_BAD_REQUEST)

        assigned_to = get_object_or_404(DataBaseUser, pk=assigned_to_id)
        try:
            assignment = TaskService.assign_user(
                task=task,
                assigned_by=request.user,
                assigned_to=assigned_to,
                role=role,
                comment=comment
            )
            return Response(TaskAssignmentSerializer(assignment).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'], url_path='history')
    def history(self, request, pk=None):
        """Возвращает историю изменений задачи."""
        task = self.get_object()
        history_qs = task.history.all().select_related('user').order_by('-created_at')
        return Response(TaskHistorySerializer(history_qs, many=True).data)

    @action(detail=True, methods=['get', 'post'], url_path='subtasks')
    def subtasks(self, request, pk=None):
        """Получение списка или добавление подзадачи."""
        task = self.get_object()
        if request.method == 'GET':
            subtasks = task.subtasks.all()
            return Response(SubTaskSerializer(subtasks, many=True).data)

        title = request.data.get('title', '').strip()
        if not title:
            return Response({'error': 'Название подзадачи обязательно'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            subtask = SubTaskService.create_subtask(task, request.user, title)
            return Response(SubTaskSerializer(subtask).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get', 'post'], url_path='comments')
    def comments(self, request, pk=None):
        """Получение списка комментариев или публикация нового комментария."""
        task = self.get_object()
        if request.method == 'GET':
            comments = task.comments.filter(parent__isnull=True).prefetch_related('replies')
            return Response(TaskCommentSerializer(comments, many=True).data)

        text = request.data.get('text', '').strip()
        parent_id = request.data.get('parent_id')
        parent = TaskComment.objects.filter(id=parent_id, task=task).first() if parent_id else None
        try:
            comment = CommentService.add_comment(task, request.user, text, parent=parent)
            return Response(TaskCommentSerializer(comment).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """ReadOnly ViewSet для категорий задач."""

    queryset = Category.objects.all().order_by('name')
    serializer_class = CategorySerializer
    permission_classes = [permissions.IsAuthenticated]


class DisciplineReportAPIView(APIView):
    """REST API эндпоинт для получения аналитики исполнительской дисциплины."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Возвращает JSON с агрегированными KPI и статистикой по подразделениям и сотрудникам."""
        date_from_str = request.query_params.get('date_from')
        date_to_str = request.query_params.get('date_to')
        division_id_str = request.query_params.get('division')
        employee_id_str = request.query_params.get('employee')

        date_from = None
        date_to = None
        division_id = None
        employee_id = None

        if date_from_str:
            try:
                date_from = datetime.datetime.strptime(date_from_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        if date_to_str:
            try:
                date_to = datetime.datetime.strptime(date_to_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        if division_id_str and division_id_str.isdigit():
            division_id = int(division_id_str)
        if employee_id_str and employee_id_str.isdigit():
            employee_id = int(employee_id_str)

        report_data = ReportService.get_discipline_report_data(
            date_from=date_from,
            date_to=date_to,
            division_id=division_id,
            employee_id=employee_id,
            current_user=request.user
        )

        # Подготавливаем JSON-совместимый ответ
        return Response({
            'date_from': report_data['date_from'],
            'date_to': report_data['date_to'],
            'total_count': report_data['total_count'],
            'completed_on_time_count': report_data['completed_on_time_count'],
            'completed_overdue_count': report_data['completed_overdue_count'],
            'in_progress_count': report_data['in_progress_count'],
            'active_overdue_count': report_data['active_overdue_count'],
            'eds_signed_count': report_data['eds_signed_count'],
            'discipline_rate': report_data['discipline_rate'],
            'avg_completion_days': report_data['avg_completion_days'],
            'division_stats': report_data['division_stats'],
            'employee_stats': [
                {k: v for k, v in emp.items() if k != 'user'} for emp in report_data['employee_stats']
            ],
            'generated_at': report_data['generated_at'].isoformat(),
        })
