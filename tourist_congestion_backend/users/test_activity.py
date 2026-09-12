import io
import tempfile
from datetime import timedelta
from PIL import Image
from django.test import override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APITestCase
from places.models import Place
from .models import User, Review, PointEntry, CompanionMember, Inquiry


class ActivityAPITests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email='owner@example.com', nickname='owner', password='Safe-password123!')
        self.other = User.objects.create_user(email='other@example.com', nickname='other', password='Safe-password123!')
        self.third = User.objects.create_user(email='third@example.com', nickname='third', password='Safe-password123!')
        self.place = Place.objects.create(name='Test place', category='park', region_code='1', address='test', latitude=37, longitude=127)
        self.client.force_authenticate(self.owner)

    def review(self):
        return self.client.post('/api/reviews', {'place_id': self.place.id, 'text': 'Good place', 'rating': 4}, format='json')

    def companion(self):
        return self.client.post('/api/companions', {'place_id': self.place.id, 'title': 'Walk', 'text': 'Join us', 'date': str(timezone.localdate()), 'capacity': 2}, format='json')

    def test_review_persistence_reward_once_and_ownership(self):
        response = self.review()
        self.assertEqual(response.status_code, 201)
        review_id = response.data['data']['review']['id']
        self.assertEqual(response.data['data']['points_awarded'], 50)
        self.assertEqual(self.review().data['data']['points_awarded'], 0)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.delete(f'/api/reviews/{review_id}').status_code, 404)
        for _ in range(2):
            self.assertEqual(self.client.post(f'/api/reviews/{review_id}/like').status_code, 200)
        self.assertEqual(Review.objects.get(pk=review_id).likes.count(), 1)
        self.client.force_authenticate(self.owner)
        self.assertEqual(len(self.client.get('/api/notifications').data['data']['items']), 1)
        self.client.delete(f'/api/reviews/{review_id}')
        self.assertEqual(self.review().data['data']['points_awarded'], 0)
        self.assertEqual(self.client.get('/api/points').data['data']['balance'], 50)
        self.assertEqual(PointEntry.objects.count(), 1)
        self.place.refresh_from_db()
        self.assertEqual(float(self.place.avg_rating), 4)

    def test_photo_upload_validation(self):
        stream = io.BytesIO()
        Image.new('RGB', (2, 2)).save(stream, format='PNG')
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            response = self.client.post('/api/reviews', {'place_id': self.place.id, 'text': 'Photo', 'photo': SimpleUploadedFile('photo.png', stream.getvalue(), content_type='image/png')}, format='multipart')
            self.assertEqual(response.status_code, 201)
            self.assertIn('/media/reviews/', response.data['data']['review']['photo_url'])
            self.assertFalse(response.data['data']['review']['visit_verified'])
        response = self.client.post('/api/reviews', {'place_id': self.place.id, 'text': 'Bad', 'photo': SimpleUploadedFile('bad.png', b'not an image', content_type='image/png')}, format='multipart')
        self.assertEqual(response.status_code, 400)

    def test_companion_capacity_membership_and_dates(self):
        response = self.companion()
        self.assertEqual(response.status_code, 201)
        pk = response.data['data']['id']
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.post(f'/api/companions/{pk}/join').status_code, 200)
        self.assertEqual(self.client.post(f'/api/companions/{pk}/join').data['data']['member_count'], 2)
        self.client.force_authenticate(self.third)
        self.assertEqual(self.client.post(f'/api/companions/{pk}/join').status_code, 409)
        self.assertEqual(self.client.patch(f'/api/companions/{pk}', {'title': 'Hijack'}, format='json').status_code, 404)
        self.client.force_authenticate(self.other)
        self.client.delete(f'/api/companions/{pk}/join')
        self.assertEqual(self.client.delete(f'/api/companions/{pk}/join').data['data']['member_count'], 1)
        self.assertEqual(CompanionMember.objects.filter(companion_id=pk).count(), 1)
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.patch(f'/api/companions/{pk}', {'date': str(timezone.localdate()-timedelta(days=1))}, format='json').status_code, 400)
        self.assertEqual(self.client.get('/api/companions?date=invalid').status_code, 400)

    def test_profile_recent_plan_inquiry_private_state(self):
        self.assertEqual(self.client.patch('/api/me', {'nickname': 'updated', 'preferences': {'notifications': False}}, format='json').status_code, 200)
        self.assertEqual(self.client.get('/api/me').data['data']['nickname'], 'updated')
        self.client.post('/api/recent-places', {'place_id': self.place.id}, format='json')
        self.client.post('/api/recent-places', {'place_id': self.place.id}, format='json')
        self.assertEqual(self.client.get('/api/recent-places').data['data']['place_ids'], [self.place.id])
        self.client.delete('/api/recent-places')
        self.assertEqual(self.client.get('/api/recent-places').data['data']['place_ids'], [])
        plan = self.client.post('/api/plans', {'title': 'Trip', 'date': str(timezone.localdate()), 'stops': [{'time': '12:00', 'place': 'Park'}]}, format='json')
        self.assertEqual(plan.status_code, 201)
        inquiry = self.client.post('/api/inquiries', {'subject': 'Help', 'text': 'Question', 'answer': 'Fake answer', 'status': 'answered'}, format='json')
        self.assertEqual(inquiry.status_code, 201)
        self.assertEqual(inquiry.data['data']['status'], 'received')
        self.assertEqual(inquiry.data['data']['answer'], '')
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get('/api/inquiries').data['data']['items'], [])
        self.assertEqual(self.client.delete(f"/api/plans/{plan.data['data']['id']}").status_code, 404)

    def test_public_read_authenticated_writes_and_cors(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/reviews').status_code, 200)
        self.assertEqual(self.review().status_code, 401)
        self.assertEqual(self.client.get('/api/points').status_code, 401)
        with override_settings(DEBUG=True):
            response = self.client.options('/api/reviews', HTTP_ORIGIN='http://localhost:7357')
            self.assertEqual(response['Access-Control-Allow-Origin'], 'http://localhost:7357')
        with override_settings(DEBUG=False, CORS_ALLOWED_ORIGINS=[]):
            response = self.client.options('/api/reviews', HTTP_ORIGIN='https://evil.example')
            self.assertNotIn('Access-Control-Allow-Origin', response)
