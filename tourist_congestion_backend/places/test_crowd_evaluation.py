from datetime import timedelta
from django.test import TestCase
from places.models import CrowdArea, CrowdData, ForecastEvaluation, Place
from places.services.crowd_evaluation import evaluate_forecasts
from places.services.crowd_estimator import estimate, opening_status
from places.test_crowd_estimator import NOW, observed


class EvaluationTests(TestCase):
    def setUp(self):
        self.area=CrowdArea.objects.create(source='seoul_realtime',external_id='POI001',name='test',last_synced_at=NOW)
        self.place=Place.objects.create(name='test',latitude=37,longitude=127,category='관광지',region_code='11',address='서울')

    def row(self, **kwargs):
        return ForecastEvaluation.objects.create(place=self.place,crowd_area=self.area,issued_at=NOW,
            valid_at=NOW+timedelta(hours=1),hours_ahead=1,predicted_score=80,baseline_score=50,
            persistence_score=70,distribution=list(range(100)),model_version='heuristic-v1',**kwargs)

    def test_only_later_real_observation_is_a_label(self):
        row=self.row(); at=NOW+timedelta(hours=1)
        CrowdData.objects.create(crowd_area=self.area,observed_at=at,fetched_at=at,population_min=99,population_max=99,raw_data={'dev_seed':True})
        evaluate_forecasts(at+timedelta(minutes=20)); row.refresh_from_db(); self.assertIsNone(row.actual_score)
        CrowdData.objects.create(crowd_area=self.area,observed_at=at+timedelta(minutes=1),fetched_at=at+timedelta(minutes=2),population_min=80,population_max=80)
        report=evaluate_forecasts(at+timedelta(minutes=20)); row.refresh_from_db()
        self.assertEqual(row.actual_score,80.5); self.assertEqual(report['disabled_horizons'],[])

    def test_sufficient_bad_forecast_disables_horizon(self):
        rows=[]
        for i in range(105):
            at=NOW-timedelta(days=i%7+1,minutes=i)
            rows.append(ForecastEvaluation(place=self.place,crowd_area=self.area,issued_at=at,valid_at=at+timedelta(hours=2),
                hours_ahead=2,predicted_score=90,baseline_score=51,persistence_score=60,distribution=[1],actual_score=50,model_version='heuristic-v1'))
        ForecastEvaluation.objects.bulk_create(rows)
        self.assertIn(2,evaluate_forecasts(NOW)['disabled_horizons'])
        forecast=estimate(observed(),NOW,trend_enabled=(True,False,True))[0]['forecast'][1]
        self.assertTrue(forecast['baseline_fallback']); self.assertEqual(forecast['crowd_score'],51)

    def test_only_reviewed_current_schedule_affects_closure(self):
        schedule={'verified':True,'evidence':'operator','valid_until':'2026-12-31',
                  'weekdays':{str(NOW.weekday()):[['09:00','14:00']]}}
        self.assertEqual(opening_status(schedule,NOW),'CLOSED')
        schedule['verified']=False
        self.assertIsNone(opening_status(schedule,NOW))
