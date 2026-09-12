from copy import deepcopy
from datetime import datetime, timedelta
from unittest import TestCase

from places.services.crowd_estimator import KST, estimate, event_effect, ewma, level, percentile, prior, profile_for, weather_effect
from places.services.crowd_confidence import freshness


NOW = datetime(2026, 9, 12, 15, 0, tzinfo=KST)


def inputs():
    return {'place_id': 1, 'latitude': 37.57, 'longitude': 126.97, 'profile': 'park',
            'indoor_outdoor': 'outdoor', 'events': [], 'sources': [], 'baselines': {},
            'distribution': [], 'calendars': {}, 'mapping': {}}


def observed():
    data = inputs()
    data.update(mapping={'area_id': 1, 'match_quality': 1, 'representativeness': 1},
        population={'value': 80, 'min': 75, 'max': 85, 'observed_at': NOW, 'level': 'busy'},
        distribution=list(range(100)), baseline_version='v1',
        baselines={(d,h): {'median': 50, 'sample_days': 8, 'coverage': 1, 'context': {}}
                   for d in range(7) for h in range(24)})
    return data


class CrowdEstimatorTests(TestCase):
    def test_future_confidence_uses_future_history_sample_days(self):
        data=observed()
        full=estimate(data,NOW)[0]
        future=NOW+timedelta(hours=1)
        data['baselines'][future.weekday(),future.hour]['sample_days']=4
        sparse=estimate(data,NOW)[0]
        self.assertEqual(full['confidence'],sparse['confidence'])
        self.assertLess(sparse['forecast'][0]['confidence'],full['forecast'][0]['confidence'])
        self.assertEqual(full['forecast'][1]['confidence'],sparse['forecast'][1]['confidence'])

    def test_live_kto_beach_classification_without_legacy_category(self):
        # Haeundae 126081: new classification returned with empty legacy cat3.
        self.assertEqual(profile_for({'contenttypeid':'12','cat3':'','lclsSystm3':'NA020900'}), 'beach')
        self.assertEqual(profile_for({'contenttypeid':'12','lclsSystm3':'UNREVIEWED'}), 'day_visit')

    def test_bins_and_midrank(self):
        self.assertEqual([level(x)[0] for x in (0,20,21,40,41,65,66,85,86,100)],
                         ['VERY_LOW','VERY_LOW','LOW','LOW','NORMAL','NORMAL','HIGH','HIGH','VERY_HIGH','VERY_HIGH'])
        self.assertEqual(percentile([10]*100, 10), 50)
        self.assertEqual(percentile([1,2,3], 0), 0)
        self.assertEqual(percentile([1,2,3], 4), 100)
        self.assertEqual(percentile([10,20,30],20), percentile([100,200,300],200))

    def test_prior_weekend_holiday_not_double_counted_and_midnight(self):
        self.assertEqual(prior('park', NOW), prior('park',NOW,{'is_holiday':True}))
        self.assertEqual(prior('park',NOW,{'holiday_run':3}), prior('park',NOW)+3)
        before=NOW.replace(hour=23,minute=59,second=59)
        self.assertAlmostEqual(prior('park',before),prior('park',before+timedelta(seconds=1)),places=2)

    def test_nationwide_cold_start_is_explicit_low_quality(self):
        payload, state=estimate(inputs(),NOW)
        self.assertEqual(payload['tier'],'C')
        self.assertLessEqual(payload['confidence'],.2)
        self.assertEqual(payload['normalization'],'heuristic_prior')
        self.assertIsNone(payload['estimated_visitors'])
        self.assertIsNone(payload['data_as_of'])
        self.assertEqual(len(payload['forecast']),3)
        self.assertFalse(state['history'])

    def test_bootstrap_and_low_denominator(self):
        data=observed(); data['distribution']=[]
        result,_=estimate(data,NOW)
        self.assertEqual(result['normalization'],'provider_category_bootstrap')
        self.assertLessEqual(result['confidence'],.55)
        self.assertIsNone(result['relative_to_normal'])
        data=observed(); data['baselines'][NOW.weekday(),NOW.hour]['median']=0
        self.assertIsNone(estimate(data,NOW)[0]['relative_to_normal'])

    def test_replaced_and_demo_are_not_observations(self):
        for flag in ('is_replaced','is_demo'):
            data=observed(); data['distribution']=[]
            if flag=='is_demo': data[flag]=True
            else: data['population'][flag]=True
            result,state=estimate(data,NOW)
            self.assertEqual(result['tier'],'C')
            self.assertFalse(state['history'])

    def test_freshness_quality_decreases_and_ttl(self):
        data=observed()
        current=estimate(data,NOW)[0]
        aged=estimate(data,NOW+timedelta(minutes=25))[0]
        self.assertLess(aged['confidence'],current['confidence'])
        data['mapping']['representativeness']=.4
        self.assertLess(estimate(data,NOW)[0]['confidence'],current['confidence'])
        self.assertEqual(freshness(NOW,NOW+timedelta(hours=1),'population'),0)
        self.assertEqual(freshness(NOW,NOW+timedelta(minutes=30),'transit'),0)
        self.assertEqual(freshness(NOW+timedelta(hours=1),NOW,'population'),0)

    def test_observed_delta_decays_toward_future_baseline(self):
        payload,_=estimate(observed(),NOW)
        residuals=[r['crowd_score']-r['baseline_score'] for r in payload['forecast']]
        self.assertGreater(residuals[0],residuals[1]); self.assertGreater(residuals[1],residuals[2])
        self.assertTrue(all(f['confidence']<=payload['confidence'] for f in payload['forecast']))
        self.assertAlmostEqual(sum(f['contribution_points'] for f in payload['factors']),payload['crowd_score'],places=2)

    def test_environment_is_suppressed_when_observations_are_strong(self):
        def change(data):
            before=estimate(data,NOW)[0]['crowd_score']
            data['weather']={'issued_at':NOW,'values':{'temperature':20,'precipitation_type':1}}
            return abs(estimate(data,NOW)[0]['crowd_score']-before)
        self.assertLess(change(observed()),change(inputs()))

    def test_identical_weather_in_baseline_is_not_added_twice(self):
        data=observed(); data['weather']={'issued_at':NOW,'values':{'temperature':20,'precipitation_type':1}}
        data['baselines'][NOW.weekday(),NOW.hour]['context']={'weather_park':-.8}
        self.assertEqual(next(f for f in estimate(data,NOW)[0]['factors'] if f['key']=='weather')['contribution_points'],0)

    def test_transit_requires_comparable_history_and_does_not_sum_people(self):
        data=inputs(); data['mapping']={'match_quality':1,'representativeness':1}
        signal={'value':200,'baseline':100,'sample_days':4,'observed_at':NOW,'timestamp_quality':'source'}
        data['transit']=[signal]
        single=estimate(data,NOW)[0]
        data['transit']=[signal,deepcopy(signal)]
        self.assertEqual(estimate(data,NOW)[0]['crowd_score'],single['crowd_score'])
        data['transit'][0]['sample_days']=0; data['transit']=data['transit'][:1]
        self.assertEqual(estimate(data,NOW)[0]['tier'],'C')

    def test_ewma_only_new_observation_and_gap_reset(self):
        value,history,_=ewma(10,NOW,None,NOW)
        second,h2,_=ewma(100,NOW,{'history':history},NOW+timedelta(minutes=1))
        self.assertEqual(second,value); self.assertEqual(h2,history)
        self.assertEqual(ewma(30,NOW+timedelta(minutes=30),{'history':history},NOW+timedelta(minutes=30))[0],30)

    def test_delayed_source_series_retains_ewma_without_refreshing_quality(self):
        value,history,_=ewma(10,NOW,None,NOW+timedelta(minutes=31))
        self.assertEqual(len(history),1)
        second,h2,_=ewma(30,NOW+timedelta(minutes=5),{'history':history},NOW+timedelta(minutes=36))
        self.assertEqual(len(h2),2)
        self.assertGreater(second,value)
        self.assertLess(second,30)
        self.assertLess(freshness(NOW+timedelta(minutes=5),NOW+timedelta(minutes=36),'population'),1)

    def test_event_dates_distance_dedup_and_verified_ramps(self):
        event={'external_id':'1','latitude':37.57,'longitude':126.97,'start_date':NOW.date(),'end_date':NOW.date()}
        self.assertAlmostEqual(event_effect([event,event],37.57,126.97,NOW),.175)
        self.assertEqual(event_effect([event],35,129,NOW),0)
        event.update(time_quality='verified',starts_at=NOW,ends_at=NOW+timedelta(hours=1))
        self.assertAlmostEqual(event_effect([event],37.57,126.97,NOW-timedelta(minutes=30)),.25)
        self.assertEqual(event_effect([event],37.57,126.97,NOW+timedelta(hours=2)),0)

    def test_weather_profiles_and_missing_future_weather(self):
        values={'temperature':20,'precipitation_type':3}
        self.assertEqual(weather_effect('park','outdoor',values),(-.8,1))
        self.assertEqual(weather_effect('park','unknown',values),(-.8,.5))
        self.assertEqual(weather_effect('shopping','indoor',values),(.2,1))
        self.assertEqual(weather_effect('unknown','unknown',values),(0,0))
        data=inputs(); data['weather']={'issued_at':NOW,'values':values}
        self.assertTrue(all(not f['weather_available'] for f in estimate(data,NOW)[0]['forecast']))
