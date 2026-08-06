from django.test import SimpleTestCase
from django.urls import reverse


class HealthzTests(SimpleTestCase):
    def test_healthz_returns_ok(self):
        response = self.client.get(reverse('healthz'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})

    def test_healthz_rejects_post_requests(self):
        response = self.client.post(reverse('healthz'))

        self.assertEqual(response.status_code, 405)
