"""Модульные и интеграционные тесты прав доступа (RBAC) для flight_planning.

Проверяет корректность разграничения прав для трех основных ролей:
1. Отдел планирования полетов (полный CRUD, управление экипажами, отчеты).
2. Руководство полетов (просмотр шахматки, графиков и аналитических отчетов).
3. Летный состав (просмотр своего графика, шахматки, пометки к своим рейсам).
"""

import datetime
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import Group, Permission
from customers_app.models import DataBaseUser
from hrdepartment_app.models import PlaceProductionActivity
from contracts_app.models import Estate, TypeProperty
from flight_planning.models import FlightCrew, CrewMember, FlightCrewNote, AircraftMovement, PilotAssignment
from flight_planning.permissions import (
    is_flight_planner,
    can_view_flight_reports,
    can_view_flight_planning,
    GROUP_FLIGHT_PLANNERS,
    GROUP_FLIGHT_MANAGEMENT,
    GROUP_FLIGHT_CREW
)


class FlightPlanningRBACPermissionsTests(TestCase):
    """Тестирование вспомогательных функций проверки прав доступа (RBAC)."""

    def setUp(self):
        """Создает тестовых пользователей для различных ролей."""
        self.planner_user = DataBaseUser.objects.create_user(
            username='planner_user',
            password='password123',
            last_name='Планировщиков',
            first_name='Петр'
        )
        self.manager_user = DataBaseUser.objects.create_user(
            username='manager_user',
            password='password123',
            last_name='Руководителев',
            first_name='Роман'
        )
        self.pilot_user = DataBaseUser.objects.create_user(
            username='pilot_user',
            password='password123',
            last_name='Летчиков',
            first_name='Леонид'
        )
        self.guest_user = DataBaseUser.objects.create_user(
            username='guest_user',
            password='password123',
            last_name='Гостев',
            first_name='Григорий'
        )

        # Создаем группы и добавляем пользователей
        self.planner_group, _ = Group.objects.get_or_create(name=GROUP_FLIGHT_PLANNERS)
        self.manager_group, _ = Group.objects.get_or_create(name=GROUP_FLIGHT_MANAGEMENT)
        self.crew_group, _ = Group.objects.get_or_create(name=GROUP_FLIGHT_CREW)

        self.planner_user.groups.add(self.planner_group)
        self.manager_user.groups.add(self.manager_group)
        self.pilot_user.groups.add(self.crew_group)

    def test_planner_permissions(self):
        """Проверяет, что планировщик обладает всеми правами."""
        self.assertTrue(is_flight_planner(self.planner_user))
        self.assertTrue(can_view_flight_reports(self.planner_user))
        self.assertTrue(can_view_flight_planning(self.planner_user))

    def test_manager_permissions(self):
        """Проверяет, что руководство может смотреть планирование и отчеты, но не имеет прав планировщика."""
        self.assertFalse(is_flight_planner(self.manager_user))
        self.assertTrue(can_view_flight_reports(self.manager_user))
        self.assertTrue(can_view_flight_planning(self.manager_user))

    def test_pilot_permissions(self):
        """Проверяет, что летный состав имеет базовый доступ к планированию, но не к отчетам и не к управлению."""
        self.assertFalse(is_flight_planner(self.pilot_user))
        self.assertFalse(can_view_flight_reports(self.pilot_user))
        self.assertTrue(can_view_flight_planning(self.pilot_user))

    def test_guest_permissions(self):
        """Проверяет, что сторонний пользователь без групп не имеет прав доступа."""
        self.assertFalse(is_flight_planner(self.guest_user))
        self.assertFalse(can_view_flight_reports(self.guest_user))
        self.assertFalse(can_view_flight_planning(self.guest_user))

    def test_regular_staff_user_does_not_have_planner_rights(self):
        """Проверяет, что обычный штатный сотрудник (is_staff=True) без явных прав НЕ имеет прав диспетчера."""
        staff_user = DataBaseUser.objects.create_user(
            username='regular_staff',
            password='password123',
            is_staff=True
        )
        self.assertFalse(is_flight_planner(staff_user))
        self.assertFalse(can_view_flight_reports(staff_user))
        self.assertFalse(can_view_flight_planning(staff_user))


