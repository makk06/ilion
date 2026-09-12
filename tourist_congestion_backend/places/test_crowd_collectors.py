import os
from datetime import timedelta
from unittest.mock import Mock, patch

import requests
from django.test import TestCase, SimpleTestCase
from shapely.geometry import Polygon

from places.integrations.crowd_http import BudgetSession, xml_root
from places.integrations.exceptions import ExternalAPIError
from places.integrations.seoul_citydata import normalize_citydata
from places.integrations.weather import latest_issue, parse_weather, weather_grid
from places.models import CollectorState, CrowdArea, CrowdData, Place, PlaceCrowdArea, TransitObservation
from places.services.crowd_collector import BudgetExhausted, acquire_lease, charge, release_lease, seoul_interval, _execute
from places.services.input_sync import save_citydata
from places.services.place_resolver import import_geometry, polygon_match, resolve_places
from places.test_crowd_estimator import NOW


XML = b'''<CITYDATA><AREA_CD>POI001</AREA_CD><AREA_NM>test</AREA_NM>
<LIVE_PPLTN_STTS><PPLTN_TIME>2026-09-12 15:00</PPLTN_TIME><AREA_CONGEST_LVL>normal</AREA_CONGEST_LVL>
<AREA_PPLTN_MIN>100</AREA_PPLTN_MIN><AREA_PPLTN_MAX>200</AREA_PPLTN_MAX></LIVE_PPLTN_STTS>
<LIVE_SUB_PPLTN><SUB_STN_TIME>202609</SUB_STN_TIME><SUB_30WTHN_GTOFF_PPLTN_MIN>20</SUB_30WTHN_GTOFF_PPLTN_MIN>
<SUB_30WTHN_GTOFF_PPLTN_MAX>40</SUB_30WTHN_GTOFF_PPLTN_MAX></LIVE_SUB_PPLTN></CITYDATA>'''


class AdapterTests(SimpleTestCase):
    @patch('places.management.commands.verify_crowd_providers.BudgetSession')
    @patch('places.management.commands.verify_crowd_providers.TourAPIClient')
    def test_provider_smoke_skips_hidden_poi_for_detail(self, client, session):
        from io import StringIO
        from django.core.management import call_command
        hidden = Mock(external_id='hidden', raw_data={'showflag':'0','contenttypeid':'12'})
        public = Mock(external_id='public', raw_data={'showflag':'1','contenttypeid':'12'})
        client.return_value.fetch_places_page.return_value.records = [hidden, public]
        with patch.dict(os.environ, {'TOUR_API_SERVICE_KEY':'test', 'TOUR_API_DAILY_LIMIT':'1000'}):
            output = StringIO()
            call_command('verify_crowd_providers', provider='tour_api', stdout=output)
        client.return_value.fetch_place_detail.assert_called_once_with('public','12')
        self.assertIn('passed', output.getvalue())

    def test_xml_rejects_entities_and_invalid_document(self):
        for value in (b'<bad',b'<!DOCTYPE x [<!ENTITY a "xx">]><x/>'):
            with self.assertRaises(ExternalAPIError): xml_root(value)

    def test_transit_reference_month_is_not_observation_time(self):
        _,transit=normalize_citydata(xml_root(XML),'POI001',NOW)
        self.assertEqual(transit[0]['timestamp_quality'],'collection_only')
        self.assertEqual(transit[0]['observed_at'],NOW)
        with self.assertRaises(ExternalAPIError): normalize_citydata(xml_root(XML),'POI002',NOW)

    def test_weather_grid_and_publication_midnight(self):
        self.assertEqual(weather_grid(37.5665,126.978),(60,127))
        at=NOW.replace(hour=0,minute=5)
        self.assertEqual(latest_issue('getUltraSrtNcst',at).date(),(at-timedelta(days=1)).date())
        self.assertEqual(latest_issue('getUltraSrtFcst',at).hour,23)
        self.assertEqual(latest_issue('getUltraSrtFcst',at.replace(minute=47)).hour,0)
        self.assertEqual(latest_issue('getVilageFcst',at).hour,23)
        items=[{'category':'T1H','obsrValue':'NaN'},{'category':'PTY','obsrValue':'1'}]
        self.assertEqual(parse_weather(items,'getUltraSrtNcst',NOW)[NOW],{'precipitation_type':1})

    @patch('places.integrations.crowd_http.time.sleep')
    @patch('requests.Session.request')
    def test_retries_are_charged_and_auth_is_not_retried(self,request,sleep):
        def response(code):
            r=Mock(status_code=code,headers={}); r.iter_content.return_value=[b'{}']; return r
        request.side_effect=[response(429),response(503),response(200)]
        charged=Mock(); session=BudgetSession(charged)
        self.assertEqual(session.get('https://example.test').status_code,200)
        self.assertEqual([c.kwargs['retry'] for c in charged.call_args_list],[False,True,True])
        request.reset_mock(); request.side_effect=[response(401)]
        self.assertEqual(session.get('https://example.test').status_code,401)
        self.assertEqual(request.call_count,1)

    def test_geometry_holes_boundaries_overlaps_and_no_nearest(self):
        shell=[(126,37),(127,37),(127,38),(126,38)]
        hole=[(126.4,37.4),(126.6,37.4),(126.6,37.6),(126.4,37.6)]
        polygon=Polygon(shell,[hole]); areas=[('a',polygon)]
        self.assertEqual(polygon_match(37.2,126.2,areas),'a')
        for lat,lon in ((37,126.2),(37.0001,126.2),(37.5,126.5),(36.99,126.2)):
            self.assertIsNone(polygon_match(lat,lon,areas))
        self.assertIsNone(polygon_match(37.2,126.2,areas+[('b',polygon)]))


