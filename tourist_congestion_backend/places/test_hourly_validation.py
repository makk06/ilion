import copy
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from django.test import TestCase, SimpleTestCase
from places.hourly_models import HourlyStudy, HourlyTarget, HourlyObservation, HourlyRun
from places.services.hourly_forecast import dt
from places.services.hourly_decisions import CONTRACT
from places.services.hourly_evaluation import (stored_rows, evaluate, select_parameters, require_frozen,
                                              selection_hash, row, advance)
from places.services.mean_validation import assess, improvement_interval
from places.services.hourly_reporting import export_report

NOW = dt('2026-09-01T00:00:00+09:00')


def rows():
    return [{'area_id': a, 'issued_at': (NOW+timedelta(hours=i)).isoformat(),
             'valid_at': (NOW+timedelta(hours=i+h)).isoformat(), 'hours_ahead': h,
             'population': 101, 'actual': 100, 'arithmetic': 110, 'reference': 110,
             'weekly': 112, 'persistence': 108}
            for a in (1, 2) for i in range(14*24-3) for h in (1, 2, 3)]


class GateTests(SimpleTestCase):
    def assess(self, data):
        return assess(data, [1, 2], {'1': 100, '2': 100}, {'1': 100, '2': 100},
                      reference='reference', required_areas=None, date_field='valid_at', strict_coverage=True)

    def test_cell_coverage_cannot_hide_in_provider_average(self):
        data = rows()
        self.assertEqual(self.assess(data)['status'], 'PASS')
        for r in [r for r in data if r['area_id'] == 2 and r['hours_ahead'] == 3][:40]:
            r['population'] = None
        report = self.assess(data)
        self.assertGreater(report['provided_rate'], .9)
        self.assertLess(report['coverage_cells']['2:3']['provided_rate'], .9)
        self.assertEqual(report['status'], 'NEEDS_MORE_DATA')

    def test_comparator_coverage_and_truth_are_independent(self):
        data = rows()
        for r in data:
            r['weekly'] = None
        report = self.assess(data)
        self.assertEqual(report['label_rate'], 1)
        self.assertEqual(report['provided_rate'], 1)
        self.assertEqual(report['paired_rate'], 0)
        self.assertEqual(report['status'], 'NEEDS_MORE_DATA')

    def test_bootstrap_clusters_target_korean_date_and_is_repeatable(self):
        data = rows()
        for r in data:
            r['issued_at'] = NOW.isoformat()
            r['population'] += dt(r['valid_at']).day % 3
        first = improvement_interval(data, 'arithmetic', {'1': 100, '2': 100}, 'valid_at')
        self.assertIsNotNone(first)
        self.assertEqual(first, improvement_interval(data, 'arithmetic', {'1': 100, '2': 100}, 'valid_at'))
        self.assertIsNone(improvement_interval(data, 'arithmetic', {'1': 100, '2': 100}))
        utc = copy.deepcopy(data)
        from datetime import timezone
        for r in utc:
            r['valid_at'] = dt(r['valid_at']).astimezone(timezone.utc).isoformat()
        self.assertEqual(first, improvement_interval(utc, 'arithmetic', {'1': 100, '2': 100}, 'valid_at'))

    def test_report_preserves_all_rows_and_gaps(self):
        data = rows()[:10]
        data[2]['population'] = None
        with tempfile.TemporaryDirectory() as directory:
            export_report(directory, {'status': 'AUXILIARY_ONLY'}, data)
            self.assertEqual(len((Path(directory)/'predictions.jsonl').read_text(encoding='utf-8').splitlines()), 10)
            self.assertIn('<svg', (Path(directory)/'series.html').read_text(encoding='utf-8'))
            self.assertTrue((Path(directory)/'report.json').exists())

    def test_forecast_rain_is_not_observed_rain(self):
        target = type('Target', (), {'pk': 1})()
        forecast = {'valid_at': NOW.isoformat(), 'issued_at': NOW.isoformat(), 'hours_ahead': 1,
                    'value': 1, 'comparisons': {}, 'parameters': {}, 'analysis': {'rain_forecast': True}}
        result = row(target, forecast, 1, {})
        self.assertIn('rain_forecast', result['tags'])
        self.assertNotIn('rain_observed', result['tags'])
        self.assertNotIn('rain', result['tags'])


