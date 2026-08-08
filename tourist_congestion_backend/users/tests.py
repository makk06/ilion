from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from .models import RefreshToken, User


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