class CollectorStorageTests(TestCase):
    @patch('places.services.crowd_collector.TourAPIClient')
    def test_event_pagination_resumes_without_marking_partial_as_complete(self,client):
        state=CollectorState.objects.create(provider='tour_api',key='events')
        items=[{'contentid':str(i),'title':'event','mapx':'127','mapy':'37',
                'eventstartdate':'20260101','eventenddate':'20261231'} for i in range(100)]
        client.return_value.fetch_events_page.return_value=(items,101)
        self.assertFalse(_execute('tour_api','events',None,Mock(),state,NOW))
        self.assertEqual(state.cursor['page'],2); self.assertIsNone(state.last_success_at)
        client.return_value.fetch_events_page.return_value=([],101)
        with self.assertRaises(ExternalAPIError): _execute('tour_api','events',None,Mock(),state,NOW)
        self.assertEqual(state.cursor['page'],2)
        client.return_value.fetch_events_page.return_value=([items[0]|{'contentid':'100'}],101)
        self.assertTrue(_execute('tour_api','events',None,Mock(),state,NOW))
        self.assertEqual(state.cursor['coverage'],1)

    def test_budget_counts_attempts_reserves_retries_and_resets_at_kst_midnight(self):
        with patch.dict(os.environ,{'SEOUL_DAILY_LIMIT':'10'}):
            for _ in range(8): charge('seoul',now=NOW)
            with self.assertRaises(BudgetExhausted): charge('seoul',now=NOW)
            for _ in range(2): charge('seoul',retry=True,now=NOW)
            with self.assertRaises(BudgetExhausted): charge('seoul',retry=True,now=NOW)
            charge('seoul',now=NOW+timedelta(days=1))
            self.assertEqual(CollectorState.objects.get(key='_budget').calls,1)
        self.assertEqual(seoul_interval(50000),5)
        self.assertGreater(seoul_interval(10000),5)

    def test_lease_only_owner_releases_and_expiry_recovers(self):
        owner=acquire_lease(NOW)
        self.assertIsNotNone(owner); self.assertIsNone(acquire_lease(NOW))
        release_lease('wrong'); self.assertIsNone(acquire_lease(NOW))
        self.assertIsNotNone(acquire_lease(NOW+timedelta(minutes=4)))

    def test_duplicate_collection_only_transit_does_not_refresh_age(self):
        area=CrowdArea.objects.create(source='seoul_realtime',external_id='POI001',name='test',last_synced_at=NOW)
        _,transit=normalize_citydata(xml_root(XML),'POI001',NOW)
        save_citydata(area,None,transit,NOW)
        _,again=normalize_citydata(xml_root(XML),'POI001',NOW+timedelta(minutes=5))
        save_citydata(area,None,again,NOW+timedelta(minutes=5))
        self.assertEqual(TransitObservation.objects.count(),1)
        self.assertEqual(TransitObservation.objects.get().fetched_at,NOW)

    def test_official_geometry_is_idempotent_and_preserves_manual_mapping(self):
        self.assertEqual(import_geometry(),121); import_geometry()
        self.assertEqual(CrowdArea.objects.count(),121)
        place=Place.objects.create(name='manual',latitude=35,longitude=129,category='관광지',region_code='26',address='Busan')
        area=CrowdArea.objects.first()
        mapping=PlaceCrowdArea.objects.create(place=place,crowd_area=area,match_method='manual')
        resolve_places([place]); mapping.refresh_from_db()
        self.assertTrue(mapping.is_primary); self.assertTrue(mapping.verified)
