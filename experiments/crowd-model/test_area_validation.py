import unittest
from datetime import datetime, timedelta, timezone

from area_validation import assess


class AreaValidationTests(unittest.TestCase):
    def fixture(self):
        first = datetime(2026, 9, 1, tzinfo=timezone.utc)
        rows = []
        for day in range(7):
            for area in (1, 2):
                for hour in range(8):
                    issued = first+timedelta(days=day, hours=hour)
                    target = issued+timedelta(hours=1)
                    rows.append(dict(scope='area_core', model_version='synthetic-only', input_snapshot={}, hours_ahead=1,
                        issued_at=issued.isoformat(), valid_at=target.isoformat(), status='matched', crowd_area_id=area,
                        actual_observed_at=target.isoformat(), actual_received_at=(target+timedelta(minutes=30)).isoformat(),
                        predicted_score=50., actual_score=50., baseline_score=60., persistence_score=55.))
        return rows, first+timedelta(days=9)

    def test_empty_blocked(self):
        self.assertEqual(assess([], datetime.now(timezone.utc))['status'], 'BLOCKED')

    def test_paired_cluster_interval_and_missing_horizons(self):
        rows, now = self.fixture()
        result = assess(rows, now, iterations=100)
        self.assertEqual(result['status'], 'BLOCKED')  # 2h and 3h absent.
        cohort = result['cohorts'][0]
        self.assertEqual(cohort['status'], 'PASS')
        self.assertEqual(cohort['difference_95_ci']['baseline'], [-10., -10.])
        self.assertEqual(cohort['difference_95_ci']['persistence'], [-5., -5.])
        self.assertEqual(result, assess(rows, now, iterations=100))

    def test_versions_never_pool_to_meet_sample_count(self):
        rows, now = self.fixture()
        for r in rows[:56]:
            r['model_version'] = 'another-version'
        result = assess(rows, now, iterations=100)
        self.assertEqual(len(result['cohorts']), 2)
        self.assertTrue(all(c['status'] == 'BLOCKED' for c in result['cohorts']))

    def test_truth_window_and_late_receipt_not_widened(self):
        rows, now = self.fixture()
        for r in rows[:20]:
            r['actual_received_at'] = (datetime.fromisoformat(r['valid_at'])+timedelta(hours=25)).isoformat()
        result = assess(rows, now, iterations=100)
        self.assertEqual(result['cohorts'][0]['samples'], 92)
        self.assertEqual(result['cohorts'][0]['status'], 'BLOCKED')

    def test_worse_model_fails_without_operational_action(self):
        rows, now = self.fixture()
        for r in rows:
            r['predicted_score'] = 80.
        result = assess(rows, now, iterations=100)
        self.assertEqual(result['cohorts'][0]['status'], 'FAIL')
        self.assertFalse(result['changes_production'])
