from types import SimpleNamespace
from datetime import timedelta
from django.test import SimpleTestCase
from django.utils import timezone
from shapely.geometry import Polygon
from places.services.place_resolver import polygon_diagnostics, select_mapping


class MappingValidationTests(SimpleTestCase):
    def test_diagnostic_reasons(self):
        polygon = Polygon([(126,37),(127,37),(127,38),(126,38)],
                          [[(126.4,37.4),(126.6,37.4),(126.6,37.6),(126.4,37.6)]])
        areas = [('a', polygon)]
        for lat,lon,reason in [(None,None,'NO_COORDINATE'),(float('nan'),127,'NO_COORDINATE'),
                               (35,125,'OUTSIDE'),(37.5,126.5,'HOLE'),(37,126.5,'BOUNDARY')]:
            self.assertEqual(polygon_diagnostics(lat,lon,areas)['reason'],reason)
        self.assertEqual(polygon_diagnostics(37.2,126.2,areas)['area'],'a')
        self.assertEqual(polygon_diagnostics(37.2,126.2,areas+[('b',polygon)])['reason'],'OVERLAP')

    def test_approval_conflicts_and_expiry_are_order_independent(self):
        now=timezone.now()
        def mapping(**kw):
            return SimpleNamespace(**dict(verified=True,valid_from=None,valid_until=None,
                                          match_method='manual',is_primary=False,**kw))
        a,b=mapping(),mapping()
        for rows in ([a,b],[b,a]):
            self.assertEqual(select_mapping(rows,now),(None,'APPROVAL_CONFLICT'))
        b.is_primary=True
        self.assertIs(select_mapping([a,b],now)[0],b)
        b.valid_until=now-timedelta(seconds=1)
        self.assertIs(select_mapping([a,b],now)[0],a)
        a.verified=False
        self.assertEqual(select_mapping([a,b],now),(None,None))

    def test_source_precedes_automatic(self):
        now=timezone.now()
        a=SimpleNamespace(verified=True,valid_from=None,valid_until=None,match_method='source',is_primary=False)
        b=SimpleNamespace(verified=True,valid_from=None,valid_until=None,match_method='coordinate',is_primary=True)
        self.assertIs(select_mapping([b,a],now)[0],a)


from io import StringIO
from django.test import TestCase
from django.core.management import call_command, CommandError
from places.models import Place, CrowdArea, PlaceCrowdArea, ExternalSource


class MappingApprovalTests(TestCase):
    def setUp(self):
        self.place = Place.objects.create(name='fixture', category='tour', region_code='11',
                                         address='fixture', latitude=37.5, longitude=127)
        self.a = CrowdArea.objects.create(source=ExternalSource.SEOUL_REALTIME, external_id='A', name='A',
                                          last_synced_at=timezone.now())
        self.b = CrowdArea.objects.create(source=ExternalSource.SEOUL_REALTIME, external_id='B', name='B',
                                          last_synced_at=timezone.now())

    def approve(self, area, **extra):
        call_command('map_place_crowd_area', str(self.place.pk), area.external_id,
                     reviewer='tester', evidence='https://example.org/source; same space review',
                     valid_until='2099-01-01T00:00:00+09:00', stdout=StringIO(), **extra)

    def test_new_mapping_unverified_and_explicit_approval_records_provenance(self):
        row = PlaceCrowdArea.objects.create(place=self.place, crowd_area=self.a)
        self.assertFalse(row.verified)
        self.assertEqual(select_mapping([row], timezone.now()), (None, None))
        self.approve(self.a)
        row.refresh_from_db()
        self.assertTrue(row.verified)
        self.assertEqual(row.evidence['reviewer'], 'tester')
        self.assertEqual(row.evidence['place_id'], self.place.pk)
        self.assertEqual(row.evidence['area_external_id'], 'A')
        self.assertIsNotNone(row.valid_until)

    def test_primary_requires_explicit_flag_and_resolves_conflict(self):
        self.approve(self.a)
        self.approve(self.b)
        rows = self.place.crowd_area_mappings.all()
        self.assertEqual(select_mapping(rows,timezone.now())[1],'APPROVAL_CONFLICT')
        self.approve(self.a, primary=True)
        self.assertEqual(select_mapping(self.place.crowd_area_mappings.all(),timezone.now())[0].crowd_area_id,self.a.pk)
        self.approve(self.b)
        self.assertEqual(self.place.crowd_area_mappings.get(is_primary=True).crowd_area_id,self.a.pk)
        self.approve(self.b, primary=True)
        self.assertEqual(self.place.crowd_area_mappings.get(is_primary=True).crowd_area_id,self.b.pk)

    def test_invalid_expiry_does_not_approve(self):
        with self.assertRaises(CommandError):
            call_command('map_place_crowd_area', str(self.place.pk), self.a.external_id,
                         reviewer='tester', evidence='source', valid_until='2000-01-01T00:00:00+09:00')
        self.assertFalse(self.place.crowd_area_mappings.exists())
