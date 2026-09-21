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


CONSENT = {'age_over_14': True, 'agree_terms': True}


class SignupTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_signup_creates_user_and_returns_tokens(self):
        response = self.client.post(reverse('auth-signup'), {
            'email': 'test@example.com',
            'password': 'a-strong-password-123',
            'nickname': '테스트닉네임',
            **CONSENT,
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
            **CONSENT,
        })

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])
        self.assertEqual(
            response.json()['message']['nickname'],
            ['이미 사용 중인 닉네임이에요. 다른 닉네임을 써주세요.'],
        )

    def test_signup_duplicate_email_message_is_reader_facing(self):
        User.objects.create_user(
            email='taken@example.com', password='pw12345678', nickname='먼저가입'
        )

        response = self.client.post(reverse('auth-signup'), {
            'email': 'taken@example.com',
            'password': 'pw12345678',
            'nickname': '나중가입',
            **CONSENT,
        })

        self.assertEqual(response.status_code, 400)
        message = response.json()['message']['email']
        self.assertEqual(message, ['이미 가입된 이메일이에요. 로그인해 주세요.'])
        # Django's default phrasing must not reach the signup form.
        self.assertNotIn('user', message[0])

    def test_signup_records_age_and_terms_consent(self):
        from config import legal

        response = self.client.post(reverse('auth-signup'), {
            'email': 'consent@example.com',
            'password': 'a-strong-password-123',
            'nickname': '동의한사람',
            **CONSENT,
        }, format='json')

        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email='consent@example.com')
        self.assertIsNotNone(user.age_confirmed_at)
        self.assertIsNotNone(user.terms_agreed_at)
        self.assertEqual(user.terms_version, legal.TERMS_VERSION)

    def test_signup_requires_age_and_terms_consent(self):
        cases = [
            ({}, {'age_over_14': '만 14세 이상인지 확인해 주세요.',
                  'agree_terms': '이용약관에 동의해 주세요.'}),
            ({'age_over_14': False, 'agree_terms': True},
             {'age_over_14': '만 14세 이상만 가입할 수 있어요.'}),
            ({'age_over_14': True, 'agree_terms': False},
             {'agree_terms': '이용약관에 동의해야 가입할 수 있어요.'}),
        ]
        for consent, expected in cases:
            with self.subTest(consent=consent):
                response = self.client.post(reverse('auth-signup'), {
                    'email': 'nope@example.com',
                    'password': 'a-strong-password-123',
                    'nickname': '거절될사람',
                    **consent,
                }, format='json')

                self.assertEqual(response.status_code, 400)
                message = response.json()['message']
                for field, text in expected.items():
                    self.assertEqual(message[field], [text])
                self.assertFalse(User.objects.filter(email='nope@example.com').exists())


class PasswordChangeTests(TestCase):
    def test_legacy_refresh_without_password_fingerprint_requires_login(self):
        from rest_framework_simplejwt.tokens import RefreshToken as JWTRefresh
        from rest_framework_simplejwt.settings import api_settings
        from .utils import hash_token
        token = JWTRefresh.for_user(self.user)
        del token[api_settings.REVOKE_TOKEN_CLAIM]
        raw = str(token)
        RefreshToken.objects.create(user=self.user, token_hash=hash_token(raw),
            expires_at=timezone.now() + timedelta(days=1))
        self.client.force_authenticate(None)
        response = self.client.post(reverse('auth-refresh'), {'refresh_token': raw})
        self.assertEqual(response.status_code, 401)

    def test_password_change_revokes_real_access_and_refresh(self):
        from .views import issue_tokens
        tokens = issue_tokens(self.user)
        self.client.force_authenticate(None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access_token']}")
        response = self.client.post(reverse('auth-password'), {
            'current_password': 'old-password-123',
            'new_password': 'brand-new-password-456',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get('/api/me').status_code, 401)
        self.client.credentials()
        self.assertEqual(self.client.post(reverse('auth-refresh'), {
            'refresh_token': tokens['refresh_token'],
        }).status_code, 401)

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='pw@example.com', password='old-password-123', nickname='비번유저'
        )
        self.client.force_authenticate(self.user)

    def test_change_password_updates_credential_and_revokes_sessions(self):
        RefreshToken.objects.create(
            user=self.user,
            token_hash='hash',
            expires_at=timezone.now() + timedelta(days=1),
        )

        response = self.client.post(reverse('auth-password'), {
            'current_password': 'old-password-123',
            'new_password': 'brand-new-password-456',
        })

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('brand-new-password-456'))
        self.assertFalse(RefreshToken.objects.filter(user=self.user).exists())

    def test_change_password_rejects_wrong_current_password(self):
        response = self.client.post(reverse('auth-password'), {
            'current_password': 'not-my-password',
            'new_password': 'brand-new-password-456',
        })

        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('old-password-123'))

    def test_change_password_rejects_weak_new_password(self):
        response = self.client.post(reverse('auth-password'), {
            'current_password': 'old-password-123',
            'new_password': '12345678',
        })

        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('old-password-123'))

    def test_change_password_requires_authentication(self):
        self.client.force_authenticate(None)

        response = self.client.post(reverse('auth-password'), {
            'current_password': 'old-password-123',
            'new_password': 'brand-new-password-456',
        })

        self.assertEqual(response.status_code, 401)


class WithdrawTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='bye@example.com', password='pw12345678', nickname='탈퇴유저'
        )

    def test_withdraw_marks_account_and_blocks_login(self):
        self.client.force_authenticate(self.user)
        RefreshToken.objects.create(
            user=self.user,
            token_hash='hash',
            expires_at=timezone.now() + timedelta(days=1),
        )

        response = self.client.post(reverse('withdraw'), {'password': 'pw12345678'})

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.status, User.Status.WITHDRAWN)
        self.assertFalse(self.user.is_active)
        self.assertFalse(RefreshToken.objects.filter(user=self.user).exists())

        self.client.force_authenticate(None)
        login = self.client.post(reverse('auth-login'), {
            'email': 'bye@example.com',
            'password': 'pw12345678',
        })
        self.assertEqual(login.status_code, 403)
        self.assertEqual(login.json()['data']['code'], 'withdrawal_pending')

    def test_withdraw_requires_authentication(self):
        response = self.client.post(reverse('withdraw'), {'password': 'pw12345678'})

        self.assertEqual(response.status_code, 401)


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

        Feedback.objects.filter(id__in=[older.id, newer.id]).update(created_at=older.created_at)
        response = self.client.get(reverse('feedback-list-create'))
        feedbacks = response.json()['data']['feedbacks']
        self.assertEqual([item['id'] for item in feedbacks], [newer.id, older.id])
