from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from places.models import Place


class PlaceModelTests(TestCase):
    def setUp(self):
        self.place_data = {
            'name': '서울숲',
            'category': '자연',
            'region_code': '11200',
            'address': '서울특별시 성동구 뚝섬로 273',
            'latitude': Decimal('37.544387'),
            'longitude': Decimal('127.037442'),
            'indoor_outdoor': Place.IndoorOutdoor.OUTDOOR,
        }

    def test_create_place_with_required_fields(self):
        place = Place.objects.create(**self.place_data)

        self.assertIsNotNone(place.id)
        self.assertEqual(str(place), '서울숲')
        self.assertIsNone(place.subcategory)
        self.assertIsNone(place.open_status)
        self.assertIsNone(place.avg_rating)
        self.assertIsNotNone(place.created_at)
        self.assertIsNotNone(place.updated_at)

    def test_reject_invalid_choice_and_numeric_ranges(self):
        place = Place(
            **{
                **self.place_data,
                'indoor_outdoor': 'both',
                'latitude': Decimal('91'),
                'longitude': Decimal('181'),
                'avg_rating': Decimal('5.01'),
            }
        )

        with self.assertRaises(ValidationError) as context:
            place.full_clean()

        self.assertEqual(
            set(context.exception.message_dict),
            {'indoor_outdoor', 'latitude', 'longitude', 'avg_rating'},
        )
