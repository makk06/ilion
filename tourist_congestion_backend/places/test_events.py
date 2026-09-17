from datetime import datetime, timedelta, timezone as tz
from unittest.mock import Mock, patch
from django.test import TestCase, SimpleTestCase
from django.utils import timezone
from places.models import TourEvent, EventTargetLink, MeanEvidence, CollectorState
from places.hourly_models import HourlyStudy, HourlyTarget
from places.services.event_context import context, event_rows
from places.services.event_forecast import predict_events, effect, history
from places.services.hourly_forecast import samples, baseline
from places.services.input_sync import save_event
from places.services.event_collection import collect_page
from places.services.event_validation import promotion_allowed
from places.services.event_experiment import issue, reproduce, report
from places.admin import EventForm

KST=tz(timedelta(hours=9))
NOW=datetime(2026,3,1,9,tzinfo=KST)


class EventMathTests(SimpleTestCase):
    def data(self):
        data={'provider':'seoul','external_id':'a','metric':'population_count','calendar':{},'observations':[]}
        for n in range(80*24+1):
            at=NOW-timedelta(hours=80*24-n)
            data['observations'].append({'observed_at':at.isoformat(),'received_at':at.isoformat(),'value':100.0})
        events=[]
        for days in (30,20,10,0):
            start=(NOW-timedelta(days=days)).replace(hour=10)
            e={'provider':'seoul','external_id':'a','metric':'population_count','event_id':str(days),
                'family':'festival','edition':str(days),'verified':True,'status':'scheduled',
                'starts_at':start.isoformat(),'ends_at':(start+timedelta(hours=3)).isoformat(),
                'start_date':start.date().isoformat(),'end_date':start.date().isoformat(),
                'received_at':(start-timedelta(days=1)).isoformat()}
            events.append(e)
            if days:
                points=samples(data,NOW)
                for h in range(3):
                    at=start+timedelta(hours=h)
                    b=baseline(history(points,at),at,at,{},None)['base']
                    next(r for r in data['observations'] if r['observed_at']==at.isoformat())['value']=b+30
        return data,events

    def test_shrinkage_equal_editions(self):
        data,events=self.data()
        rows=predict_events(data,NOW,events)
        self.assertAlmostEqual(rows[0]['event_adjustment'],30*3/11)
        self.assertAlmostEqual(rows[0]['value'],rows[0]['unadjusted_value']+30*3/11)
        self.assertEqual(len(rows[0]['event_editions']),3)

    def test_late_announcements_do_not_change_prediction(self):
        data,events=self.data(); before=predict_events(data,NOW,events)
        late={**events[-1],'received_at':(NOW+timedelta(minutes=1)).isoformat()}
        self.assertEqual(before,predict_events(data,NOW,events+[late]))

    def test_insufficient_overlap_and_date_only(self):
        data,events=self.data()
        self.assertEqual(predict_events(data,NOW,events[1:])[0]['event_adjustment'],0)
        self.assertEqual(predict_events(data,NOW,events+[events[-1]])[0]['event_reason'],'overlapping_events')
        events[-1]['starts_at']=events[-1]['ends_at']=None
        self.assertEqual(predict_events(data,NOW,events)[0]['event_reason'],'event_time_unknown')

    def test_identity_and_missing_current(self):
        data,events=self.data(); events[-1]['metric']='population_density'
        with self.assertRaises(ValueError): predict_events(data,NOW,events)
        events[-1]['metric']='population_count'; data['observations'].pop()
        self.assertEqual(predict_events(data,NOW,events)[0]['correction'],0)

    def test_current_effect_not_counted_twice(self):
        data,events=self.data(); at=NOW+timedelta(hours=1)
        points=samples(data,NOW)
        b=baseline(history(points,at),at,at,{},None)['base']
        e=30*3/11
        data['observations'].append({'observed_at':at.isoformat(),'received_at':at.isoformat(),'value':b+e})
        row=predict_events(data,at,events)[0]
        self.assertAlmostEqual(row['delta'],0)
        self.assertAlmostEqual(row['correction'],0)

    def test_advice_boundaries_and_empty_unknown(self):
        data,events=self.data(); e={**events[-1],'name':'축제','source':'manual'}
        at=NOW.replace(hour=10)
        self.assertEqual(len(context([e],at,NOW,NOW)['events']),1)
        self.assertEqual(context([e],at+timedelta(hours=3),NOW,NOW)['events'],[])
        self.assertEqual(context([],NOW,NOW,NOW-timedelta(hours=3))['collection_status'],'delayed')
        self.assertEqual(context([],NOW,NOW,NOW)['coverage'],'registered_events_only')