class EvaluationLifecycleTests(TestCase):
    def setUp(self):
        self.study = HourlyStudy.objects.create(provider='seoul', started_at=NOW)
        self.target = HourlyTarget.objects.create(study=self.study, external_id='A', name='A',
            metric='population_count', scope='area_population', selected=True)

    def freeze(self):
        self.study.state = {'decision_contract': CONTRACT, 'selection_guidance_pass': True, 'selection_ranking_pass': True, 'parameters': {'half_life': None, 'tau': 3}, 'reference': 'arithmetic',
                            'recent_parameters': {'half_life': 28, 'tau': None},
                            'scales': {str(self.target.pk): 100}, 'peaks': {str(self.target.pk): 100},
                            'frozen_at': (NOW-timedelta(minutes=1)).isoformat(), 'holdout_start': NOW.isoformat(),
                            'frozen_targets': [self.target.pk]}
        self.study.state['selection_hash'] = selection_hash(self.study)
        self.study.save()

    def test_evaluate_never_selects_from_unfrozen_history(self):
        self.study.state = {'training_start': (NOW-timedelta(days=100)).isoformat()}
        with patch('places.services.hourly_evaluation.dataset') as dataset:
            self.assertIn('selection_not_frozen', evaluate(self.study, NOW)['reasons'])
            dataset.assert_not_called()
        self.assertNotIn('parameters', self.study.state)

    def test_changed_parameters_thresholds_or_cohort_refuse_evaluation(self):
        self.freeze()
        require_frozen(self.study)
        for field, value in [('parameters', {'tau': .5}), ('scales', {}), ('peaks', {}), ('reference', 'weekly')]:
            original = copy.deepcopy(self.study.state)
            self.study.state[field] = value
            with self.assertRaises(ValueError): evaluate(self.study, NOW)
            self.study.state = original
        self.target.selected = False
        self.target.save()
        with self.assertRaises(ValueError): require_frozen(self.study)

    def test_freeze_after_holdout_is_rejected_even_with_matching_hash(self):
        self.freeze()
        self.study.state['frozen_at'] = (NOW+timedelta(seconds=1)).isoformat()
        self.study.state['selection_hash'] = selection_hash(self.study)
        with self.assertRaises(ValueError): require_frozen(self.study)

    def test_missing_forecast_keeps_independent_valid_truth(self):
        self.freeze()
        valid = NOW+timedelta(hours=1)
        HourlyObservation.objects.create(target=self.target, observed_at=valid-timedelta(minutes=15),
            received_at=valid, value=0, fingerprint='truth', raw_path='', raw_hash='')
        HourlyObservation.objects.create(target=self.target, observed_at=valid-timedelta(minutes=1),
            received_at=valid+timedelta(seconds=1), value=999, fingerprint='late', raw_path='', raw_hash='')
        result = stored_rows(self.study, NOW, NOW+timedelta(hours=4))
        self.assertIsNone(result[0]['population'])
        self.assertEqual(result[0]['actual'], 0)
        self.assertIsNone(result[1]['actual'])

    def test_provider_failure_does_not_stop_other_provider(self):
        HourlyStudy.objects.create(provider='tmap', started_at=NOW)
        with patch('places.services.hourly_evaluation.select_parameters', side_effect=[ValueError('bad contract'), {'status': 'NEEDS_MORE_DATA'}]):
            result = advance()
        self.assertEqual(result['seoul']['status'], 'BLOCKED')
        self.assertEqual(result['tmap']['status'], 'NEEDS_MORE_DATA')

    def test_saved_prediction_replay_and_changed_truth_only_change_metrics(self):
        from places.services.hourly_store import issue, reproduce
        self.freeze()
        readings = []
        for i in range(16*24):
            at = NOW-timedelta(hours=i, minutes=10)
            readings.append(HourlyObservation(target=self.target, observed_at=at,
                received_at=at+timedelta(minutes=1), value=100, fingerprint=f'past{i}', raw_path='', raw_hash=''))
        HourlyObservation.objects.bulk_create(readings)
        run = issue(self.target, NOW, self.study.state['parameters'])
        HourlyRun.objects.filter(pk=run.pk).update(computed_at=NOW+timedelta(minutes=1))
        valid = NOW+timedelta(hours=1)
        truth = HourlyObservation.objects.create(target=self.target, observed_at=valid-timedelta(minutes=5),
            received_at=valid, value=90, fingerprint='future_truth', raw_path='', raw_hash='')
        before = reproduce(run)
        first = stored_rows(self.study, NOW, NOW+timedelta(hours=4))[0]
        self.assertEqual(first['actual'], 90)
        self.assertEqual(first['recent'], 100)
        self.assertEqual(first['population'], 100)
        truth.value = 80
        truth.save()
        second = stored_rows(self.study, NOW, NOW+timedelta(hours=4))[0]
        self.assertEqual(second['actual'], 80)
        self.assertEqual(second['population'], first['population'])
        self.assertEqual(reproduce(run), before)
        HourlyRun.objects.filter(pk=run.pk).update(computed_at=valid+timedelta(seconds=1))
        self.assertIsNone(stored_rows(self.study, NOW, NOW+timedelta(hours=4))[0]['population'])

    def test_late_selection_starts_fresh_holdout_and_is_idempotent(self):
        start = NOW-timedelta(days=84)
        self.study.state = {'training_start': start.isoformat()}
        points = {start+timedelta(hours=i): {'value': 100} for i in range(56*24)}
        def predictions(source, at, params):
            return [{'valid_at': (at+timedelta(hours=h)).isoformat(), 'issued_at': at.isoformat(),
                     'hours_ahead': h, 'value': 100, 'comparisons': {'arithmetic': 100, 'weekly': 100, 'persistence': 100},
                     'parameters': params} for h in (1, 2, 3)]
        points.update({start+timedelta(hours=i): {'value': 100} for i in range(56*24, 70*24)})
        with patch('places.services.hourly_evaluation.samples', return_value=points), \
             patch('places.services.hourly_evaluation.dataset', return_value=({}, {})), \
             patch('places.services.hourly_evaluation.predict', side_effect=predictions), \
             patch('places.services.hourly_evaluation.calendar', return_value={}), \
             patch('places.services.hourly_evaluation.timezone.now', return_value=NOW+timedelta(minutes=5)):
            result = select_parameters(self.study, NOW)
        self.assertEqual(result['status'], 'FROZEN')
        self.assertEqual(dt(result['holdout_start']), NOW+timedelta(hours=1))
        self.assertTrue(self.study.state['late_selection'])
        self.assertEqual(select_parameters(self.study, NOW)['status'], 'FROZEN')
        self.assertIsNone(self.study.state['parameters']['tau'])
