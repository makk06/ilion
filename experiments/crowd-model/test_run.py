"""Contract tests; synthetic target changes never enter real evaluation metrics."""
import unittest
import math
from copy import deepcopy

import run


class ExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.manifest = run.audit()
        cls.folds = list(run.splits(cls.rows))

    def test_frozen_dataset(self):
        self.assertEqual(len(self.rows), 20)
        self.assertEqual(self.manifest['forward_pairs'], 0)
        self.assertEqual(self.manifest['classes'], {'relaxed': 20})
        self.assertEqual(len({r['id'] for r in self.rows}), 20)

    def test_splits(self):
        self.assertEqual(len(self.folds), 10)
        for name, train, test in self.folds:
            self.assertFalse({r['id'] for r in train} & {r['id'] for r in test})
            if name.startswith(('time_', 'joint_')):
                self.assertLess(max(r['t'] for r in train), min(r['t'] for r in test))
            if name.startswith(('area_', 'joint_')):
                self.assertFalse({r['area'] for r in train} & {r['area'] for r in test})

    def test_evaluation_target_cannot_change_fitted_state(self):
        # Mutate the original combined dataset, re-split and refit, not just predict twice.
        for split, train, test in self.folds:
            ids = {r['id'] for r in test}
            changed = [dict(r, y=1234567.) if r['id'] in ids else deepcopy(r) for r in self.rows]
            _, retrain, retest = next(f for f in run.splits(changed) if f[0] == split)
            for name in run.MODELS:
                a, b = run.Model(name, train), run.Model(name, retrain)
                self.assertEqual(run.encode(a.state()), run.encode(b.state()))
                self.assertEqual([a.predict(run.features(r)) for r in test],
                                 [b.predict(run.features(r)) for r in retest])

    def test_prediction_boundary_rejects_target(self):
        _, train, test = self.folds[0]
        with self.assertRaises(AssertionError):
            run.Model('ridge', train).predict(test[0])

    def test_preview_regression(self):
        expected = {'mean': 1.460666, 'area_median': .111479, 'persistence': .104125,
                    'ridge': .090526, 'hybrid_a': .088075, 'stump': .464862}
        _, train, test = self.folds[1]
        for name, value in expected.items():
            model = run.Model(name, train)
            self.assertAlmostEqual(run.metrics(test, [model.predict(run.features(r)) for r in test])['log_mae'], value, places=6)

    def test_guards_and_unused_inputs(self):
        _, train, test = self.folds[1]
        for name in run.MODELS:
            model = run.Model(name, train)
            row = run.features(test[0])
            for scenario in ('no_history', 'baseline_only'):
                self.assertEqual(model.predict(row, scenario), model.mean)
            self.assertEqual(model.predict(dict(row, t=None)), model.mean)
            for scenario in ('no_transit', 'no_event', 'no_weather'):
                self.assertEqual(model.predict(row, scenario), model.predict(row))
            if name not in ('hierarchy', 'hour'):
                self.assertEqual(model.predict(dict(row, area='UNSEEN')), model.mean)

    def test_no_sequential_test_update(self):
        _, train, test = self.folds[1]
        for name in run.MODELS:
            model = run.Model(name, train)
            state = run.encode(model.state())
            forward = [model.predict(run.features(r)) for r in test]
            reverse = [model.predict(run.features(r)) for r in reversed(test)]
            self.assertEqual(forward, list(reversed(reverse)))
            self.assertEqual(forward[::2], [model.predict(run.features(r)) for r in test[::2]])
            self.assertEqual(state, run.encode(model.state()))

    def test_constant_truth_r2_null(self):
        rows = [{'y': 3., 'area': 'synthetic'}]*2
        self.assertIsNone(run.metrics(rows, [3., 3.])['r2'])

    def test_hand_calculated_models(self):
        # log1p targets 1 and 3: centered slope numerator=1, denominator=.5+1.
        rows = [dict(area='A', category='C', hour='0:12', t=t, y=math.expm1(z))
                for t, z in ((0., 1.), (1., 3.))]
        target = dict(area='A', category='C', hour='0:12', t=2.)
        expected_mean = (math.expm1(1)+math.expm1(3))/2
        for name in ('mean', 'hour', 'area_median', 'hierarchy'):
            self.assertAlmostEqual(run.Model(name, rows).predict(target), expected_mean)
        # Ridge intercept = 2 - (2/3)*.5 = 5/3, prediction at t=2 is log=3.
        self.assertAlmostEqual(run.Model('ridge', rows).predict(target), math.expm1(3))
        # Hybrid A rate=(1*2)/(1+1)=1; last log=3, one extra unit => log=4.
        self.assertAlmostEqual(run.Model('hybrid_a', rows).predict(target), math.expm1(4))

    def test_hand_calculated_stump_and_median(self):
        rows = [dict(area=a, category='C', hour='0:12', t=t, y=math.expm1(z))
                for a, t, z in [('A', 0., 1.), ('A', 1., 1.), ('B', 0., 3.), ('B', 1., 3.)]]
        stump = run.Model('stump', rows)
        for area, z in [('A', 1.), ('B', 3.)]:
            self.assertAlmostEqual(stump.predict(dict(area=area, category='C', hour='0:12', t=2.)), math.expm1(z))
        rows = [dict(area='A', category='C', hour='0:12', t=float(i), y=y) for i, y in enumerate([2., 4., 100.])]
        self.assertEqual(run.Model('area_median', rows).predict(dict(area='A', category='C', hour='0:12', t=3.)), 4.)

    def test_unseen_category_and_training_dictionary(self):
        _, train, test = self.folds[1]
        for name in run.MODELS:
            model = run.Model(name, train)
            target = dict(run.features(test[0]), area='NEW_AREA', category='NEW_CATEGORY')
            self.assertNotIn('NEW_AREA', model.ids)
            self.assertNotIn('NEW_CATEGORY', model.categories)
            expected = model.hour_median[target['hour']] if name == 'hierarchy' else model.mean
            self.assertAlmostEqual(model.predict(target), expected)


if __name__ == '__main__':
    unittest.main()
