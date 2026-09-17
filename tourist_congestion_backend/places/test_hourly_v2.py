import copy
import math
import os
import tempfile
from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase, SimpleTestCase
from places.hourly_models import HourlyStudy, HourlyTarget, HourlyObservation, HourlyRun, HourlyForecast
from places.services.hourly_forecast import predict, samples, dt, PARAMETERS
from places.services.hourly_store import record, dataset, issue, reproduce, match_truth, digest
from places.services.hourly_collector import capacity, select, tick
from places.services.hourly_evaluation import evaluate, select_parameters, validate_shadow, promote
from places.services.hourly_evaluation import gate, monitor
from places.services.hourly_adapter import adapt_many
from places.services.hourly_decisions import CONTRACT
from places.integrations.tmap_density import normalize
from places.integrations.exceptions import ExternalAPIError
from places.services.crowd_collector import charge, BudgetExhausted, acquire_lease, release_lease

NOW = dt('2026-05-10T12:00:00+09:00')


def history(value=100):
    rows = []
    for day in range(1, 57):
        for hour in range(24):
            at = (NOW-timedelta(days=day)).replace(hour=hour)-timedelta(minutes=10)
            rows.append({'observed_at': at, 'received_at': at+timedelta(minutes=8), 'value': value})
    return {'provider': 'seoul', 'external_id': 'A', 'metric': 'population_count', 'observations': rows}


class CalculationTests(SimpleTestCase):
    def test_hand_computed_current_and_arithmetic(self):
        data = history()
        data['observations'].append({'observed_at': NOW-timedelta(minutes=10), 'received_at': NOW-timedelta(minutes=1), 'value': 130})
        forecasts = predict(data, NOW, {'tau': 3})
        for h, r in enumerate(forecasts, 1):
            self.assertAlmostEqual(r['value'], 100+math.exp(-h/3)*30)
        self.assertEqual(len(PARAMETERS), 16)
        self.assertEqual(predict(data, NOW)[0]['value'], 100)

    def test_recency_and_negative_floor(self):
        data = history()
        for r in data['observations']:
            r['value'] = 200 if r['observed_at'] > NOW-timedelta(days=14) else 100
        self.assertGreater(predict(data, NOW, {'half_life': 14})[0]['value'], predict(data, NOW)[0]['value'])
        data = history(1)
        for r in data['observations']:
            if (r['observed_at']+timedelta(minutes=10)).hour == 12:
                r['value'] = 100
        data['observations'].append({'observed_at': NOW-timedelta(minutes=10), 'received_at': NOW-timedelta(minutes=1), 'value': 0})
        self.assertEqual(predict(data, NOW, {'tau': 3})[0]['value'], 0)

    def test_boundaries_duplicates_and_invalid_values(self):
        data = history()
        valid = {'observed_at': NOW-timedelta(minutes=15), 'received_at': NOW, 'value': 0}
        data['observations'] += [valid, {**valid, 'value': 99, 'received_at': NOW+timedelta(seconds=1)}]
        self.assertEqual(samples(data, NOW)[NOW]['value'], 0)
        for value in (float('nan'), float('inf'), -1, True, None):
            bad = {'observations': [{**valid, 'value': value}]}
            self.assertNotIn(NOW, samples(bad, NOW))
        self.assertNotIn(NOW, samples({'observations': [{**valid, 'observed_at': NOW-timedelta(minutes=15, seconds=1)}]}, NOW))
        self.assertEqual(predict(history(), NOW, {'tau': 3})[0]['reasons'], ['current_unavailable', 'calendar_unknown'])
        for now in ('2026-06-01T00:00:00+09:00', '2026-05-31T23:00:00+09:00'):
            result = predict(history(), dt(now))
            self.assertEqual(dt(result[2]['valid_at']), dt(now)+timedelta(hours=3))

    def test_no_history_mixed_units_and_future_leakage(self):
        data = history()
        original = predict(data, NOW)
        data['observations'].append({'observed_at': NOW+timedelta(hours=1), 'received_at': NOW+timedelta(hours=1), 'value': 999999})
        self.assertEqual(predict(data, NOW), original)
        data['observations'][0]['provider'] = 'tmap'
        with self.assertRaises(ValueError): predict(data, NOW)
        data = history(.01)
        data.update(provider='tmap', metric='population_density')
        self.assertIsNone(predict(data, NOW)[0]['population'])
        self.assertEqual(predict({**data, 'observations': []}, NOW)[0]['status'], 'insufficient_history')

    def test_tmap_only_exact_place_and_valid_zero(self):
        raw = {'status': {'code': '00'}, 'contents': {'poiId': 'X', 'rltm': [{'type': 1, 'congestion': 0, 'datetime': '20260510115000'}]}}
        self.assertEqual(normalize(raw, 'X')['value'], 0)
        raw['contents']['rltm'][0]['type'] = 2
        with self.assertRaises(ExternalAPIError): normalize(raw, 'X')
        raw['contents']['rltm'][0]['type'] = 1
        with self.assertRaises(ExternalAPIError): normalize(raw, 'Y')


