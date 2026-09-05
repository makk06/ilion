from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from places.models import Place

from .models import Favorite, Feedback, RefreshToken, User
from .views import FEEDBACK_COOLDOWN


def create_place(**overrides):
    fields = {
        'name': '테스트 장소',
        'category': '관광지',
        'region_code': '11000',
        'address': '서울 어딘가',
        'latitude': '37.5665',
        'longitude': '126.9780',
        'indoor_outdoor': Place.IndoorOutdoor.OUTDOOR,
    }
    fields.update(overrides)
    return Place.objects.create(**fields)


class SignupTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_signup_creates_user_and_returns_tokens(self):
        response = self.client.post(reverse('auth-signup'), {
            'email': 'test@example.com',
            'password': 'a-strong-password-123',
            'nickname': '테스트닉네임',
        })

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertTrue(body['success'])
        self.assertIn('access_token', body['data'])
        self.assertIn('refresh_token', body['data'])

        user = User.objects.get(email='test@example.com')
        self.assertEqual(user.provider, User.Provider.EMAIL)
        self.assertEqual(user.status, User.Status.ACTIVE)
        self.assertTrue(user.check_password('a-strong-password-123'))

    def test_signup_rejects_duplicate_nickname(self):
        User.objects.create_user(email='a@example.com', password='pw12345678', nickname='중복닉네임')

        response = self.client.post(reverse('auth-signup'), {
            'email': 'b@example.com',
            'password': 'pw12345678',
            'nickname': '중복닉네임',
        })

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])


class LoginTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='login@example.com',
            password='correct-password',
            nickname='로그인유저',
        )

    def test_login_success_issues_tokens_and_replaces_previous_session(self):
        first_login = self.client.post(reverse('auth-login'), {
            'email': 'login@example.com',
            'password': 'correct-password',
        })
        self.assertEqual(first_login.status_code, 200)
        self.assertEqual(RefreshToken.objects.filter(user=self.user).count(), 1)
        first_token_id = RefreshToken.objects.get(user=self.user).id

        second_login = self.client.post(reverse('auth-login'), {
            'email': 'login@example.com',
            'password': 'correct-password',
        })
        self.assertEqual(second_login.status_code, 200)

        tokens = RefreshToken.objects.filter(user=self.user)
        self.assertEqual(tokens.count(), 1)
        self.assertNotEqual(tokens.first().id, first_token_id)

    def test_login_rejects_wrong_password(self):
        response = self.client.post(reverse('auth-login'), {
            'email': 'login@example.com',
            'password': 'wrong-password',
        })

        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()['success'])


class GoogleLoginTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch('users.views.google_id_token.verify_oauth2_token')
    def test_google_login_creates_new_user(self, mock_verify):
        mock_verify.return_value = {
            'sub': 'google-sub-123',
            'email': 'googleuser@example.com',
            'picture': 'https://example.com/photo.jpg',
        }

        response = self.client.post(reverse('auth-google'), {'id_token': 'dummy-token'})

        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email='googleuser@example.com')
        self.assertEqual(user.provider, User.Provider.GOOGLE)
        self.assertEqual(user.provider_user_id, 'google-sub-123')
        self.assertFalse(user.has_usable_password())

    @patch('users.views.google_id_token.verify_oauth2_token')
    def test_google_login_links_existing_email_account(self, mock_verify):
        User.objects.create_user(email='existing@example.com', password='pw12345678', nickname='기존유저')
        mock_verify.return_value = {
            'sub': 'google-sub-456',
            'email': 'existing@example.com',
            'picture': None,
        }

        response = self.client.post(reverse('auth-google'), {'id_token': 'dummy-token'})

        self.assertEqual(response.status_code, 200)
        user = User.objects.get(email='existing@example.com')
        self.assertEqual(user.provider_user_id, 'google-sub-456')


class RefreshAndLogoutTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='refresh@example.com',
            password='correct-password',
            nickname='리프레시유저',
        )
        login_response = self.client.post(reverse('auth-login'), {
            'email': 'refresh@example.com',
            'password': 'correct-password',
        })
        self.tokens = login_response.json()['data']

    def test_refresh_issues_new_access_token(self):
        response = self.client.post(reverse('auth-refresh'), {
            'refresh_token': self.tokens['refresh_token'],
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn('access_token', response.json()['data'])

    def test_refresh_rejects_token_after_logout(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.tokens["access_token"]}')
        logout_response = self.client.post(reverse('auth-logout'))
        self.assertEqual(logout_response.status_code, 200)

        self.client.credentials()
        refresh_response = self.client.post(reverse('auth-refresh'), {
            'refresh_token': self.tokens['refresh_token'],
        })
        self.assertEqual(refresh_response.status_code, 401)


class RandomNicknameTests(TestCase):
    def test_returns_unique_nickname(self):
        response = APIClient().get(reverse('auth-nickname-random'))

        self.assertEqual(response.status_code, 200)
        nickname = response.json()['data']['nickname']
        self.assertFalse(User.objects.filter(nickname=nickname).exists())


class FavoriteTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='fav@example.com',
            password='correct-password',
            nickname='즐겨찾기유저',
        )
        self.place = create_place(name='좋아하는 장소')

        login_response = self.client.post(reverse('auth-login'), {
            'email': 'fav@example.com',
            'password': 'correct-password',
        })
        access_token = login_response.json()['data']['access_token']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')

    def test_requires_authentication(self):
        response = APIClient().get(reverse('favorite-list-create'))
        self.assertEqual(response.status_code, 401)

    def test_add_favorite(self):
        response = self.client.post(reverse('favorite-list-create'), {'place_id': self.place.id})

        self.assertEqual(response.status_code, 201)
        self.assertTrue(Favorite.objects.filter(user=self.user, place=self.place).exists())

    def test_add_favorite_twice_is_idempotent(self):
        self.client.post(reverse('favorite-list-create'), {'place_id': self.place.id})
        second_response = self.client.post(reverse('favorite-list-create'), {'place_id': self.place.id})

        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(Favorite.objects.filter(user=self.user, place=self.place).count(), 1)

    def test_add_favorite_rejects_nonexistent_place(self):
        response = self.client.post(reverse('favorite-list-create'), {'place_id': 999999})

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])

    def test_list_favorites_returns_place_ids(self):
        another_place = create_place(name='다른 장소')
        Favorite.objects.create(user=self.user, place=self.place)
        Favorite.objects.create(user=self.user, place=another_place)

        response = self.client.get(reverse('favorite-list-create'))

        self.assertEqual(response.status_code, 200)
        place_ids = response.json()['data']['place_ids']
        self.assertCountEqual(place_ids, [self.place.id, another_place.id])

    def test_delete_favorite(self):
        Favorite.objects.create(user=self.user, place=self.place)

        response = self.client.delete(reverse('favorite-delete', args=[self.place.id]))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Favorite.objects.filter(user=self.user, place=self.place).exists())

    def test_delete_nonexistent_favorite_returns_404(self):
        response = self.client.delete(reverse('favorite-delete', args=[self.place.id]))

        self.assertEqual(response.status_code, 404)

    def test_cannot_see_or_delete_other_users_favorite(self):
        other_user = User.objects.create_user(
            email='other@example.com',
            password='correct-password',
            nickname='다른유저',
        )
        Favorite.objects.create(user=other_user, place=self.place)

        list_response = self.client.get(reverse('favorite-list-create'))
        self.assertEqual(list_response.json()['data']['place_ids'], [])

        delete_response = self.client.delete(reverse('favorite-delete', args=[self.place.id]))
        self.assertEqual(delete_response.status_code, 404)


class FeedbackTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='feedback@example.com',
            password='correct-password',
            nickname='피드백유저',
        )
        self.place = create_place(name='피드백 장소')

        login_response = self.client.post(reverse('auth-login'), {
            'email': 'feedback@example.com',
            'password': 'correct-password',
        })
        access_token = login_response.json()['data']['access_token']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')

    def test_requires_authentication(self):
        response = APIClient().get(reverse('feedback-list-create'))
        self.assertEqual(response.status_code, 401)

    def test_create_feedback(self):
        response = self.client.post(reverse('feedback-list-create'), {
            'place_id': self.place.id,
            'feedback_type': Feedback.FeedbackType.CROWD,
            'value': 72,
            'memo': '생각보다 붐볐어요',
        })

        self.assertEqual(response.status_code, 201)
        data = response.json()['data']
        self.assertEqual(data['place_id'], self.place.id)
        self.assertEqual(data['value'], 72)

        feedback = Feedback.objects.get(user=self.user, place=self.place)
        self.assertEqual(feedback.feedback_type, Feedback.FeedbackType.CROWD)
        self.assertEqual(feedback.memo, '생각보다 붐볐어요')

    def test_create_feedback_without_optional_fields(self):
        response = self.client.post(reverse('feedback-list-create'), {
            'place_id': self.place.id,
            'feedback_type': Feedback.FeedbackType.PLACE,
        })

        self.assertEqual(response.status_code, 201)
        feedback = Feedback.objects.get(user=self.user, place=self.place)
        self.assertIsNone(feedback.value)

    def test_rejects_value_out_of_range(self):
        response = self.client.post(reverse('feedback-list-create'), {
            'place_id': self.place.id,
            'feedback_type': Feedback.FeedbackType.CROWD,
            'value': 101,
        })

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Feedback.objects.exists())

    def test_rejects_invalid_feedback_type(self):
        response = self.client.post(reverse('feedback-list-create'), {
            'place_id': self.place.id,
            'feedback_type': 'unknown',
            'value': 50,
        })

        self.assertEqual(response.status_code, 400)

    def test_rejects_nonexistent_place(self):
        response = self.client.post(reverse('feedback-list-create'), {
            'place_id': 999999,
            'feedback_type': Feedback.FeedbackType.CROWD,
            'value': 50,
        })

        self.assertEqual(response.status_code, 400)

    def test_same_place_and_type_is_limited_to_once_a_day(self):
        payload = {
            'place_id': self.place.id,
            'feedback_type': Feedback.FeedbackType.CROWD,
            'value': 50,
        }
        self.assertEqual(self.client.post(reverse('feedback-list-create'), payload).status_code, 201)

        second_response = self.client.post(reverse('feedback-list-create'), payload)
        self.assertEqual(second_response.status_code, 429)
        self.assertEqual(Feedback.objects.count(), 1)

    def test_different_type_on_same_place_is_allowed(self):
        self.client.post(reverse('feedback-list-create'), {
            'place_id': self.place.id,
            'feedback_type': Feedback.FeedbackType.CROWD,
            'value': 50,
        })
        response = self.client.post(reverse('feedback-list-create'), {
            'place_id': self.place.id,
            'feedback_type': Feedback.FeedbackType.PLACE,
            'value': 80,
        })

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Feedback.objects.count(), 2)

    def test_allowed_again_after_cooldown(self):
        payload = {
            'place_id': self.place.id,
            'feedback_type': Feedback.FeedbackType.CROWD,
            'value': 50,
        }
        self.client.post(reverse('feedback-list-create'), payload)

        old_feedback = Feedback.objects.get()
        Feedback.objects.filter(id=old_feedback.id).update(
            created_at=timezone.now() - FEEDBACK_COOLDOWN - timedelta(minutes=1),
        )

        response = self.client.post(reverse('feedback-list-create'), payload)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Feedback.objects.count(), 2)

    def test_list_returns_only_own_feedback_newest_first(self):
        other_user = User.objects.create_user(
            email='other-feedback@example.com',
            password='correct-password',
            nickname='다른피드백유저',
        )
        Feedback.objects.create(
            user=other_user,
            place=self.place,
            feedback_type=Feedback.FeedbackType.CROWD,
            value=10,
        )
        older = Feedback.objects.create(
            user=self.user,
            place=self.place,
            feedback_type=Feedback.FeedbackType.PLACE,
            value=20,
        )
        newer = Feedback.objects.create(
            user=self.user,
            place=self.place,
            feedback_type=Feedback.FeedbackType.RECOMMENDATION,
            value=30,
        )

        response = self.client.get(reverse('feedback-list-create'))

        self.assertEqual(response.status_code, 200)
        feedbacks = response.json()['data']['feedbacks']
        self.assertEqual([item['id'] for item in feedbacks], [newer.id, older.id])
