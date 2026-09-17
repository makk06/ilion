from datetime import timedelta
from django.test import TestCase
from places.models import CrowdArea, CrowdData, ForecastEvaluation, Place
from places.services.crowd_evaluation import evaluate_forecasts, record_forecast
from places.services.crowd_estimator import estimate, opening_status
from places.test_crowd_estimator import NOW, observed


class EvaluationTests(TestCase):
    def setUp(self):
        self.area=CrowdArea.objects.create(source='seoul_realtime',external_id='POI001',name='test',last_synced_at=NOW)
        self.place=Place.objects.create(name='test',latitude=37,longitude=127,category='관광지',region_code='11',address='서울')

    def row(self, **kwargs):
        return ForecastEvaluation.objects.create(place=self.place,crowd_area=self.area,issued_at=NOW,
            valid_at=NOW+timedelta(hours=1),hours_ahead=1,predicted_score=80,baseline_score=50,
            persistence_score=70,distribution=list(range(100)),model_version='heuristic-v1',scope='area_core',**kwargs)

    def test_only_later_real_observation_is_a_label(self):
        row=self.row(); at=NOW+timedelta(hours=1)
        CrowdData.objects.create(crowd_area=self.area,observed_at=at,fetched_at=at,population_min=99,population_max=99,raw_data={'dev_seed':True})
        evaluate_forecasts(at+timedelta(minutes=20)); row.refresh_from_db(); self.assertIsNone(row.actual_score)
        CrowdData.objects.create(crowd_area=self.area,observed_at=at+timedelta(minutes=1),fetched_at=at+timedelta(minutes=2),population_min=80,population_max=80)
        report=evaluate_forecasts(at+timedelta(minutes=20)); row.refresh_from_db()
        self.assertEqual(row.actual_score,80.5); self.assertTrue(report['warnings_only'])

    def test_missing_after_deadline_and_late_receipt_excluded(self):
        row=self.row()
        at=row.valid_at
        CrowdData.objects.create(crowd_area=self.area, observed_at=at, fetched_at=at+timedelta(hours=25), population_min=80,population_max=80)
        evaluate_forecasts(at+timedelta(hours=26));row.refresh_from_db()
        self.assertEqual(row.status,'missing');self.assertIsNone(row.actual_score)

    def test_area_core_ignores_poi_and_accepts_delayed_population(self):
        data=observed();data['mapping']['area_id']=self.area.pk
        data['population']['observed_at']=NOW-timedelta(minutes=30)
        record_forecast(self.place,data,{'is_stale':True},NOW)
        rows=list(ForecastEvaluation.objects.order_by('hours_ahead'))
        self.assertEqual(len(rows),3);self.assertIsNone(rows[0].place_id)
        first=[r.predicted_score for r in rows]
        ForecastEvaluation.objects.all().delete()
        data.update(profile='beach',latitude=0,longitude=0)
        data['mapping']['representativeness']=.4
        record_forecast(self.place,data,{},NOW)
        self.assertEqual(first,list(ForecastEvaluation.objects.order_by('hours_ahead').values_list('predicted_score',flat=True)))
        record_forecast(self.place,data,{},NOW+timedelta(minutes=1))
        self.assertEqual(ForecastEvaluation.objects.count(),3)

    def test_versions_report_separately_and_do_not_disable(self):
        for version in ('one','two'):
            row=self.row( );row.issued_at=NOW-timedelta(minutes=1 if version=='one' else 2);row.model_version=version;row.status='matched';row.actual_score=0;row.valid_at=NOW-timedelta(seconds=1);row.actual_observed_at=row.valid_at;row.actual_received_at=NOW;row.save()
        result=evaluate_forecasts(NOW)
        self.assertEqual(len(result['metrics']),2)
        self.assertNotIn('disabled_horizons',result)
        self.assertFalse(any(r['sufficient'] for r in result['metrics']))

    def test_missing_one_horizon_does_not_block_other_horizons(self):
        data=observed();data['mapping']['area_id']=self.area.pk
        at=NOW+timedelta(hours=1)
        del data['baselines'][at.weekday(),at.hour]
        record_forecast(self.place,data,{},NOW)
        self.assertEqual(list(ForecastEvaluation.objects.order_by('hours_ahead').values_list('hours_ahead',flat=True)),[2,3])

    def test_invalid_expired_and_future_population_not_recorded(self):
        for delta in (-61,1):
            data=observed();data['mapping']['area_id']=self.area.pk
            data['population']['observed_at']=NOW+timedelta(minutes=delta)
            record_forecast(self.place,data,{},NOW)
        data=observed();data['mapping']['area_id']=self.area.pk
        data['population']['value']=float('nan')
        record_forecast(self.place,data,{},NOW)
        self.assertFalse(ForecastEvaluation.objects.exists())

    def test_daily_baseline_revisions_share_policy_cohort(self):
        for index, version in enumerate(('2026-09-10','2026-09-11')):
            row=self.row();row.issued_at=NOW-timedelta(days=index+1);row.baseline_version=version
            row.status='matched';row.actual_score=50;row.valid_at=row.issued_at+timedelta(hours=1);row.actual_observed_at=row.valid_at;row.actual_received_at=row.valid_at+timedelta(minutes=30);row.save()
        result=evaluate_forecasts(NOW)
        self.assertEqual(len(result['metrics']),1)
        self.assertEqual(result['metrics'][0]['baseline_versions'],['2026-09-10','2026-09-11'])

    def test_as_of_report_excludes_later_received_labels(self):
        row=self.row()
        row.issued_at=NOW-timedelta(hours=2);row.valid_at=NOW-timedelta(hours=1)
        row.actual_observed_at=row.valid_at;row.actual_received_at=NOW+timedelta(minutes=10)
        row.actual_score=50;row.status='matched';row.save()
        self.assertEqual(evaluate_forecasts(NOW)['metrics'],[])
        self.assertEqual(len(evaluate_forecasts(NOW+timedelta(minutes=11))['metrics']),1)

    def test_only_reviewed_current_schedule_affects_closure(self):
        schedule={'verified':True,'evidence':'operator','valid_until':'2026-12-31',
                  'weekdays':{str(NOW.weekday()):[['09:00','14:00']]}}
        self.assertEqual(opening_status(schedule,NOW),'CLOSED')
        schedule['verified']=False
        self.assertIsNone(opening_status(schedule,NOW))
