"""Модульные тесты приложения заявок и добровольных сообщений (tickets_app.tests).

Покрывает:
- Модели данных, валидацию расширений и вложений;
- Сервисный слой асинхронных Celery-уведомлений;
- Разграничение прав доступа и фильтрацию служебных заметок;
- Контроллеры представлений (ListView, DetailView, CreateView, UpdateView, add_message);
- Эндпоинты REST API и валидацию апелляций.
"""

from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from .models import Attachment, Message, Ticket, TicketStatus, validate_file_extension
from .services import save_ticket_attachments, send_ticket_notification_async

User = get_user_model()


class TicketModelTestCase(TestCase):
    """Тестирование моделей данных Ticket, Message и Attachment."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='pilot1',
            email='pilot1@barkol.ru',
            password='pass',
            first_name='Иван',
            last_name='Иванов',
        )
        self.ticket = Ticket.objects.create(
            title='Замечание по ВПП',
            description='Неровности на покрытии ВПП',
            author=self.user,
        )

    def test_ticket_str_and_properties(self):
        """Проверяет строковое представление и служебные свойства заявки."""
        self.assertEqual(str(self.ticket), f'#{self.ticket.pk} - Замечание по ВПП')
        self.assertFalse(self.ticket.is_closed_or_resolved)
        self.assertEqual(self.ticket.status_badge_class, 'bg-primary')

        self.ticket.status = TicketStatus.RESOLVED
        self.ticket.save()
        self.assertTrue(self.ticket.is_closed_or_resolved)
        self.assertEqual(self.ticket.status_badge_class, 'bg-success')

    def test_message_creation_and_str(self):
        """Проверяет создание и строковое представление сообщений."""
        msg = Message.objects.create(
            ticket=self.ticket,
            sender=self.user,
            text='Прошу провести грейдирование',
            is_internal=False,
        )
        self.assertIn(f'Сообщение в #{self.ticket.pk}', str(msg))

    def test_attachment_validation(self):
        """Проверяет валидацию расширений файлов."""
        valid_pdf = SimpleUploadedFile('report.pdf', b'fake pdf content', content_type='application/pdf')
        validate_file_extension(valid_pdf)  # Не должно вызывать исключений

        invalid_exe = SimpleUploadedFile('script.exe', b'bad content', content_type='application/octet-stream')
        with self.assertRaises(ValidationError):
            validate_file_extension(invalid_exe)

    def test_attachment_clean(self):
        """Проверяет требование привязки вложения к сообщению или заявке."""
        f = SimpleUploadedFile('photo.jpg', b'fake image', content_type='image/jpeg')
        attachment = Attachment(file=f)
        with self.assertRaises(ValidationError):
            attachment.clean()


class TicketServicesTestCase(TestCase):
    """Тестирование сервисного слоя tickets_app.services."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='engineer1',
            email='eng@barkol.ru',
            password='pass',
            first_name='Петр',
            last_name='Петров',
        )
        self.ticket = Ticket.objects.create(
            title='Вопрос по гидросистеме',
            description='Падение давления гидросистемы',
            author=self.user,
        )

    @patch('mailbox_app.services.email_service.UniversalEmailService.send_async_email')
    def test_send_ticket_notification_async(self, mock_send_async):
        """Проверяет постановку задачи отправки email в Celery через UniversalEmailService."""
        mock_send_async.return_value = True

        leadership_group, _ = Group.objects.get_or_create(name='Руководство')
        leader = User.objects.create_user(
            username='leader1',
            email='leader1@barkol.ru',
            password='pass',
            first_name='Сергей',
            last_name='Сергеев',
        )
        leader.groups.add(leadership_group)

        # 1. Новое обращение
        result = send_ticket_notification_async('new', self.ticket, actor=self.user)
        self.assertTrue(result)
        self.assertTrue(mock_send_async.called)
        args, kwargs = mock_send_async.call_args
        self.assertIn('leader1@barkol.ru', kwargs['recipient_list'])
        self.assertIn('Новое добровольное сообщение', kwargs['subject'])

        # 2. Назначение ответственного
        self.ticket.responsible = leader
        self.ticket.save()
        result_assigned = send_ticket_notification_async('assigned', self.ticket, actor=leader)
        self.assertTrue(result_assigned)

        # 3. Решено
        result_resolved = send_ticket_notification_async('resolved', self.ticket, actor=leader)
        self.assertTrue(result_resolved)

    def test_save_ticket_attachments(self):
        """Проверяет корректное сохранение и валидацию вложений."""
        f1 = SimpleUploadedFile('doc.pdf', b'pdf binary', content_type='application/pdf')
        f2 = SimpleUploadedFile('pic.png', b'png binary', content_type='image/png')
        attachments = save_ticket_attachments([f1, f2], ticket=self.ticket)
        self.assertEqual(len(attachments), 2)
        self.assertEqual(self.ticket.attachments.count(), 2)

        bad_file = SimpleUploadedFile('virus.sh', b'rm -rf', content_type='application/x-sh')
        with self.assertRaises(ValidationError):
            save_ticket_attachments([bad_file], ticket=self.ticket)