class EventStorageTests(TestCase):
    def setUp(self):
        self.study=HourlyStudy.objects.create(provider='seoul',started_at=NOW)
        self.target=HourlyTarget.objects.create(study=self.study,external_id='a',name='a',metric='population_count',scope='area_population',active=True,selected=True)
        self.item={'contentid':'123','title':'축제','mapx':'127','mapy':'37','eventstartdate':'20260301','eventenddate':'20260302'}

    def test_identical_payload_deduplicates_and_revision_preserved(self):
        save_event(self.item,NOW)
        save_event(self.item,NOW+timedelta(hours=1))
        self.assertEqual(MeanEvidence.objects.filter(kind='event').count(),1)
        save_event({**self.item,'title':'변경'},NOW+timedelta(hours=2))
        self.assertEqual(MeanEvidence.objects.filter(kind='event').count(),2)

    def test_hidden_is_not_cancelled(self):
        save_event({**self.item,'showflag':'0'},NOW)
        self.assertEqual(TourEvent.objects.get().status,'unpublished')

    def test_verified_mapping_and_cancellation_asof(self):
        save_event(self.item,NOW); event=TourEvent.objects.get()
        with patch('places.event_models.timezone.now',return_value=NOW):
            link=EventTargetLink.objects.create(event=event,target=self.target,verified=True,evidence='verified venue')
        self.assertEqual(len(event_rows(self.target,NOW)),1)
        with patch('places.event_models.timezone.now',return_value=NOW+timedelta(hours=1)):
            link.verified=False; link.save()
        self.assertEqual(len(event_rows(self.target,NOW)),1)
        self.assertEqual(event_rows(self.target,NOW+timedelta(hours=1)),[])

    def test_partial_sync_does_not_advance_watermark(self):
        state=CollectorState.objects.create(provider='tour_api',key='events',cursor={'watermark':NOW.isoformat()})
        client=Mock(); client.fetch_places_page.return_value=Mock(page_number=1,total_count=2,records=[])
        with self.assertRaises(Exception): collect_page(client,state,NOW+timedelta(hours=1))
        self.assertEqual(state.cursor['watermark'],NOW.isoformat())

    def test_missing_inputs_reproduce_and_report_without_false_pass(self):
        run=issue(self.target,NOW,now=NOW+timedelta(minutes=5))
        self.assertEqual(run.mode,'shadow')
        self.assertEqual(reproduce(run),run.payload)
        self.assertEqual(report(self.target)['status'],'NEEDS_MORE_DATA')
        self.assertEqual(report(self.target)['prediction_count'],0)
        self.study.state={'validation':{'status':'PASS'},'shadow_validation':{'status':'PASS'}}
        self.assertFalse(promotion_allowed(self.study))

    def test_manual_form_requires_evidence(self):
        form=EventForm(data={'external_id':'manual:rally','name':'집회','source':'manual',
            'start_date':'2026-03-01','end_date':'2026-03-01','status':'scheduled','size_weight':.5})
        self.assertFalse(form.is_valid())
        self.assertIn('공식 출처',str(form.errors))

    def test_late_event_and_truth_change_do_not_mutate_saved_run(self):
        from places.hourly_models import HourlyObservation
        run=issue(self.target,NOW,now=NOW)
        before=run.payload
        save_event(self.item,NOW+timedelta(hours=1))
        self.assertEqual(reproduce(run),before)
        valid=NOW+timedelta(hours=1)
        obs=HourlyObservation.objects.create(target=self.target,observed_at=valid,received_at=valid,
            value=0,fingerprint='zero',raw_path='',raw_hash='')
        first=report(self.target)
        self.assertEqual(first['truth_count'],1)
        self.assertEqual(first['prediction_count'],0)
        obs.value=15; obs.save()
        self.assertEqual(report(self.target)['rows'][0]['actual'],15)
        run.refresh_from_db(); self.assertEqual(run.payload,before)

    def test_promotion_and_freeze_cannot_use_old_pass(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        self.study.state={'event_selection':{'status':'PASS'},'event_holdout':{'status':'PASS'},'event_shadow':{'status':'PASS'}}
        self.study.save()
        with self.assertRaises(CommandError): call_command('event_crowd','promote',study=self.study.pk)

    def test_unverified_link_is_not_advice(self):
        save_event(self.item,NOW)
        with patch('places.event_models.timezone.now',return_value=NOW):
            EventTargetLink.objects.create(event=TourEvent.objects.get(),target=self.target)
        self.assertEqual(event_rows(self.target,NOW),[])

    def test_budget_resume_skips_completed_details(self):
        state=CollectorState.objects.create(provider='tour_api',key='events',cursor={'watermark':NOW.isoformat()})
        client=Mock()
        items=[{k:v for k,v in (self.item|{'contentid':str(n)}).items() if not k.startswith('event')} for n in (1,2)]
        client.fetch_places_page.return_value=Mock(page_number=1,total_count=2,records=[Mock(raw_data=i) for i in items])
        good=Mock(raw_data={'common':{},'intro':{'eventstartdate':'20260301','eventenddate':'20260302'}})
        from places.services.crowd_collector import BudgetExhausted
        client.fetch_place_detail.side_effect=[good,BudgetExhausted('limit')]
        with self.assertRaises(BudgetExhausted): collect_page(client,state,NOW)
        self.assertEqual(state.cursor['page_done'],['1:'])
        client.fetch_place_detail.reset_mock(); client.fetch_place_detail.side_effect=None; client.fetch_place_detail.return_value=good
        self.assertTrue(collect_page(client,state,NOW+timedelta(hours=1)))
        client.fetch_place_detail.assert_called_once_with('2','15')

    def test_prune_preserves_latest_mapping_but_removes_old_versions(self):
        from places.services.event_context import prune
        from places.services.mean_archive import append
        old=NOW-timedelta(days=401)
        append('event_link','x',old,{'verified':False})
        append('event_link','x',old+timedelta(hours=1),{'verified':True})
        prune(NOW)
        self.assertEqual(MeanEvidence.objects.filter(kind='event_link').count(),1)
        self.assertTrue(MeanEvidence.objects.get(kind='event_link').payload['verified'])
