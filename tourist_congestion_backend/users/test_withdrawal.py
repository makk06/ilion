from datetime import date

from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from places.models import Place

from .utils import hash_email_for_withdrawal
from .models import (AnonymousActor, Favorite, Feedback, RecentPlace, Review, ReviewLike,
                     User, WithdrawalReason, WithdrawnEmailHash)


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