class TicketViewsTestCase(TestCase):
    """Тестирование представлений реестра, деталей, создания и добавления сообщений."""

    def setUp(self):
        self.client = Client()
        self.leadership_group, _ = Group.objects.get_or_create(name='Руководство')

        self.author = User.objects.create_user(
            username='author_user',
            email='author@barkol.ru',
            password='pass',
            first_name='Алексей',
            last_name='Алексеев',
        )
        self.staff_user = User.objects.create_user(
            username='staff_user',
            email='staff@barkol.ru',
            password='pass',
            first_name='Михаил',
            last_name='Михайлов',
            is_staff=True,
        )
        self.leader_user = User.objects.create_user(
            username='leader_user',
            email='leader@barkol.ru',
            password='pass',
            first_name='Дмитрий',
            last_name='Дмитриев',
        )
        self.leader_user.groups.add(self.leadership_group)

        self.other_user = User.objects.create_user(
            username='other_user',
            email='other@barkol.ru',
            password='pass',
            first_name='Николай',
            last_name='Николаев',
        )

        self.ticket = Ticket.objects.create(
            title='Препятствие на посадочной площадке',
            description='Посторонний объект в зоне подлета',
            author=self.author,
            responsible=self.staff_user,
            status=TicketStatus.NEW,
        )

        self.internal_msg = Message.objects.create(
            ticket=self.ticket,
            sender=self.leader_user,
            text='Служебная заметка для ОЛЭ: проверить журнал полетов',
            is_internal=True,
        )
        self.public_msg = Message.objects.create(
            ticket=self.ticket,
            sender=self.staff_user,
            text='Территория обследована, объект удален',
            is_internal=False,
        )

    def test_ticket_list_access_and_kpi(self):
        """Проверяет разграничение доступа в реестре и достоверность KPI-метрик."""
        # 1. Неавторизованный пользователь перенаправляется на логин
        resp = self.client.get(reverse('tickets_app:list'))
        self.assertEqual(resp.status_code, 302)

        # 2. Обычный автор видит только свои заявки
        self.client.force_login(self.author)
        resp_author = self.client.get(reverse('tickets_app:list'))
        self.assertEqual(resp_author.status_code, 200)
        self.assertEqual(len(resp_author.context['tickets']), 1)

        # 3. Руководство видит все заявки и KPI
        self.client.force_login(self.leader_user)
        resp_leader = self.client.get(reverse('tickets_app:list'))
        self.assertEqual(resp_leader.status_code, 200)
        self.assertEqual(resp_leader.context['total_count'], 1)
        self.assertEqual(resp_leader.context['unassigned_count'], 0)  # назначен staff_user

    def test_ticket_detail_internal_notes_privacy(self):
        """Проверяет, что автор НЕ видит служебные заметки, а руководство и ответственный видят."""
        # Автор сообщения
        self.client.force_login(self.author)
        resp_author = self.client.get(reverse('tickets_app:detail', kwargs={'pk': self.ticket.pk}))
        self.assertEqual(resp_author.status_code, 200)
        visible_msgs = resp_author.context['visible_messages']
        self.assertEqual(len(visible_msgs), 1)
        self.assertEqual(visible_msgs[0].pk, self.public_msg.pk)

        # Ответственный специалист
        self.client.force_login(self.staff_user)
        resp_staff = self.client.get(reverse('tickets_app:detail', kwargs={'pk': self.ticket.pk}))
        self.assertEqual(len(resp_staff.context['visible_messages']), 2)

        # Руководство
        self.client.force_login(self.leader_user)
        resp_leader = self.client.get(reverse('tickets_app:detail', kwargs={'pk': self.ticket.pk}))
        self.assertEqual(len(resp_leader.context['visible_messages']), 2)

        # Посторонний пользователь
        self.client.force_login(self.other_user)
        resp_other = self.client.get(reverse('tickets_app:detail', kwargs={'pk': self.ticket.pk}))
        self.assertEqual(resp_other.status_code, 404)

    @patch('mailbox_app.services.email_service.UniversalEmailService.send_async_email')
    def test_ticket_create_view(self, mock_send):
        """Проверяет создание заявки и запуск Celery-уведомления."""
        mock_send.return_value = True
        self.client.force_login(self.author)

        post_data = {
            'title': 'Новая проблема с радиостанцией',
            'description': 'Помехи на аварийной частоте 121.5 МГц',
        }
        resp = self.client.post(reverse('tickets_app:create'), post_data)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Ticket.objects.filter(title='Новая проблема с радиостанцией').exists())
        new_ticket = Ticket.objects.get(title='Новая проблема с радиостанцией')
        self.assertEqual(new_ticket.author, self.author)
        self.assertTrue(mock_send.called)

    @patch('mailbox_app.services.email_service.UniversalEmailService.send_async_email')
    def test_ticket_update_status_and_resolved_at(self, mock_send):
        """Проверяет фиксацию и сброс даты решения при изменении статуса."""
        mock_send.return_value = True
        self.client.force_login(self.leader_user)

        # 1. Перевод в статус Решено
        update_data = {
            'title': self.ticket.title,
            'description': self.ticket.description,
            'responsible': self.staff_user.pk,
            'status': TicketStatus.RESOLVED,
        }
        resp = self.client.post(reverse('tickets_app:edit', kwargs={'pk': self.ticket.pk}), update_data)
        self.assertEqual(resp.status_code, 302)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TicketStatus.RESOLVED)
        self.assertIsNotNone(self.ticket.resolved_at)

        # 2. Возврат в статус В работе очищает resolved_at
        update_data['status'] = TicketStatus.IN_PROGRESS
        self.client.post(reverse('tickets_app:edit', kwargs={'pk': self.ticket.pk}), update_data)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TicketStatus.IN_PROGRESS)
        self.assertIsNone(self.ticket.resolved_at)

    @patch('mailbox_app.services.email_service.UniversalEmailService.send_async_email')
    def test_add_message_and_status_transition(self, mock_send):
        """Проверяет добавление сообщения, автоматический перевод в IN_PROGRESS и ручную смену статуса."""
        mock_send.return_value = True

        # Сбросим статус в NEW
        self.ticket.status = TicketStatus.NEW
        self.ticket.save()

        # 1. Ответ от ответственного специалиста автоматически переводит NEW -> IN_PROGRESS
        self.client.force_login(self.staff_user)
        resp = self.client.post(
            reverse('tickets_app:add_message', kwargs={'pk': self.ticket.pk}),
            {'text': 'Принято к исполнению, выезжаю на место'},
        )
        self.assertEqual(resp.status_code, 302)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TicketStatus.IN_PROGRESS)

        # 2. Руководитель выбирает статус RESOLVED через селектор формы ответа
        self.client.force_login(self.leader_user)
        resp_resolve = self.client.post(
            reverse('tickets_app:add_message', kwargs={'pk': self.ticket.pk}),
            {'text': 'Акт проверки утвержден, замечание устранено', 'status': TicketStatus.RESOLVED},
        )
        self.assertEqual(resp_resolve.status_code, 302)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TicketStatus.RESOLVED)
        self.assertIsNotNone(self.ticket.resolved_at)

        # 3. Добавление сообщения в закрытую заявку блокируется
        resp_closed = self.client.post(
            reverse('tickets_app:add_message', kwargs={'pk': self.ticket.pk}),
            {'text': 'Попытка писать в закрытую заявку'},
        )
        self.assertEqual(resp_closed.status_code, 302)


