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
