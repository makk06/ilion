from datetime import timedelta
from types import SimpleNamespace
from django.test import SimpleTestCase
from places.services.hourly_decisions import (CONTRACT, annotate, assess_decisions, distribution,
                                             percentile, relative_label)
from places.services.hourly_forecast import dt
from places.services.mean_validation import assess
from places.services.hourly_evaluation import require_frozen

NOW = dt('2026-05-01T00:00:00+09:00')


def examples():
    result = []
    for a in (1, 2):
        for i in range(14*24):
            for h in (1, 2, 3):
                # Half relaxed, half peaks. Candidate and baseline order agree with truth.
                busy = i % 2
                actual = 110 if busy else 10
                score = 90 if busy else 10
                result.append({'area_id': a, 'external_id': str(a), 'provider': 'seoul',
                    'metric': 'population_count', 'scope': 'area_population',
                    'issued_at': (NOW+timedelta(hours=i)).isoformat(),
                    'valid_at': (NOW+timedelta(hours=i+h)).isoformat(), 'hours_ahead': h,
                    'population': actual, 'arithmetic': actual+1, 'actual': actual,
                    'decision_contract_version': CONTRACT['version'],
                    'decision_scores': {'population': score+a, 'arithmetic': score+a, 'actual': score+a}})
    return result


class DecisionTests(SimpleTestCase):
    def test_boundaries_zero_ties_and_frozen_distribution(self):
        self.assertEqual(percentile([0, 0, 10, 20], 0), 25)
        self.assertEqual(relative_label(40), '평소보다 한산')
        self.assertEqual(relative_label(65), '평소 수준')
        self.assertEqual(relative_label(85), '평소보다 붐빔')
        source = {'observations': [{'observed_at': NOW-timedelta(hours=1), 'received_at': NOW-timedelta(hours=1), 'value': 0}]}
        before = distribution(source, NOW)
        source['observations'].append({'observed_at': NOW+timedelta(hours=1), 'received_at': NOW+timedelta(hours=1), 'value': 999})
        self.assertEqual(before, distribution(source, NOW))
        row = annotate({'population': 0, 'arithmetic': 0, 'actual': 999}, before)
        self.assertEqual(row['decision_scores']['population'], 50)
        self.assertEqual(row['decision_scores']['actual'], 100)

    def test_relaxed_denominator_is_not_all_forecasts_and_peak_miss_rejects(self):
        rows = examples()
        for r in rows:
            if r['actual'] == 110:
                r['population'] = 90
                r['decision_scores']['population'] = 30
        report = assess_decisions(rows, {'1': 100, '2': 100})
        cell = report['guidance']['cells']['1:1']
        self.assertEqual(cell['false_relaxed']['model']['count'], 336)
        self.assertEqual(cell['false_relaxed']['model']['rate'], .5)
        self.assertEqual(cell['peak_miss']['model']['rate'], 1)
        self.assertEqual(report['guidance']['status'], 'FAIL')

    def test_numeric_pass_does_not_override_peak_misses(self):
        rows = examples()
        for r in rows:
            r.update(population=90, actual=100, arithmetic=120, reference=120, weekly=120, persistence=120)
            if r['decision_scores']['actual'] > 85:
                r['decision_scores']['population'] = 80
        numeric = assess(rows, [1, 2], {'1': 100, '2': 100}, {'1': 100, '2': 100},
                         reference='reference', required_areas=None, date_field='valid_at', strict_coverage=True)
        self.assertEqual(numeric['status'], 'PASS')
        self.assertEqual(assess_decisions(rows, {'1': 100, '2': 100})['guidance']['status'], 'FAIL')

    def test_good_guidance_and_ranking_pass_and_same_target_is_not_duplicated(self):
        rows = examples()
        report = assess_decisions(rows, {'1': 100, '2': 100})
        self.assertEqual(report['guidance']['status'], 'PASS')
        self.assertEqual(report['ranking']['status'], 'PASS')
        again = assess_decisions(rows+rows, {'1': 100, '2': 100})
        self.assertEqual(report['ranking'], again['ranking'])
        single = [r for r in rows if r['area_id'] == 1]
        self.assertEqual(assess_decisions(single, {'1': 100})['ranking']['status'], 'NEEDS_MORE_DATA')

    def test_provider_scope_and_ties_cannot_manufacture_ranking_evidence(self):
        rows = examples()
        for r in rows:
            if r['area_id'] == 2:
                r['scope'] = 'place_density'
        self.assertEqual(assess_decisions(rows, {'1': 100, '2': 100})['ranking']['status'], 'NEEDS_MORE_DATA')
        rows = examples()
        for r in rows:
            r['decision_scores']['actual'] = 50
        result = assess_decisions(rows, {'1': 100, '2': 100})['ranking']
        group = next(iter(result['groups'].values()))
        self.assertGreater(group['actual_ties'], 0)
        self.assertEqual(group['model']['count'], 0)
        self.assertEqual(result['status'], 'NEEDS_MORE_DATA')

    def test_insufficient_and_unversioned_rows_never_pass(self):
        rows = examples()[:3]
        self.assertEqual(assess_decisions(rows, {'1': 100})['guidance']['status'], 'NEEDS_MORE_DATA')
        for r in rows:
            r.pop('decision_contract_version')
        self.assertEqual(assess_decisions(rows, {'1': 100})['ranking']['status'], 'NEEDS_MORE_DATA')

    def test_old_or_changed_decision_contract_cannot_be_used(self):
        for contract in (None, {**CONTRACT, 'false_relaxed_max': .1}):
            study = SimpleNamespace(state={'decision_contract': contract})
            with self.assertRaisesRegex(ValueError, 'Decision contract changed'):
                require_frozen(study)

    def test_population_threshold_cannot_change_relative_decision(self):
        self.assertEqual(relative_label(percentile([100, 200, 300], 100)), '평소보다 매우 한산')
        self.assertEqual(relative_label(percentile([10, 20, 30], 100)), '평소보다 매우 붐빔')
        rows = examples()
        for r in rows:
            r.update(population=9, arithmetic=9, actual=11)
        low = assess_decisions(rows, {'1': 10, '2': 10})
        high = assess_decisions(rows, {'1': 100000, '2': 100000})
        self.assertEqual(low, high)
        self.assertEqual(low['guidance']['status'], 'PASS')
        self.assertEqual(low['guidance']['cells']['1:1']['peak_miss']['model']['errors'], 0)

    def test_relative_busy_boundary_matches_display_and_numeric_gate(self):
        rows = examples()
        for r in rows:
            if r['decision_scores']['actual'] > 85:
                r['decision_scores']['actual'] = 85.01
                r['decision_scores']['population'] = 85
        report = assess_decisions(rows)
        self.assertEqual(report['guidance']['cells']['1:1']['peak_miss']['model']['rate'], 1)
        self.assertEqual(relative_label(85), '평소보다 붐빔')
        self.assertEqual(relative_label(85.01), '평소보다 매우 붐빔')
        from places.services.mean_validation import metrics
        a = metrics(rows, 'population', {'1': 1, '2': 1}, {'1': 100000, '2': 100000}, relative_peak_threshold=85)
        b = metrics(rows, 'population', {'1': 1, '2': 1}, {'1': 0, '2': 0}, relative_peak_threshold=85)
        self.assertEqual(a, b)
        self.assertEqual(a['cells']['1:1']['peak_miss_rate'], 1)
        for r in rows:
            if r['decision_scores']['actual'] > 85:
                r['decision_scores']['actual'] = 85
        self.assertEqual(assess_decisions(rows)['guidance']['cells']['1:1']['peak_miss']['model']['count'], 0)
