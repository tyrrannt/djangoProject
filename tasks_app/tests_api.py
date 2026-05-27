from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from customers_app.models import DataBaseUser
from .models import Task, Category

class TasksAPITests(APITestCase):
    def setUp(self):
        # Create user with required names
        self.user = DataBaseUser.objects.create_user(
            username='testuser', 
            password='password',
            last_name='Петров',
            first_name='Петр'
        )
        self.client.force_authenticate(user=self.user)

        # Create category
        self.category = Category.objects.create(name='Work')

        # Create task
        self.task = Task.objects.create(
            user=self.user,
            title='Test Task',
            description='Test Description',
            category=self.category,
            priority='info'
        )

    def test_list_tasks(self):
        """
        Ensure we can list tasks via API.
        """
        url = reverse('tasks_app:api_task-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['title'], 'Test Task')

    def test_create_task(self):
        """
        Ensure we can create a new task via API.
        """
        url = reverse('tasks_app:api_task-list')
        data = {
            'title': 'New API Task',
            'priority': 'danger',
            'category_id': self.category.id
        }
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Task.objects.count(), 2)
        self.assertEqual(Task.objects.last().title, 'New API Task')

    def test_update_task_status(self):
        """
        Ensure we can update task status (completed) via PATCH.
        """
        url = reverse('tasks_app:api_task-detail', args=[self.task.id])
        data = {'completed': True}
        response = self.client.patch(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.task.refresh_from_db()
        self.assertTrue(self.task.completed)
