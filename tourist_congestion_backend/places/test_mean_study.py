from datetime import timedelta
from io import StringIO
from unittest.mock import patch
from django.test import TestCase
from django.core.management import call_command, CommandError
from places.models import CrowdArea, CrowdData, MeanEvidence, MeanStudy, MeanPrediction
from .services.mean_archive import append
from .services.mean_study import tick, adapter, label, validation_rows
from .services.mean_validation import assess
from .test_mean_forecast import NOW, fixture, observation


class MeanStudyTests(TestCase):
    def setUp(self):
        self.area = CrowdArea.objects.create(source='seoul_realtime', external_id='test-mean', name='Mean area', last_synced_at=NOW)

    def test_signal_archives_and_legacy_delete_keeps_evidence(self):
        row = CrowdData.objects.create(crowd_area=self.area, observed_at=NOW, fetched_at=NOW, population_min=0, population_max=100)
        row.delete()
        self.assertEqual(MeanEvidence.objects.filter(kind='population').count(), 1)

    def test_archive_duplicate_idempotent(self):
        row = observation(NOW)
        append('population', self.area.pk, NOW, row)
        append('population', self.area.pk, NOW, row)
        self.assertEqual(MeanEvidence.objects.count(), 1)

    def test_shadow_inputs_frozen_and_labels_independent(self):
        study = MeanStudy.objects.create(started_at=NOW-timedelta(days=100), config={'grids': {str(self.area.pk): '60,127'}},
            state={'areas': [self.area.pk], 'selection_complete': True})
        for row in fixture()['population']:
            append('population', self.area.pk, NOW-timedelta(seconds=1), row)
        result = tick(NOW)
        self.assertEqual(result['issued'], 3)
        before = list(MeanPrediction.objects.values_list('payload', flat=True))
        from .services.mean_study import reproduce
        first = MeanPrediction.objects.order_by('valid_at').first()
        self.assertEqual(reproduce(first)[0]['population'], first.payload['population'])
        self.assertEqual(tick(NOW)['issued'], 0)
        target = NOW+timedelta(hours=1)
        append('population', self.area.pk, target, observation(target, 300))
        tick(target+timedelta(minutes=2))
        self.assertEqual(before, list(MeanPrediction.objects.filter(issued_at=NOW).values_list('payload', flat=True)))
        self.assertEqual(MeanPrediction.objects.get(valid_at=target).actual, 300)

    def test_late_tick_does_not_backdate_forecast(self):
        MeanStudy.objects.create(started_at=NOW, config={}, state={'selection_complete': True, 'areas': []})
        self.assertEqual(tick(NOW+timedelta(minutes=5))['status'], 'awaiting_next_hour')
        self.assertEqual(MeanPrediction.objects.count(), 0)

    def test_promotion_denied_without_validation(self):
        MeanStudy.objects.create(started_at=NOW, config={})
        with self.assertRaises(CommandError):
            call_command('mean_crowd', 'promote', stdout=StringIO())

    def test_unapproved_adapter_preserves_payload(self):
        payload = {'forecast': [{'old': True}]}
        self.assertEqual(adapter(payload, self.area.pk, NOW), payload)

    def test_missing_future_label_is_not_zero(self):
        self.assertIsNone(label({'population': []}, NOW, NOW+timedelta(days=1)))

    def test_small_dataset_cannot_pass(self):
        self.assertEqual(assess([], [1, 2, 3], {'1': 1, '2': 1, '3': 1}, {})['status'], 'NEEDS_MORE_DATA')

    def test_unissued_hours_are_in_coverage_denominator(self):
        study = MeanStudy.objects.create(started_at=NOW, config={}, state={'areas': [self.area.pk]})
        rows = validation_rows(study, NOW, NOW+timedelta(hours=2))
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(r['population'] is None for r in rows))

    def test_adapter_approved_missing_value_stays_null(self):
        MeanStudy.objects.create(started_at=NOW, config={}, state={'areas': [self.area.pk],
            'deployment': 'mean', 'promotion': {'status': 'PASS'}})
        row = adapter({'forecast': []}, self.area.pk, NOW)['forecast'][0]
        self.assertIsNone(row['crowd_score'])
        self.assertEqual(row['scope'], 'area_population')
        self.assertEqual(row['confidence_status'], 'not_calibrated')

    def test_backtest_short_history_reports_waiting(self):
        from .services.mean_replay import run
        study = MeanStudy.objects.create(started_at=NOW, config={}, state={'areas': [1, 2, 3]})
        self.assertEqual(run(study, NOW)['status'], 'NEEDS_MORE_DATA')

    def test_backtest_pass_alone_cannot_promote(self):
        MeanStudy.objects.create(started_at=NOW, config={}, state={'validation': {'status': 'PASS'}})
        with self.assertRaises(CommandError):
            call_command('mean_crowd', 'promote', stdout=StringIO())

    def test_three_consecutive_bad_days_fall_back_once(self):
        from .services.mean_monitor import monitor
        params = {'events': False}
        study = MeanStudy.objects.create(started_at=NOW, config={}, state={
            'areas': [self.area.pk], 'deployment': 'mean', 'parameters': params,
            'promotion': {'scales': {str(self.area.pk): 100}, 'peaks': {str(self.area.pk): 90}}})
        rows = [{'area_id': self.area.pk, 'hours_ahead': h, 'population': 130,
                 'arithmetic': 110, 'actual': 100, 'parameters': params} for h in (1, 2, 3) for _ in range(100)]
        with patch('places.services.mean_monitor.validation_rows', return_value=rows):
            monitor(study, NOW)
            monitor(study, NOW)
            self.assertEqual(study.state['deployment'], 'mean')
            monitor(study, NOW+timedelta(days=1))
            monitor(study, NOW+timedelta(days=2))
        self.assertEqual(study.state['deployment'], 'arithmetic')

    def test_mature_synthetic_gate_and_regression(self):
        rows = []
        for day in range(14):
            for hour in range(8):
                for area in (1, 2, 3):
                    for h in (1, 2, 3):
                        rows.append({'area_id': area, 'hours_ahead': h, 'issued_at': (NOW+timedelta(days=day, hours=hour)).isoformat(),
                            'actual': 100, 'population': 101, 'arithmetic': 110, 'parameters': {'events': False}})
        scales, peaks = {str(a): 100 for a in (1, 2, 3)}, {str(a): 90 for a in (1, 2, 3)}
        self.assertEqual(assess(rows, [1, 2, 3], scales, peaks)['status'], 'PASS')
        for row in rows:
            row['population'] = 120
        self.assertEqual(assess(rows, [1, 2, 3], scales, peaks)['status'], 'FAIL')
