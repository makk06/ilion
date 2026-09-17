import uuid
from datetime import date, timedelta
from io import StringIO

from django.core.management import call_command

from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from places.models import Place

from .models import (AnonymousActor, Companion, CompanionMember, Favorite, Feedback, Plan,
                     RecentPlace, RefreshToken, Review, ReviewLike, User, WithdrawalReason,
                     WithdrawnEmailHash)
from .utils import hash_email_for_withdrawal
from .withdrawal import purge_withdrawn_users


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


class AnonymousActorTests(TestCase):
    def test_actor_has_no_time_columns(self):
        # 스펙 5.2: actor에 시각 정보가 있으면 탈퇴 이메일 해시와 짝지어 재식별된다.
        names = {field.name for field in AnonymousActor._meta.get_fields()}
        self.assertEqual(names & {'created_at', 'updated_at', 'withdrawn_at'}, set())

    def test_actor_id_is_random_uuid(self):
        first = AnonymousActor.objects.create()
        second = AnonymousActor.objects.create()
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(len(str(first.id)), 36)


class WithdrawalStorageTests(TestCase):
    def test_email_hash_expires_on_a_date_not_a_timestamp(self):
        row = WithdrawnEmailHash.objects.create(email_hash='a' * 64, expires_at=date(2026, 10, 18))
        self.assertIsInstance(row.expires_at, date)
        self.assertEqual(
            WithdrawnEmailHash._meta.get_field('expires_at').get_internal_type(),
            'DateField',
        )

    def test_reason_is_not_linked_to_any_person(self):
        names = {field.name for field in WithdrawalReason._meta.get_fields()}
        self.assertEqual(names & {'user', 'actor', 'email', 'email_hash'}, set())


class UserWithdrawalFieldTests(TestCase):
    def test_new_user_has_no_purge_schedule(self):
        user = User.objects.create_user(email='a@example.com', password='pw12345678', nickname='가입자')
        self.assertIsNone(user.purge_at)
        self.assertIsNone(user.withdrawal_reason_code)