class TicketApiTestCase(TestCase):
    """Тестирование эндпоинтов REST API (/api/tickets/)."""

    def setUp(self):
        self.client = Client()
        self.leadership_group, _ = Group.objects.get_or_create(name='Руководство')

        self.author = User.objects.create_user(
            username='api_author',
            email='apiauthor@barkol.ru',
            password='pass',
            first_name='Андрей',
            last_name='Андреев',
        )
        self.leader = User.objects.create_user(
            username='api_leader',
            email='apileader@barkol.ru',
            password='pass',
            first_name='Григорий',
            last_name='Григорьев',
        )
        self.leader.groups.add(self.leadership_group)

        self.ticket = Ticket.objects.create(
            title='API Тест заявки',
            description='Тестовое описание через API',
            author=self.author,
            status=TicketStatus.NEW,
        )

        Message.objects.create(
            ticket=self.ticket,
            sender=self.leader,
            text='Секретная внутренняя заметка',
            is_internal=True,
        )
        Message.objects.create(
            ticket=self.ticket,
            sender=self.author,
            text='Публичный вопрос автора',
            is_internal=False,
        )

    def test_api_internal_notes_filtered_for_author(self):
        """Проверяет сокрытие служебных заметок в ответе REST API для обычного автора."""
        self.client.force_login(self.author)
        resp = self.client.get(f'/api/tickets/{self.ticket.pk}/')
        self.assertEqual(resp.status_code, 200)
        messages_data = resp.json().get('messages', [])
        self.assertEqual(len(messages_data), 1)
        self.assertEqual(messages_data[0]['text'], 'Публичный вопрос автора')

    def test_api_internal_notes_visible_for_leader(self):
        """Проверяет видимость всех заметок в REST API для руководства."""
        self.client.force_login(self.leader)
        resp = self.client.get(f'/api/tickets/{self.ticket.pk}/')
        self.assertEqual(resp.status_code, 200)
        messages_data = resp.json().get('messages', [])
        self.assertEqual(len(messages_data), 2)

    @patch('mailbox_app.services.email_service.UniversalEmailService.send_async_email')
    def test_api_change_status_action(self, mock_send):
        """Проверяет эндпоинт смены статуса PATCH /api/tickets/<pk>/change_status/."""
        mock_send.return_value = True
        self.client.force_login(self.leader)

        resp = self.client.patch(
            f'/api/tickets/{self.ticket.pk}/change_status/',
            data={'status': TicketStatus.RESOLVED},
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TicketStatus.RESOLVED)
        self.assertIsNotNone(self.ticket.resolved_at)
