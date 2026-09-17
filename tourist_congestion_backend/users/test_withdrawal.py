from datetime import date

from django.test import TestCase

from .models import AnonymousActor, User, WithdrawalReason, WithdrawnEmailHash


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