class UserXorActorConstraintTests(TestCase):
    def setUp(self):
        self.place = create_place()
        self.user = User.objects.create_user(
            email='keeper@example.com', password='pw12345678', nickname='보존자')
        self.actor = AnonymousActor.objects.create()

    def test_row_may_belong_to_a_user(self):
        favorite = Favorite.objects.create(user=self.user, place=self.place)
        self.assertIsNone(favorite.actor)

    def test_row_may_belong_to_an_actor(self):
        favorite = Favorite.objects.create(actor=self.actor, place=self.place)
        self.assertIsNone(favorite.user)

    def test_row_may_not_belong_to_both(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Favorite.objects.create(user=self.user, actor=self.actor, place=self.place)

    def test_row_may_not_be_orphaned(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Favorite.objects.create(place=self.place)

    def test_every_preserved_model_enforces_the_rule(self):
        for model in (Feedback, Review, ReviewLike, Favorite, RecentPlace):
            names = {constraint.name for constraint in model._meta.constraints}
            self.assertIn(
                f'{model.__name__.lower()}_user_xor_actor', names,
                f'{model.__name__}에 XOR 제약이 없습니다',
            )

    def test_actor_may_not_favorite_the_same_place_twice(self):
        Favorite.objects.create(actor=self.actor, place=self.place)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Favorite.objects.create(actor=self.actor, place=self.place)


class EmailHashTests(TestCase):
    @override_settings(WITHDRAWAL_HASH_KEY='k' * 50)
    def test_hash_is_case_and_space_insensitive(self):
        self.assertEqual(
            hash_email_for_withdrawal('  User@Example.COM '),
            hash_email_for_withdrawal('user@example.com'),
        )

    @override_settings(WITHDRAWAL_HASH_KEY='k' * 50)
    def test_hash_is_sixty_four_hex_characters(self):
        value = hash_email_for_withdrawal('user@example.com')
        self.assertEqual(len(value), 64)
        int(value, 16)

    def test_hash_depends_on_the_secret_key(self):
        # 키 없이 sha256만 쓰면 이메일 후보를 전수 대입해 복원할 수 있다.
        with override_settings(WITHDRAWAL_HASH_KEY='a' * 50):
            first = hash_email_for_withdrawal('user@example.com')
        with override_settings(WITHDRAWAL_HASH_KEY='b' * 50):
            second = hash_email_for_withdrawal('user@example.com')
        self.assertNotEqual(first, second)

    @override_settings(WITHDRAWAL_HASH_KEY='k' * 50)
    def test_hash_is_not_a_plain_sha256(self):
        import hashlib
        plain = hashlib.sha256(b'user@example.com').hexdigest()
        self.assertNotEqual(hash_email_for_withdrawal('user@example.com'), plain)


class PurgeTests(TestCase):
    def setUp(self):
        self.place = create_place()
        self.leaver = User.objects.create_user(
            email='leaver@example.com', password='pw12345678', nickname='떠나는사람')
        self.stayer = User.objects.create_user(
            email='stayer@example.com', password='pw12345678', nickname='남는사람')

    def _request_withdrawal(self, user, reason_code='etc'):
        user.status = User.Status.WITHDRAWN
        user.purge_at = timezone.now() - timedelta(seconds=1)
        user.withdrawal_reason_code = reason_code
        user.save(update_fields=['status', 'purge_at', 'withdrawal_reason_code', 'updated_at'])

    def test_user_row_is_actually_deleted(self):
        self._request_withdrawal(self.leaver)
        purge_withdrawn_users()
        self.assertFalse(User.objects.filter(email='leaver@example.com').exists())

    def test_review_survives_without_its_author(self):
        review = Review.objects.create(user=self.leaver, place=self.place, text='좋았습니다', rating=5)
        self._request_withdrawal(self.leaver)
        purge_withdrawn_users()

        review.refresh_from_db()
        self.assertIsNone(review.user_id)
        self.assertIsNotNone(review.actor_id)
        self.assertEqual(review.text, '좋았습니다')

    def test_feedback_keeps_its_value_but_loses_its_memo(self):
        Feedback.objects.create(user=self.leaver, place=self.place,
                                feedback_type=Feedback.FeedbackType.CROWD, value=70,
                                memo='제가 사는 동네라 잘 압니다')
        self._request_withdrawal(self.leaver)
        purge_withdrawn_users()

        feedback = Feedback.objects.get(place=self.place)
        self.assertEqual(feedback.value, 70)
        self.assertIsNone(feedback.memo)
        self.assertIsNone(feedback.user_id)

    def test_all_preserved_rows_share_one_actor(self):
        Review.objects.create(user=self.leaver, place=self.place, text='글', rating=4)
        Favorite.objects.create(user=self.leaver, place=self.place)
        RecentPlace.objects.create(user=self.leaver, place=self.place)
        self._request_withdrawal(self.leaver)
        purge_withdrawn_users()

        actors = {
            Review.objects.get().actor_id,
            Favorite.objects.get().actor_id,
            RecentPlace.objects.get().actor_id,
        }
        self.assertEqual(len(actors), 1)

    def test_companion_membership_is_deleted_and_counter_is_corrected(self):
        companion = Companion.objects.create(
            user=self.stayer, place=self.place, title='같이 가요', text='본문',
            capacity=4, member_count=2)
        CompanionMember.objects.create(user=self.leaver, companion=companion)
        self._request_withdrawal(self.leaver)
        purge_withdrawn_users()

        companion.refresh_from_db()
        self.assertEqual(companion.member_count, 1)
        self.assertEqual(CompanionMember.objects.count(), 0)

    def test_own_companion_is_removed(self):
        Companion.objects.create(user=self.leaver, place=self.place, title='내 모임',
                                 text='본문', capacity=4)
        self._request_withdrawal(self.leaver)
        purge_withdrawn_users()
        self.assertEqual(Companion.objects.count(), 0)

    def test_private_records_are_cascade_deleted(self):
        Plan.objects.create(user=self.leaver, title='일정', date=date(2026, 10, 1))
        RefreshToken.objects.create(user=self.leaver, token_hash='t' * 64,
                                    expires_at=timezone.now() + timedelta(days=1))
        self._request_withdrawal(self.leaver)
        purge_withdrawn_users()

        self.assertEqual(Plan.objects.count(), 0)
        self.assertEqual(RefreshToken.objects.count(), 0)

    def test_email_hash_is_recorded_with_a_date_only_expiry(self):
        self._request_withdrawal(self.leaver)
        now = timezone.now()
        purge_withdrawn_users(now=now)

        row = WithdrawnEmailHash.objects.get()
        self.assertEqual(row.email_hash, hash_email_for_withdrawal('leaver@example.com'))
        self.assertEqual(row.expires_at, (now + timedelta(days=30)).date())

    def test_reason_is_recorded_without_any_link(self):
        self._request_withdrawal(self.leaver, reason_code='no_longer_needed')
        purge_withdrawn_users()

        reason = WithdrawalReason.objects.get()
        self.assertEqual(reason.reason_code, 'no_longer_needed')

    def test_user_not_yet_due_is_untouched(self):
        self.leaver.status = User.Status.WITHDRAWN
        self.leaver.purge_at = timezone.now() + timedelta(days=7)
        self.leaver.save(update_fields=['status', 'purge_at', 'updated_at'])

        self.assertEqual(purge_withdrawn_users(), 0)
        self.assertTrue(User.objects.filter(email='leaver@example.com').exists())

    def test_running_twice_changes_nothing(self):
        Review.objects.create(user=self.leaver, place=self.place, text='글', rating=4)
        self._request_withdrawal(self.leaver)

        self.assertEqual(purge_withdrawn_users(), 1)
        snapshot = (User.objects.count(), Review.objects.count(),
                    WithdrawnEmailHash.objects.count(), WithdrawalReason.objects.count())
        self.assertEqual(purge_withdrawn_users(), 0)
        self.assertEqual(
            (User.objects.count(), Review.objects.count(),
             WithdrawnEmailHash.objects.count(), WithdrawalReason.objects.count()),
            snapshot,
        )

    def test_expired_email_hashes_are_swept(self):
        WithdrawnEmailHash.objects.create(email_hash='b' * 64,
                                          expires_at=timezone.now().date() - timedelta(days=1))
        purge_withdrawn_users()
        self.assertEqual(WithdrawnEmailHash.objects.count(), 0)

    def test_actor_cannot_be_traced_back_to_the_user(self):
        # 스펙 결정 4: 복원 경로가 구조적으로 존재하지 않아야 한다.
        Review.objects.create(user=self.leaver, place=self.place, text='글', rating=4)
        self._request_withdrawal(self.leaver)
        leaver_pk = self.leaver.pk
        purge_withdrawn_users()

        actor = AnonymousActor.objects.get()

        # 1. actor 자체에 식별 컬럼이 없다
        column_names = {field.name for field in AnonymousActor._meta.get_fields()}
        self.assertEqual(column_names & {'user', 'user_id', 'email', 'email_hash'}, set())

        # 2. id가 user_id에서 계산되지 않는다 — 난수(v4)이지 결정적 파생(v5)이 아니다
        self.assertEqual(uuid.UUID(str(actor.id)).version, 4)
        self.assertNotEqual(str(actor.id), str(uuid.uuid5(uuid.NAMESPACE_OID, str(leaver_pk))))

        # 3. user와 actor를 동시에 들고 있는 행이 하나도 없다
        for model in (Feedback, Review, ReviewLike, Favorite, RecentPlace):
            self.assertEqual(
                model.objects.filter(actor__isnull=False, user__isnull=False).count(), 0,
                f'{model.__name__}에 매핑을 남기는 행이 있습니다',
            )

        # 4. 원래 계정 행이 사라져 이어붙일 대상 자체가 없다
        self.assertFalse(User.objects.filter(pk=leaver_pk).exists())


class WithdrawRequestTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='leaver@example.com', password='pw12345678', nickname='떠나는사람')
        self.client.force_authenticate(user=self.user)

    def test_withdraw_schedules_purge_seven_days_out(self):
        response = self.client.post(reverse('withdraw'), {'password': 'pw12345678'})

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.status, User.Status.WITHDRAWN)
        delta = self.user.purge_at - timezone.now()
        self.assertGreater(delta, timedelta(days=6, hours=23))
        self.assertLess(delta, timedelta(days=7))

    def test_withdraw_requires_the_correct_password(self):
        response = self.client.post(reverse('withdraw'), {'password': 'wrong-password'})

        self.assertEqual(response.status_code, 401)
        self.user.refresh_from_db()
        self.assertEqual(self.user.status, User.Status.ACTIVE)

    def test_withdraw_ends_every_session(self):
        RefreshToken.objects.create(user=self.user, token_hash='t' * 64,
                                    expires_at=timezone.now() + timedelta(days=1))
        self.client.post(reverse('withdraw'), {'password': 'pw12345678'})
        self.assertEqual(RefreshToken.objects.filter(user=self.user).count(), 0)

    def test_withdraw_stores_the_reason_on_the_user_until_purge(self):
        self.client.post(reverse('withdraw'),
                         {'password': 'pw12345678', 'reason_code': 'no_longer_needed'})

        self.user.refresh_from_db()
        self.assertEqual(self.user.withdrawal_reason_code, 'no_longer_needed')
        # 철회한 사람의 사유가 집계에 섞이면 안 되므로 아직 만들지 않는다.
        self.assertEqual(WithdrawalReason.objects.count(), 0)

    def test_withdraw_rejects_an_unknown_reason_code(self):
        response = self.client.post(reverse('withdraw'),
                                    {'password': 'pw12345678', 'reason_code': '제가 이사를 가서요'})
        self.assertEqual(response.status_code, 400)

    def test_withdraw_requires_authentication(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(reverse('withdraw'), {'password': 'pw12345678'})
        self.assertIn(response.status_code, (401, 403))


class WithdrawalPendingLoginTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='leaver@example.com', password='pw12345678', nickname='떠나는사람')
        self.user.status = User.Status.WITHDRAWN
        self.user.purge_at = timezone.now() + timedelta(days=7)
        self.user.save(update_fields=['status', 'purge_at', 'updated_at'])

    def test_login_reports_withdrawal_pending(self):
        response = self.client.post(reverse('auth-login'),
                                    {'email': 'leaver@example.com', 'password': 'pw12345678'})

        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertFalse(body['success'])
        self.assertEqual(body['data']['code'], 'withdrawal_pending')
        self.assertIn('purge_at', body['data'])

    def test_wrong_password_does_not_reveal_withdrawal(self):
        response = self.client.post(reverse('auth-login'),
                                    {'email': 'leaver@example.com', 'password': 'wrong'})

        self.assertEqual(response.status_code, 401)
        self.assertNotIn('withdrawal_pending', response.content.decode())

    def test_unknown_email_stays_a_plain_401(self):
        response = self.client.post(reverse('auth-login'),
                                    {'email': 'nobody@example.com', 'password': 'pw12345678'})
        self.assertEqual(response.status_code, 401)


class WithdrawCancelTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.place = create_place()
        self.user = User.objects.create_user(
            email='leaver@example.com', password='pw12345678', nickname='떠나는사람')
        Review.objects.create(user=self.user, place=self.place, text='글', rating=5)
        self.user.status = User.Status.WITHDRAWN
        self.user.purge_at = timezone.now() + timedelta(days=7)
        self.user.withdrawal_reason_code = 'etc'
        self.user.save(update_fields=['status', 'purge_at', 'withdrawal_reason_code', 'updated_at'])

    def test_cancel_restores_the_account_and_returns_tokens(self):
        response = self.client.post(reverse('withdraw-cancel'),
                                    {'email': 'leaver@example.com', 'password': 'pw12345678'})

        self.assertEqual(response.status_code, 200)
        self.assertIn('access_token', response.json()['data'])
        self.user.refresh_from_db()
        self.assertEqual(self.user.status, User.Status.ACTIVE)
        self.assertIsNone(self.user.purge_at)
        self.assertIsNone(self.user.withdrawal_reason_code)

    def test_cancelled_withdrawal_never_reaches_the_reason_statistics(self):
        # 스펙 9 검증 12: 철회한 사람의 사유가 집계를 부풀리면 안 된다.
        self.client.post(reverse('withdraw-cancel'),
                         {'email': 'leaver@example.com', 'password': 'pw12345678'})
        purge_withdrawn_users()
        self.assertEqual(WithdrawalReason.objects.count(), 0)
        self.assertTrue(User.objects.filter(email='leaver@example.com').exists())

    def test_cancel_leaves_every_row_intact(self):
        self.client.post(reverse('withdraw-cancel'),
                         {'email': 'leaver@example.com', 'password': 'pw12345678'})

        review = Review.objects.get()
        self.assertEqual(review.user_id, self.user.pk)
        self.assertIsNone(review.actor_id)

    def test_cancel_is_refused_once_the_purge_is_due(self):
        self.user.purge_at = timezone.now() - timedelta(seconds=1)
        self.user.save(update_fields=['purge_at', 'updated_at'])

        response = self.client.post(reverse('withdraw-cancel'),
                                    {'email': 'leaver@example.com', 'password': 'pw12345678'})

        self.assertEqual(response.status_code, 409)
        self.user.refresh_from_db()
        self.assertEqual(self.user.status, User.Status.WITHDRAWN)

    def test_cancel_requires_the_correct_password(self):
        response = self.client.post(reverse('withdraw-cancel'),
                                    {'email': 'leaver@example.com', 'password': 'wrong'})
        self.assertEqual(response.status_code, 401)

    def test_cancel_does_nothing_for_an_active_account(self):
        self.user.status = User.Status.ACTIVE
        self.user.purge_at = None
        self.user.save(update_fields=['status', 'purge_at', 'updated_at'])

        response = self.client.post(reverse('withdraw-cancel'),
                                    {'email': 'leaver@example.com', 'password': 'pw12345678'})
        self.assertEqual(response.status_code, 401)


class RejoinBlockTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def _block(self, email, days=30):
        WithdrawnEmailHash.objects.create(
            email_hash=hash_email_for_withdrawal(email),
            expires_at=timezone.now().date() + timedelta(days=days),
        )

    def _signup(self, email):
        return self.client.post(reverse('auth-signup'), {
            'email': email, 'password': 'pw12345678', 'nickname': '재가입자',
        })

    def test_recently_withdrawn_email_cannot_sign_up(self):
        self._block('leaver@example.com')
        self.assertEqual(self._signup('leaver@example.com').status_code, 400)
        self.assertFalse(User.objects.filter(email='leaver@example.com').exists())

    def test_block_ignores_case(self):
        self._block('leaver@example.com')
        self.assertEqual(self._signup('Leaver@Example.com').status_code, 400)

    def test_expired_block_allows_sign_up(self):
        WithdrawnEmailHash.objects.create(
            email_hash=hash_email_for_withdrawal('leaver@example.com'),
            expires_at=timezone.now().date() - timedelta(days=1),
        )
        self.assertEqual(self._signup('leaver@example.com').status_code, 201)

    def test_rejection_does_not_reveal_that_the_account_was_withdrawn(self):
        self._block('leaver@example.com')
        body = self._signup('leaver@example.com').content.decode()
        for leak in ('탈퇴', '30일', 'withdraw'):
            self.assertNotIn(leak, body)

    def test_unrelated_email_is_unaffected(self):
        self._block('leaver@example.com')
        self.assertEqual(self._signup('newcomer@example.com').status_code, 201)


