import datetime

from django.test import TestCase, RequestFactory
from django.contrib.auth.models import AnonymousUser, User
from django.contrib.auth.models import Permission
from customers_app.models import DataBaseUser
from hrdepartment_app.models import OfficialMemo
from hrdepartment_app.views import OfficialMemoDetail


class OfficialMemoDetailViewTest(TestCase):
    def setUp(self):
        # Every test needs access to the request factory.
        # Create an instance of HttpRequest
        self.factory = RequestFactory()
        # Example object
        view_permission = Permission.objects.get(codename="view_officialmemo")
        self.user = DataBaseUser.objects.create_user(
            username="jacob",
            email="jacob@…",
            password="top_secret",
            first_name="Виталий",
            last_name="Шакиров",
            surname="Рустамович",
            title="Шакиров Виталий Рустамович",
        )
        self.user.user_permissions.add(view_permission)
        kwargs = {
            "person": self.user,
            "period_from": datetime.date(2023, 8, 1),
            "period_for": datetime.date(2023, 8, 1),
            "official_memo_type": "1",
        }
        self.official_memo = OfficialMemo.objects.create(**kwargs)

    def test_context_data(self):
        # Создайте экземпляр запроса GET.
        request = self.factory.get("/detail")

        # Напомним, что промежуточное ПО не поддерживается. Вы можете имитировать
        # авторизованный пользователь, установив request.user вручную.
        request.user = self.user

        # Test OfficialMemoDetail.as_view() as a logged in user.
        response = OfficialMemoDetail.as_view()(request, pk=self.official_memo.id)

        # # Check that user is logged in
        # print(response.context_data)
        # assert str(response.context_data["user"]) == "jacob"
        # assert response.status_code == 200

        # Check csrf_token exist in request
        # self.assertIn("csrf_token", response.context_data)
        self.assertIn("view", response.context_data)

        # Check change history in context
        self.assertIn("change_history", response.context_data)