class StorageTests(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.env = patch.dict(os.environ, {'HOURLY_RAW_DIR': self.directory.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.study = HourlyStudy.objects.create(provider='seoul', started_at=NOW)
        self.target = HourlyTarget.objects.create(study=self.study, external_id='A', name='A', metric='population_count', scope='area_population', selected=True, mapping={'place_ids': [1]})

    def test_append_revisions_reproduction_and_truth_independence(self):
        data = history()
        for r in data['observations']:
            record(self.target, r, {'count': r['value']}, r['received_at'])
        reading = {'observed_at': NOW-timedelta(minutes=10), 'value': 120}
        original = record(self.target, reading, {'count': 120}, NOW-timedelta(minutes=1))
        duplicate = record(self.target, reading, {'count': 120}, NOW)
        self.assertEqual(original.pk, duplicate.pk)
        run = issue(self.target, NOW, {'tau': 3})
        self.assertNotIn('evidence_ids', run.inputs)
        before = reproduce(run)
        record(self.target, {**reading, 'value': 999}, {'count': 999}, NOW+timedelta(minutes=1))
        self.assertEqual(reproduce(run), before)
        self.assertEqual(issue(self.target, NOW).pk, run.pk)
        self.assertEqual(run.forecasts.count(), 3)
        target_time = NOW+timedelta(hours=1)
        record(self.target, {'observed_at': target_time-timedelta(minutes=10), 'value': 95}, {'count': 95}, target_time-timedelta(minutes=1))
        match_truth(target_time)
        forecast = run.forecasts.order_by('valid_at').first()
        self.assertEqual(forecast.actual, 95)
        forecast.actual = 999
        forecast.save()
        self.assertEqual(reproduce(run), before)
        original.delete()
        with self.assertRaises(ValueError): reproduce(run)

    def test_budget_capacity_and_global_lease(self):
        with patch.dict(os.environ, {'TMAP_DAILY_LIMIT': '100', 'TMAP_OTHER_DAILY_CALLS': '8'}):
            self.assertEqual(capacity('tmap'), 3)
            for _ in range(80): charge('tmap', now=NOW)
            with self.assertRaises(BudgetExhausted): charge('tmap', now=NOW)
            for _ in range(20): charge('tmap', retry=True, now=NOW)
            with self.assertRaises(BudgetExhausted): charge('tmap', retry=True, now=NOW)
        owner = acquire_lease(NOW)
        self.assertIsNone(acquire_lease(NOW))
        release_lease(owner)
        self.assertIsNotNone(acquire_lease(NOW))

    def test_insufficient_history_never_promotes_or_changes_legacy(self):
        self.assertEqual(evaluate(self.study, NOW)['status'], 'NEEDS_MORE_DATA')
        self.assertEqual(validate_shadow(self.study, NOW)['status'], 'NEEDS_MORE_DATA')
        with self.assertRaises(ValueError): promote(self.study, NOW)
        old = {1: {'forecast': [{'legacy': True}]}}
        self.assertEqual(adapt_many(copy.deepcopy(old), NOW), old)

    def test_density_adapter_missing_and_provider_switch(self):
        self.study.provider = 'tmap'
        parameters = {'half_life': None, 'tau': None}
        self.study.state = {'parameters': parameters, 'validation': {'status': 'PASS', 'parameter_hash': digest(parameters)},
                            'shadow_validation': {'status': 'PASS', 'parameter_hash': digest(parameters)}}
        from places.services.hourly_evaluation import selection_hash
        self.study.state.update(decision_contract=CONTRACT, selection_guidance_pass=True, selection_ranking_pass=False, reference='arithmetic', scales={str(self.target.pk): .01}, peaks={str(self.target.pk): .02},
            frozen_at=(NOW-timedelta(days=30, minutes=1)).isoformat(), holdout_start=(NOW-timedelta(days=30)).isoformat(),
            frozen_targets=[self.target.pk])
        self.study.state['selection_hash'] = selection_hash(self.study)
        for name in ('validation', 'shadow_validation'):
            self.study.state[name]['selection_hash'] = self.study.state['selection_hash']
            self.study.state[name]['decision_contract_version'] = CONTRACT['version']
            self.study.state[name]['usability'] = {'guidance': {'status': 'PASS'}, 'ranking': {'status': 'NEEDS_MORE_DATA'}}
        self.study.save()
        self.target.metric, self.target.scope, self.target.promoted = 'population_density', 'place_density', True
        self.target.save()
        result = adapt_many({1: {'forecast': []}}, NOW)[1]['forecast'][0]
        self.assertIsNone(result['value'])
        self.assertIsNone(result['area_population'])
        self.assertEqual(result['unit'], 'persons_per_m2')
        self.assertEqual(result['reasons'], ['forecast_missing'])

    def test_selection_uses_168_scheduled_slots_not_observation_rows(self):
        start = NOW-timedelta(days=7)
        self.study.state = {'collection_start': start.isoformat()}
        self.study.save()
        self.target.active = True
        self.target.save()
        for hour in range(152):
            at = start+timedelta(hours=hour)-timedelta(minutes=10)
            record(self.target, {'observed_at': at, 'value': 1}, {}, at+timedelta(minutes=1))
        select(self.study, NOW)
        self.target.refresh_from_db()
        self.assertTrue(self.target.selected)
        self.assertEqual(self.study.state['rates'][str(self.target.pk)], 152/168)

    def test_density_normalization_and_single_target_gate(self):
        self.study.provider = 'tmap'
        self.study.state = {'scales': {str(self.target.pk): .01}, 'peaks': {str(self.target.pk): .01}}
        rows = [{'area_id': self.target.pk, 'issued_at': (NOW+timedelta(hours=i)).isoformat(),
                 'hours_ahead': h, 'population': .011, 'actual': .01, 'arithmetic': .015, 'reference': .015, 'weekly': .015, 'persistence': .01,
                 'parameters': {'tau': 3}} for i in range(14*24) for h in (1, 2, 3)]
        report = gate(rows, self.study)
        # Relative peak evaluation requires as-of percentile evidence, not a fixed density cutoff.
        self.assertEqual(report['numeric_status'], 'NEEDS_MORE_DATA')
        self.assertEqual(report['status'], 'NEEDS_MORE_DATA')
        self.assertAlmostEqual(report['metrics']['value']['nmae'], .1)
        self.assertEqual(report['unit'], 'persons_per_m2')

    def test_zero_mean_refuses_parameter_selection(self):
        start = NOW-timedelta(days=84)
        self.study.state = {'training_start': start.isoformat()}
        points = {start+timedelta(hours=i): {'value': 0} for i in range(56*24)}
        with patch('places.services.hourly_evaluation.samples', return_value=points):
            self.assertIn('zero_training_mean', select_parameters(self.study, NOW)['reasons'])

    def test_later_calendar_revision_does_not_change_saved_run(self):
        from places.mean_models import MeanEvidence
        day = NOW.date().isoformat()
        MeanEvidence.objects.create(kind='calendar', key=day, received_at=NOW-timedelta(days=1),
            fingerprint='c1', payload={'is_holiday': False})
        run = issue(self.target, NOW)
        before = reproduce(run)
        MeanEvidence.objects.create(kind='calendar', key=day, received_at=NOW+timedelta(hours=1),
            fingerprint='c2', payload={'is_holiday': True})
        self.assertFalse(run.inputs['calendar'][day])
        self.assertEqual(reproduce(run), before)

    def test_collector_one_read_per_slot_and_late_receipt_is_not_current(self):
        study = HourlyStudy.objects.create(provider='tmap', started_at=NOW)
        target = HourlyTarget.objects.create(study=study, external_id='X', name='X', metric='population_density', scope='place_density')
        before = NOW-timedelta(minutes=2)
        reading = {'observed_at': NOW-timedelta(minutes=10), 'value': .02}
        with patch.dict(os.environ, {'TMAP_APP_KEY': 'test', 'TMAP_DAILY_LIMIT': '100'}), \
             patch('places.services.hourly_collector.timezone.now', return_value=before), \
             patch('places.services.hourly_collector.TmapDensityClient') as client:
            client.return_value.fetch.return_value = (reading, {'value': .02})
            tick(before)
            tick(before)
            self.assertEqual(client.return_value.fetch.call_count, 1)
        self.assertEqual(HourlyObservation.objects.filter(target=target).count(), 1)
        late = {'observations': [{'observed_at': before, 'received_at': NOW+timedelta(seconds=1), 'value': 1}]}
        self.assertNotIn(NOW, samples(late, NOW+timedelta(hours=1)))

    def test_initialization_does_not_start_selection_clock_without_collection(self):
        study = HourlyStudy.objects.create(provider='tmap', started_at=NOW)
        HourlyTarget.objects.create(study=study, external_id='X', name='X', metric='population_density', scope='place_density')
        with patch.dict(os.environ, {'TMAP_APP_KEY': 'test', 'TMAP_DAILY_LIMIT': '100'}):
            tick(NOW+timedelta(minutes=10))
        study.refresh_from_db()
        self.assertNotIn('collection_start', study.state)

    def test_three_distinct_bad_days_rollback_is_idempotent(self):
        self.study.state = {'parameters': {'tau': 3, 'half_life': None}}
        self.study.save()
        self.target.promoted = True
        self.target.save()
        rows = [{'area_id': self.target.pk, 'hours_ahead': h, 'population': 150,
                 'arithmetic': 101, 'actual': 100} for i in range(101) for h in (1, 2, 3)]
        with patch('places.services.hourly_evaluation.stored_rows', return_value=rows):
            monitor(NOW)
            monitor(NOW)
            self.target.refresh_from_db()
            self.assertTrue(self.target.promoted)
            monitor(NOW+timedelta(days=1))
            monitor(NOW+timedelta(days=2))
        self.target.refresh_from_db()
        self.assertFalse(self.target.promoted)