class FlightPlanningViewsSecurityTests(TestCase):
    """Интеграционное тестирование защищенности представлений и эндпоинтов."""

    def setUp(self):
        """Инициализирует тестовые данные: пользователей, МПД, ВС и экипаж."""
        self.client = Client()

        self.planner_user = DataBaseUser.objects.create_user(
            username='planner',
            password='password123',
            last_name='Иванов',
            first_name='Иван'
        )
        self.manager_user = DataBaseUser.objects.create_user(
            username='manager',
            password='password123',
            last_name='Сидоров',
            first_name='Сергей'
        )
        self.pilot_user = DataBaseUser.objects.create_user(
            username='pilot',
            password='password123',
            last_name='Кузнецов',
            first_name='Константин'
        )

        planner_group, _ = Group.objects.get_or_create(name=GROUP_FLIGHT_PLANNERS)
        manager_group, _ = Group.objects.get_or_create(name=GROUP_FLIGHT_MANAGEMENT)
        crew_group, _ = Group.objects.get_or_create(name=GROUP_FLIGHT_CREW)

        self.planner_user.groups.add(planner_group)
        self.manager_user.groups.add(manager_group)
        self.pilot_user.groups.add(crew_group)

        self.mpd = PlaceProductionActivity.objects.create(name='МПД Север', in_planning=True)
        self.type_prop = TypeProperty.objects.create(type_property='Ми-8МТВ')
        self.aircraft = Estate.objects.create(registration_number='RA-22334', type_property=self.type_prop)

        self.today = datetime.date.today()
        self.crew = FlightCrew.objects.create(
            mpd=self.mpd,
            aircraft=self.aircraft,
            date=self.today,
            created_by=self.planner_user
        )
        CrewMember.objects.create(crew=self.crew, member=self.pilot_user, role='copilot')

    def test_report_access_by_role(self):
        """Проверяет доступность отчетов для руководства/планировщика и блокировку для пилота."""
        url = reverse('flight_planning:aircraft_basing_report')

        # 1. Пилот получает 403 Forbidden
        self.client.force_login(self.pilot_user)
        resp_pilot = self.client.get(url)
        self.assertEqual(resp_pilot.status_code, 403)

        # 2. Руководство получает 200 OK
        self.client.force_login(self.manager_user)
        resp_manager = self.client.get(url)
        self.assertEqual(resp_manager.status_code, 200)

        # 3. Планировщик получает 200 OK
        self.client.force_login(self.planner_user)
        resp_planner = self.client.get(url)
        self.assertEqual(resp_planner.status_code, 200)

    def test_mutation_api_access_by_role(self):
        """Проверяет, что модификация экипажей разрешена только планировщикам."""
        url = reverse('flight_planning:delete_crew_api')
        payload = {'crew_id': self.crew.id}

        # 1. Пилот не может удалять экипаж (403)
        self.client.force_login(self.pilot_user)
        resp_pilot = self.client.post(url, data=payload, content_type='application/json', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp_pilot.status_code, 403)

        # 2. Руководство не может удалять экипаж (403)
        self.client.force_login(self.manager_user)
        resp_manager = self.client.post(url, data=payload, content_type='application/json', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp_manager.status_code, 403)

        # 3. Планировщик успешно удаляет экипаж (200)
        self.client.force_login(self.planner_user)
        resp_planner = self.client.post(url, data=payload, content_type='application/json', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp_planner.status_code, 200)
        self.assertFalse(FlightCrew.objects.filter(id=self.crew.id).exists())

    def test_crew_note_creation_by_assigned_pilot(self):
        """Проверяет, что назначенный член экипажа может оставить пометку к своему рейсу."""
        url = reverse('flight_planning:save_crew_note_api', kwargs={'crew_id': self.crew.id})
        payload = {'message': 'Погода по ПВП, готовность 100%'}

        # Назначенный пилот успешно добавляет пометку
        self.client.force_login(self.pilot_user)
        resp = self.client.post(url, data=payload, content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(FlightCrewNote.objects.filter(crew=self.crew, author=self.pilot_user).exists())


class FlightPlanningDocumentWorkflowTests(TestCase):
    """Тестирование моделей, сервисов снимков (снапшотов), диффов и документооборота расстановки экипажей."""

    def setUp(self):
        """Создает тестовых пользователей, МПД, ВС и экипажи."""
        self.client = Client()

        self.planner_user = DataBaseUser.objects.create_user(
            username='doc_planner',
            password='password123',
            last_name='Иванов',
            first_name='Иван'
        )
        self.manager_user = DataBaseUser.objects.create_user(
            username='doc_manager',
            password='password123',
            last_name='Руководителев',
            first_name='Роман'
        )
        self.pilot_1 = DataBaseUser.objects.create_user(
            username='pilot_1',
            password='password123',
            last_name='Петров',
            first_name='Петр'
        )
        self.pilot_2 = DataBaseUser.objects.create_user(
            username='pilot_2',
            password='password123',
            last_name='Сидоров',
            first_name='Сергей'
        )

        planner_group, _ = Group.objects.get_or_create(name=GROUP_FLIGHT_PLANNERS)
        manager_group, _ = Group.objects.get_or_create(name=GROUP_FLIGHT_MANAGEMENT)
        crew_group, _ = Group.objects.get_or_create(name=GROUP_FLIGHT_CREW)

        self.planner_user.groups.add(planner_group)
        self.manager_user.groups.add(manager_group)
        self.pilot_1.groups.add(crew_group)
        self.pilot_2.groups.add(crew_group)

        self.mpd = PlaceProductionActivity.objects.create(name='МПД Восток', in_planning=True)
        self.type_prop = TypeProperty.objects.create(type_property='Ми-8Т')
        self.aircraft = Estate.objects.create(registration_number='RA-04111', type_property=self.type_prop)

        self.year = 2026
        self.month = 9
        self.date_1 = datetime.date(self.year, self.month, 5)

        # Создаем экипаж в сентябре 2026
        self.crew = FlightCrew.objects.create(
            mpd=self.mpd,
            aircraft=self.aircraft,
            date=self.date_1,
            created_by=self.planner_user
        )
        CrewMember.objects.create(crew=self.crew, member=self.pilot_1, role='commander')
        PilotAssignment.objects.create(
            pilot=self.pilot_1,
            mpd=self.mpd,
            date=self.date_1,
            crew=self.crew,
            role_in_crew='commander'
        )

    def test_document_number_generation_and_creation(self):
        """Проверяет генерацию номера вида ММ-ВВ/ГГГГ и создание документа расстановки."""
        from flight_planning.services import (
            get_next_document_number,
            create_planning_document,
            approve_planning_document,
            get_latest_approved_document,
            get_pending_document
        )
        from flight_planning.models import FlightPlanningDocument

        doc_number, version = get_next_document_number(self.year, self.month)
        self.assertEqual(doc_number, "09-01/2026")
        self.assertEqual(version, 1)

        # 1. Диспетчер создает первую редакцию
        doc_1 = create_planning_document(
            year=self.year,
            month=self.month,
            author=self.planner_user,
            reason="Плановая расстановка на сентябрь"
        )
        self.assertEqual(doc_1.number, "09-01/2026")
        self.assertEqual(doc_1.version, 1)
        self.assertEqual(doc_1.status, "pending")
        self.assertEqual(doc_1.author, self.planner_user)
        self.assertTrue(doc_1.snapshot_data)
        self.assertEqual(len(doc_1.diff_data), 0)

        # 2. Руководитель утверждает первую редакцию
        approve_planning_document(doc_1, approver=self.manager_user)
        doc_1.refresh_from_db()
        self.assertEqual(doc_1.status, "approved")
        self.assertEqual(doc_1.approved_by, self.manager_user)
        self.assertIsNotNone(doc_1.approved_at)

        latest = get_latest_approved_document(self.year, self.month)
        self.assertEqual(latest.id, doc_1.id)

        # 3. Вносим изменения в сетку: заменяем КВС на pilot_2
        CrewMember.objects.filter(crew=self.crew).update(member=self.pilot_2)
        PilotAssignment.objects.filter(crew=self.crew).update(pilot=self.pilot_2)

        # 4. Формируем вторую редакцию (версию 2)
        doc_number_2, version_2 = get_next_document_number(self.year, self.month)
        self.assertEqual(doc_number_2, "09-02/2026")
        self.assertEqual(version_2, 2)

        doc_2 = create_planning_document(
            year=self.year,
            month=self.month,
            author=self.planner_user,
            reason="Замена КВС в связи с командировкой"
        )
        self.assertEqual(doc_2.number, "09-02/2026")
        self.assertEqual(doc_2.version, 2)
        self.assertEqual(doc_2.previous_document, doc_1)
        self.assertTrue(len(doc_2.diff_data) > 0)
        self.assertEqual(doc_2.diff_data[0]['change_type'], 'member_replaced')

        # 5. Утверждаем вторую редакцию -> первая должна стать архивной
        approve_planning_document(doc_2, approver=self.manager_user)
        doc_1.refresh_from_db()
        doc_2.refresh_from_db()

        self.assertEqual(doc_1.status, "archived")
        self.assertEqual(doc_2.status, "approved")

        latest_new = get_latest_approved_document(self.year, self.month)
        self.assertEqual(latest_new.id, doc_2.id)

    def test_document_views_access_and_print(self):
        """Интеграционный тест представлений журнала, карточки документа и печатной формы."""
        from flight_planning.services import create_planning_document, approve_planning_document

        doc = create_planning_document(
            year=self.year,
            month=self.month,
            author=self.planner_user,
            reason="Плановая расстановка"
        )

        list_url = reverse('flight_planning:document_list')
        detail_url = reverse('flight_planning:document_detail', kwargs={'pk': doc.id})
        print_url = reverse('flight_planning:document_print', kwargs={'pk': doc.id})
        approve_url = reverse('flight_planning:document_approve', kwargs={'pk': doc.id})

        # Пилот может просматривать журнал, карточку и печатную форму
        self.client.force_login(self.pilot_1)
        self.assertEqual(self.client.get(list_url).status_code, 200)
        self.assertEqual(self.client.get(detail_url).status_code, 200)
        self.assertEqual(self.client.get(print_url).status_code, 200)

        # Но пилот НЕ может утвердить документ (403)
        self.assertEqual(self.client.post(approve_url).status_code, 403)

        # Руководитель может утвердить документ
        self.client.force_login(self.manager_user)
        resp_approve = self.client.post(approve_url, follow=True)
        self.assertEqual(resp_approve.status_code, 200)
        doc.refresh_from_db()
        self.assertEqual(doc.status, 'approved')

    def test_pilot_my_schedule_with_approved_document(self):
        """Проверяет отображение личного графика пилота из утвержденного снимка без AttributeError."""
        from flight_planning.services import create_planning_document, approve_planning_document

        doc = create_planning_document(
            year=self.year,
            month=self.month,
            author=self.planner_user,
            reason="Плановая расстановка для графика"
        )
        approve_planning_document(doc, approver=self.manager_user)

        # 1. Пилот открывает страницу своего графика /flight/my-schedule/
        self.client.force_login(self.pilot_1)
        schedule_url = reverse('flight_planning:my_schedule') + f'?year={self.year}&month={self.month}'
        response = self.client.get(schedule_url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_official'])
        self.assertIsNotNone(response.context['latest_approved_doc'])
        self.assertEqual(response.context['latest_approved_doc'].id, doc.id)

        grouped = response.context['grouped_schedule']
        self.assertTrue(len(grouped) > 0)
        # Находим интервал с МПД
        work_intervals = [g for g in grouped if not g['is_gap']]
        self.assertEqual(len(work_intervals), 1)
        self.assertEqual(work_intervals[0]['mpd_name'], self.mpd.name)
        self.assertEqual(work_intervals[0]['days_count'], 1)

    def test_get_pilot_schedule_from_snapshot_direct(self):
        """Прямое тестирование сервиса get_pilot_schedule_from_snapshot."""
        from flight_planning.services import create_planning_document, get_pilot_schedule_from_snapshot

        doc = create_planning_document(
            year=self.year,
            month=self.month,
            author=self.planner_user,
            reason="Тест снимка"
        )

        schedule = get_pilot_schedule_from_snapshot(
            doc.snapshot_data,
            pilot_id=self.pilot_1.id,
            year=self.year,
            month=self.month
        )
        self.assertIsInstance(schedule, list)
        work_items = [s for s in schedule if not s['is_gap']]
        self.assertEqual(len(work_items), 1)
        self.assertEqual(work_items[0]['mpd_name'], self.mpd.name)

    def test_pilot_my_schedule_api_with_approved_document(self):
        """Проверяет получение графика через REST API /flight/api/my-schedule/."""
        from flight_planning.services import create_planning_document, approve_planning_document

        doc = create_planning_document(
            year=self.year,
            month=self.month,
            author=self.planner_user,
            reason="Тест API графика"
        )
        approve_planning_document(doc, approver=self.manager_user)

        self.client.force_login(self.pilot_1)
        api_url = reverse('flight_planning:api_my_schedule') + f'?year={self.year}&month={self.month}'
        response = self.client.get(api_url)

        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertTrue(json_data.get('is_official'))
        self.assertEqual(json_data.get('document_id'), doc.id)
        self.assertTrue(len(json_data.get('schedule', [])) > 0)


class PeriodicChecksTests(TestCase):
    """Тестирование моделей, сервисов и представлений модуля «Периодические проверки»."""

    def setUp(self):
        self.client = Client()
        self.planner_user = DataBaseUser.objects.create_user(
            username='planner_checks',
            password='password123',
            last_name='Планировщиков',
            first_name='Иван'
        )
        self.pilot = DataBaseUser.objects.create_user(
            username='pilot_checks',
            password='password123',
            last_name='Тестов',
            first_name='Алексей'
        )

        planner_group, _ = Group.objects.get_or_create(name=GROUP_FLIGHT_PLANNERS)
        crew_group, _ = Group.objects.get_or_create(name=GROUP_FLIGHT_CREW)
        self.planner_user.groups.add(planner_group)
        self.pilot.groups.add(crew_group)

        self.mi8_type = TypeProperty.objects.create(type_property='Ми-8')

        # Создаем базовые типы проверок
        self.check_type_sim = PeriodicCheckType.objects.create(
            name='Тренажер',
            code='SIMULATOR',
            aircraft_type=self.mi8_type,
            validity_months=6,
            order=1
        )
        self.check_type_vlek = PeriodicCheckType.objects.create(
            name='ВЛЭК',
            code='VLEK',
            aircraft_type=None,
            validity_months=12,
            order=2
        )

    def test_calculate_check_end_date(self):
        """Проверка точного вычисления даты окончания действия проверки."""
        from flight_planning.services import calculate_check_end_date

        start_date = datetime.date(2026, 7, 28)
        # 6 месяцев -> 2027-01-28 (или с учетом дней)
        end_date = calculate_check_end_date(start_date, validity_months=6)
        self.assertEqual(end_date, datetime.date(2027, 1, 28))

        # 12 месяцев -> 2027-07-28
        end_date_12 = calculate_check_end_date(start_date, validity_months=12)
        self.assertEqual(end_date_12, datetime.date(2027, 7, 28))

    def test_pilot_periodic_check_status_evaluation(self):
        """Проверка вычисления статусов проверок (missing, valid, warning, expired)."""
        from flight_planning.models import PeriodicCheckRecord
        from flight_planning.services import get_pilot_periodic_check_status

        target_date = datetime.date(2026, 8, 1)

        # 1. До создания записей - статус 'missing' (не пройдено)
        status_init = get_pilot_periodic_check_status(self.pilot.id, target_date, self.mi8_type.id)
        self.assertTrue(status_init['has_issues'])
        self.assertTrue(status_init['has_missing'])

        # 2. Создаем действующую запись по тренажеру
        rec_sim = PeriodicCheckRecord.objects.create(
            employee=self.pilot,
            check_type=self.check_type_sim,
            aircraft_type=self.mi8_type,
            start_date=datetime.date(2026, 7, 1),
            end_date=datetime.date(2027, 1, 1),
            created_by=self.planner_user
        )
        self.assertEqual(rec_sim.days_remaining_on_date(target_date), 153)
        self.assertEqual(rec_sim.status_on_date(target_date), 'valid')

        # 3. Создаем просроченную запись по ВЛЭК
        rec_vlek = PeriodicCheckRecord.objects.create(
            employee=self.pilot,
            check_type=self.check_type_vlek,
            aircraft_type=None,
            start_date=datetime.date(2025, 1, 1),
            end_date=datetime.date(2026, 1, 1),
            created_by=self.planner_user
        )
        self.assertEqual(rec_vlek.status_on_date(target_date), 'expired')

        # 4. Проверяем сводный статус сотрудника
        summary = get_pilot_periodic_check_status(self.pilot.id, target_date, self.mi8_type.id)
        self.assertTrue(summary['has_issues'])
        self.assertTrue(summary['has_expired'])
        self.assertIn('ВЛЭК', summary['summary_text'])

    def test_periodic_check_views_and_api(self):
        """Проверка работы HTTP-представлений и API модуля проверок."""
        self.client.force_login(self.planner_user)

        # Список проверок (все вкладки)
        res_list = self.client.get(reverse('flight_planning:periodic_check_list'))
        self.assertEqual(res_list.status_code, 200)

        res_matrix = self.client.get(reverse('flight_planning:periodic_check_list') + '?tab=matrix')
        self.assertEqual(res_matrix.status_code, 200)

        res_types = self.client.get(reverse('flight_planning:periodic_check_list') + '?tab=types')
        self.assertEqual(res_types.status_code, 200)

        # API расчета даты окончания
        calc_res = self.client.get(reverse('flight_planning:calculate_check_date_api'), {
            'check_type_id': self.check_type_sim.id,
            'start_date': '2026-08-15'
        })
        self.assertEqual(calc_res.status_code, 200)
        calc_json = calc_res.json()
        self.assertEqual(calc_json['status'], 'success')
        self.assertEqual(calc_json['end_date'], '2027-02-15')

        # API статусов проверок пилота
        pilot_checks_res = self.client.get(reverse('flight_planning:get_pilot_checks_api', kwargs={'pilot_id': self.pilot.id}))
        self.assertEqual(pilot_checks_res.status_code, 200)
        self.assertEqual(pilot_checks_res.json()['status'], 'success')

        # API истории проверок сотрудника
        history_res = self.client.get(reverse('flight_planning:get_check_history_api'), {
            'employee_id': self.pilot.id,
            'check_type_id': self.check_type_sim.id
        })
        self.assertEqual(history_res.status_code, 200)
        history_json = history_res.json()
        self.assertEqual(history_json['status'], 'success')
        self.assertEqual(history_json['employee_id'], self.pilot.id)
        self.assertEqual(history_json['check_type_id'], self.check_type_sim.id)
        self.assertGreaterEqual(history_json['history_count'], 1)

    def test_superseded_check_renewal_behavior_and_kpi(self):
        """Проверка разграничения устаревших (продленных) и актуальных проверок, расчета KPI и бейджей."""
        # 1. Создаем старую запись, закончившуюся 1 августа
        rec_old = PeriodicCheckRecord.objects.create(
            employee=self.pilot,
            check_type=self.check_type_tech,
            aircraft_type=self.mi8_type,
            start_date=datetime.date(2026, 2, 1),
            end_date=datetime.date(2026, 8, 1),
            document_number='СТАРЫЙ-1',
            created_by=self.planner_user
        )

        # Пока новой записи нет: rec_old не superseded, просрочена
        self.assertFalse(rec_old.is_superseded)

        # 2. Создаем новую продленную запись со 2 августа
        rec_new = PeriodicCheckRecord.objects.create(
            employee=self.pilot,
            check_type=self.check_type_tech,
            aircraft_type=self.mi8_type,
            start_date=datetime.date(2026, 8, 2),
            end_date=datetime.date(2027, 2, 2),
            document_number='НОВЫЙ-2',
            created_by=self.planner_user
        )

        # Теперь rec_old является superseded (продлена), а rec_new - актуальной
        self.assertTrue(rec_old.is_superseded)
        self.assertEqual(rec_old.get_successor().id, rec_new.id)
        self.assertFalse(rec_new.is_superseded)

        # 3. Проверяем представление дашборда: старая запись не должна попадать в expired_records_count
        self.client.force_login(self.planner_user)
        response = self.client.get(reverse('flight_planning:periodic_check_list'))
        self.assertEqual(response.status_code, 200)
        # В контексте expired_records_count учитывает только актуальные проверки
        self.assertEqual(response.context['expired_records_count'], 0)
        self.assertGreaterEqual(response.context['valid_records_count'], 1)
        self.assertGreaterEqual(response.context['renewed_records_count'], 1)

        # Фильтр по просроченным не должен возвращать rec_old
        res_expired = self.client.get(reverse('flight_planning:periodic_check_list') + '?status=expired')
        self.assertEqual(len(res_expired.context['records']), 0)

        # Фильтр по продленным должен возвращать rec_old
        res_renewed = self.client.get(reverse('flight_planning:periodic_check_list') + '?status=renewed')
        self.assertEqual(len(res_renewed.context['records']), 1)
        self.assertEqual(res_renewed.context['records'][0].id, rec_old.id)

    def test_dismissed_employee_check_monitoring_exclusion(self):
        """Проверка исключения уволенных и неактивных сотрудников из мониторинга проверок."""
        from flight_planning.services import get_pilot_periodic_check_status, get_allowed_staff_queryset

        # Активный сотрудник
        self.pilot.is_active = True
        self.pilot.save()
        st_active = get_pilot_periodic_check_status(self.pilot.id)
        self.assertFalse(st_active.get('is_dismissed', False))

        # Уволенный / неактивный сотрудник
        self.pilot.is_active = False
        self.pilot.save()

        st_dismissed = get_pilot_periodic_check_status(self.pilot.id)
        self.assertTrue(st_dismissed.get('is_dismissed', False))
        self.assertFalse(st_dismissed['has_issues'])
        self.assertFalse(st_dismissed['has_expired'])
        self.assertFalse(st_dismissed['has_warning'])

        # Уволенный сотрудник не должен попадать в get_allowed_staff_queryset
        allowed_qs = get_allowed_staff_queryset(self.planner_user)
        self.assertNotIn(self.pilot, allowed_qs)

        # Восстанавливаем активность для других тестов
        self.pilot.is_active = True
        self.pilot.save()

    def test_individual_employee_check_assignments(self):
        """Проверка индивидуального закрепления обязательных проверок за сотрудником."""
        from flight_planning.models import EmployeeRequiredCheck
        from flight_planning.services import (
            get_employee_check_assignments,
            save_employee_check_assignments,
            get_pilot_periodic_check_status
        )

        # 1. Назначаем сотруднику только Тренажер (SIMULATOR), а ВЛЭК делаем необязательным
        save_employee_check_assignments(
            employee_id=self.pilot.id,
            check_type_ids=[self.check_type_sim.id],
            assigned_by=self.planner_user
        )

        # 2. Проверяем API получения закреплений
        assignments_data = get_employee_check_assignments(self.pilot.id)
        self.assertEqual(assignments_data['status'], 'success')
        self.assertIn(self.check_type_sim.id, assignments_data['assigned_check_type_ids'])
        self.assertNotIn(self.check_type_vlek.id, assignments_data['assigned_check_type_ids'])

        # 3. Проверяем статус: ВЛЭК больше не должен попадать в список обязательных проверок
        target_date = datetime.date(2026, 8, 28)
        status_info = get_pilot_periodic_check_status(self.pilot.id, target_date=target_date, aircraft_type_id=self.mi8_type.id)
        detail_ids = [d['check_type_id'] for d in status_info['details']]
        self.assertIn(self.check_type_sim.id, detail_ids)
        self.assertNotIn(self.check_type_vlek.id, detail_ids)

        # 4. Проверяем сохранение через HTTP API
        self.client.force_login(self.planner_user)
        api_res = self.client.post(
            reverse('flight_planning:save_employee_check_assignments_api'),
            data={'employee_id': self.pilot.id, 'check_type_ids': [self.check_type_vlek.id]}
        )
        self.assertEqual(api_res.status_code, 200)
        self.assertEqual(api_res.json()['status'], 'success')

        # Теперь закреплен только ВЛЭК
        updated_assignments = get_employee_check_assignments(self.pilot.id)
        self.assertIn(self.check_type_vlek.id, updated_assignments['assigned_check_type_ids'])
        self.assertNotIn(self.check_type_sim.id, updated_assignments['assigned_check_type_ids'])



class EmployeeStatusTests(TestCase):
    """Тестирование моделей, сервисов, проверки конфликтов и представлений модуля «Состояния сотрудников»."""

    def setUp(self):
        self.client = Client()
        self.planner_user = DataBaseUser.objects.create_user(
            username='planner_status_user',
            password='password123',
            is_staff=True
        )
        planner_group, _ = Group.objects.get_or_create(name='Диспетчер по планированию полетов')
        self.planner_user.groups.add(planner_group)

        self.pilot = DataBaseUser.objects.create_user(
            username='pilot_status_test',
            password='password123',
            first_name='Сергей',
            last_name='Петров'
        )

        self.mpd = PlaceProductionActivity.objects.create(
            name='МПД Север',
            in_planning=True
        )

        self.status_vacation = EmployeeStatusType.objects.create(
            name='Отпуск',
            code='VACATION',
            color='#f59e0b',
            is_blocking=True,
            order=10
        )
        self.status_sick = EmployeeStatusType.objects.create(
            name='Больничный',
            code='SICK_LEAVE',
            color='#ef4444',
            is_blocking=True,
            order=20
        )
        self.status_other = EmployeeStatusType.objects.create(
            name='Прочее',
            code='OTHER',
            color='#64748b',
            is_blocking=False,
            order=30
        )

    def test_employee_status_models_and_methods(self):
        """Проверка методов модели EmployeeStatusRecord и валидации."""
        from django.core.exceptions import ValidationError

        rec = EmployeeStatusRecord.objects.create(
            employee=self.pilot,
            status_type=self.status_vacation,
            start_date=datetime.date(2026, 9, 1),
            end_date=datetime.date(2026, 9, 14),
            document_number='12-ОТ',
            created_by=self.planner_user
        )

        self.assertEqual(rec.duration_days, 14)
        self.assertTrue(rec.is_active_on_date(datetime.date(2026, 9, 1)))
        self.assertTrue(rec.is_active_on_date(datetime.date(2026, 9, 14)))
        self.assertFalse(rec.is_active_on_date(datetime.date(2026, 8, 31)))
        self.assertFalse(rec.is_active_on_date(datetime.date(2026, 9, 15)))

        # Некорректный интервал дат
        invalid_rec = EmployeeStatusRecord(
            employee=self.pilot,
            status_type=self.status_sick,
            start_date=datetime.date(2026, 9, 10),
            end_date=datetime.date(2026, 9, 5)
        )
        with self.assertRaises(ValidationError):
            invalid_rec.clean()

    def test_check_crew_member_conflicts_with_employee_status(self):
        """Проверка обнаружения конфликтов при назначении сотрудника с активным состоянием."""
        from flight_planning.services import check_crew_member_conflicts

        EmployeeStatusRecord.objects.create(
            employee=self.pilot,
            status_type=self.status_sick,
            start_date=datetime.date(2026, 9, 5),
            end_date=datetime.date(2026, 9, 15),
            document_number='БЛ-9988',
            created_by=self.planner_user
        )

        # 1. Пересекающийся диапазон дат -> должен вернуть конфликт
        conflicts = check_crew_member_conflicts(
            mpd_id=self.mpd.id,
            start_date=datetime.date(2026, 9, 10),
            end_date=datetime.date(2026, 9, 20),
            members=[{'member_id': self.pilot.id, 'role': 'commander'}]
        )
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]['conflict_kind'], 'employee_status')
        self.assertEqual(conflicts[0]['status_name'], 'Больничный')
        self.assertIn('Больничный', conflicts[0]['description'])
        self.assertIn('БЛ-9988', conflicts[0]['description'])

        # 2. Непересекающийся диапазон дат -> конфликтов нет
        no_conflicts = check_crew_member_conflicts(
            mpd_id=self.mpd.id,
            start_date=datetime.date(2026, 9, 16),
            end_date=datetime.date(2026, 9, 25),
            members=[{'member_id': self.pilot.id, 'role': 'commander'}]
        )
        self.assertEqual(len(no_conflicts), 0)

    def test_month_employee_statuses_map_and_pilot_api(self):
        """Проверка сервиса выборки состояний за месяц и REST API."""
        from flight_planning.services import get_month_employee_statuses_map, get_pilot_employee_statuses

        rec = EmployeeStatusRecord.objects.create(
            employee=self.pilot,
            status_type=self.status_vacation,
            start_date=datetime.date(2026, 9, 1),
            end_date=datetime.date(2026, 9, 10),
            document_number='ОТ-1',
            created_by=self.planner_user
        )

        month_map = get_month_employee_statuses_map([self.pilot.id], year=2026, month=9)
        self.assertIn(self.pilot.id, month_map)
        self.assertEqual(len(month_map[self.pilot.id]), 1)
        self.assertEqual(month_map[self.pilot.id][0]['status_name'], 'Отпуск')

        pilot_data = get_pilot_employee_statuses(self.pilot.id, target_date=datetime.date(2026, 9, 5))
        self.assertTrue(pilot_data['has_active_status'])
        self.assertEqual(pilot_data['active_status_name'], 'Отпуск')

    def test_employee_status_views(self):
        """Проверка работы дашборда и CRUD представлений модуля состояний."""
        self.client.force_login(self.planner_user)

        # 1. Дашборд состояний (все вкладки)
        res_list = self.client.get(reverse('flight_planning:employee_status_list'))
        self.assertEqual(res_list.status_code, 200)

        res_matrix = self.client.get(reverse('flight_planning:employee_status_list') + '?tab=matrix')
        self.assertEqual(res_matrix.status_code, 200)

        res_types = self.client.get(reverse('flight_planning:employee_status_list') + '?tab=types')
        self.assertEqual(res_types.status_code, 200)

        # 2. Создание записи состояния
        res_create = self.client.post(reverse('flight_planning:employee_status_create'), {
            'employee': self.pilot.id,
            'status_type': self.status_vacation.id,
            'start_date': '2026-09-01',
            'end_date': '2026-09-14',
            'document_number': 'ПРИКАЗ-45'
        })
        self.assertEqual(res_create.status_code, 302)
        self.assertTrue(EmployeeStatusRecord.objects.filter(document_number='ПРИКАЗ-45').exists())

        # 3. API состояний пилота
        res_api = self.client.get(reverse('flight_planning:get_pilot_employee_statuses_api', kwargs={'pilot_id': self.pilot.id}))
        self.assertEqual(res_api.status_code, 200)
        self.assertEqual(res_api.json()['status'], 'success')

    def test_allowed_staff_filtering_by_job_affiliation(self):
        """Проверка разграничения видимости персонала по принадлежности должности (Общий/Летный/Инженерный состав)."""
        from flight_planning.services import (
            get_user_personnel_scope,
            get_allowed_staff_queryset,
            FLIGHT_CREW_JOB_NAMES,
            ENGINEERING_STAFF_JOB_NAMES,
            ALL_STAFF_JOB_NAMES
        )
        from customers_app.models import Job, DataBaseUserWorkProfile

        # Создаем должности
        job_flight = Job.objects.create(name='Командир воздушного судна Ми-8', type_of_job='1')
        job_eng = Job.objects.create(name='Инженер по эксплуатации ВС', type_of_job='2')
        job_general = Job.objects.create(name='Руководитель полетов', type_of_job='0')

        # Создаем пользователей
        user_flight = DataBaseUser.objects.create_user(username='u_flight', password='pwd')
        user_flight.user_work_profile = DataBaseUserWorkProfile.objects.create(job=job_flight)
        user_flight.save()

        user_eng = DataBaseUser.objects.create_user(username='u_eng', password='pwd')
        user_eng.user_work_profile = DataBaseUserWorkProfile.objects.create(job=job_eng)
        user_eng.save()

        user_gen = DataBaseUser.objects.create_user(username='u_gen', password='pwd')
        user_gen.user_work_profile = DataBaseUserWorkProfile.objects.create(job=job_general)
        user_gen.save()

        # 1. Проверка определения области видимости
        self.assertEqual(get_user_personnel_scope(user_flight), '1')
        self.assertEqual(get_user_personnel_scope(user_eng), '2')
        self.assertEqual(get_user_personnel_scope(user_gen), '0')

        # 2. Проверка QuerySet
        qs_flight = get_allowed_staff_queryset(user=user_flight)
        self.assertIn(user_flight, qs_flight)
        self.assertNotIn(user_eng, qs_flight)

        qs_eng = get_allowed_staff_queryset(user=user_eng)
        self.assertIn(user_eng, qs_eng)
        self.assertNotIn(user_flight, qs_eng)

        qs_gen = get_allowed_staff_queryset(user=user_gen)
        self.assertIn(user_flight, qs_gen)
        self.assertIn(user_eng, qs_gen)