ANONYMOUS_AUTHOR_NAME = '탈퇴한 사용자'


class AnonymisedReviewResponseTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.place = create_place()
        self.leaver = User.objects.create_user(
            email='leaver@example.com', password='pw12345678', nickname='떠나는사람')
        self.review = Review.objects.create(user=self.leaver, place=self.place,
                                            text='좋았습니다', rating=5)
        self.leaver.status = User.Status.WITHDRAWN
        self.leaver.purge_at = timezone.now() - timedelta(seconds=1)
        self.leaver.save(update_fields=['status', 'purge_at', 'updated_at'])
        purge_withdrawn_users()

    def _fetch(self):
        response = self.client.get(reverse('reviews'), {'place_id': self.place.pk})
        self.assertEqual(response.status_code, 200)
        return response.json()['data']['items'][0]

    def test_author_is_shown_as_withdrawn(self):
        item = self._fetch()
        self.assertIsNone(item['author_id'])
        self.assertEqual(item['author_nickname'], ANONYMOUS_AUTHOR_NAME)

    def test_anonymous_visitor_does_not_own_the_review(self):
        # request.user.id도 None, item.user_id도 None이라 == 비교가 참이 된다.
        # 이 버그가 살아 있으면 비로그인 방문자에게 수정·삭제 UI가 노출된다.
        item = self._fetch()
        self.assertFalse(item['is_mine'])

    def test_signed_in_visitor_does_not_own_the_review(self):
        other = User.objects.create_user(
            email='other@example.com', password='pw12345678', nickname='다른사람')
        self.client.force_authenticate(user=other)
        self.assertFalse(self._fetch()['is_mine'])


class NotificationTests(TestCase):
    def test_anonymised_likes_are_not_listed(self):
        client = APIClient()
        place = create_place()
        author = User.objects.create_user(
            email='author@example.com', password='pw12345678', nickname='작성자')
        liker = User.objects.create_user(
            email='liker@example.com', password='pw12345678', nickname='좋아요한사람')
        review = Review.objects.create(user=author, place=place, text='글', rating=4)
        ReviewLike.objects.create(user=liker, review=review)

        liker.status = User.Status.WITHDRAWN
        liker.purge_at = timezone.now() - timedelta(seconds=1)
        liker.save(update_fields=['status', 'purge_at', 'updated_at'])
        purge_withdrawn_users()

        client.force_authenticate(user=author)
        response = client.get(reverse('notifications'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['items'], [])


class PurgeCommandTests(TestCase):
    def test_command_purges_due_accounts_and_reports_the_count(self):
        user = User.objects.create_user(
            email='leaver@example.com', password='pw12345678', nickname='떠나는사람')
        user.status = User.Status.WITHDRAWN
        user.purge_at = timezone.now() - timedelta(seconds=1)
        user.save(update_fields=['status', 'purge_at', 'updated_at'])

        out = StringIO()
        call_command('purge_withdrawn_users', stdout=out)

        self.assertFalse(User.objects.filter(email='leaver@example.com').exists())
        self.assertIn('1', out.getvalue())

    def test_command_is_safe_when_nothing_is_due(self):
        out = StringIO()
        call_command('purge_withdrawn_users', stdout=out)
        self.assertIn('0', out.getvalue())
