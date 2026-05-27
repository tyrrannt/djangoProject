from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from customers_app.models import DataBaseUser
from hrdepartment_app.models import PlaceProductionActivity
from .models import PilotAssignment
import datetime

class FlightPlanningAPITests(APITestCase):
    def setUp(self):
        # Create user with required names
        self.user = DataBaseUser.objects.create_user(
            username='testpilot', 
            password='password',
            last_name='Иванов',
            first_name='Иван'
        )
        self.client.force_authenticate(user=self.user)

        # Create MPD
        self.mpd = PlaceProductionActivity.objects.create(name='Test MPD', in_planning=True)

        # Create assignment
        self.date = datetime.date.today()
        self.assignment = PilotAssignment.objects.create(
            pilot=self.user,
            mpd=self.mpd,
            date=self.date
        )

    def test_get_my_schedule(self):
        """
        Ensure we can get the authenticated user's schedule via API.
        """
        url = reverse('flight_planning:api_my_schedule')
        response = self.client.get(url, {'year': self.date.year, 'month': self.date.month})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Check that our MPD is mentioned in the schedule
        mpd_names = [item['mpd_name'] for item in response.data['schedule']]
        self.assertIn('Test MPD', mpd_names)

    def test_get_mpds(self):
        """
        Ensure we can get the list of MPDs.
        """
        url = reverse('flight_planning:api_mpd_list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(response.data) >= 1)
