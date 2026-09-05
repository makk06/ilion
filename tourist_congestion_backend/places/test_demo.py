from django.test import SimpleTestCase
from django.urls import reverse


class PlaceDemoTests(SimpleTestCase):
    def test_demo_page_renders_api_connected_interface(self):
        response = self.client.get(reverse('place-demo'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'places/demo.html')
        self.assertContains(response, 'ILION')
        self.assertContains(response, 'data-testid="place-results"')
        self.assertContains(response, '/static/places/demo.js')

    def test_demo_page_rejects_post(self):
        response = self.client.post(reverse('place-demo'))

        self.assertEqual(response.status_code, 405)
