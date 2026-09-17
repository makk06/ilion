import copy
import math
from datetime import datetime, timedelta
from unittest import TestCase
from .services.mean_forecast import KST, predict, population, hourly, weather, events


NOW = datetime(2026, 9, 13, 12, tzinfo=KST)


def observation(at, value=100, **extra):
    return {'at': at.isoformat(), 'received_at': at.isoformat(), 'min': value, 'max': value, **extra}


def fixture():
    rows = []
    for d in range(1, 85):
        for hour in range(24):
            rows.append(observation((NOW-timedelta(days=d)).replace(hour=hour)))
    for m in (0, 5, 10, 15):
        rows.append(observation(NOW-timedelta(minutes=m), 130))
    return {'area_id': 1, 'population': rows, 'weather': [], 'calendar': [], 'event_checks': []}


class MeanForecastTests(TestCase):
    def test_hand_calculated_correction(self):
        result = predict(fixture(), NOW, {'weather': False, 'events': False})
        for h, row in enumerate(result, 1):
            self.assertAlmostEqual(row['population'], 100+30*math.exp(-h/1.5))
            self.assertEqual(row['base'], 100)

    def test_no_correction_is_weighted_mean(self):
        self.assertEqual(predict(fixture(), NOW, {'tau': None})[0]['population'], 100)

    def test_zero_preserved(self):
        data = fixture()
        for r in data['population']:
            r['min'] = r['max'] = 0
        self.assertEqual(predict(data, NOW)[0]['population'], 0)

    def test_insufficient_history_is_null(self):
        row = predict({'area_id': 1}, NOW)[0]
        self.assertIsNone(row['population'])
        self.assertIn('insufficient_history', row['reasons'])

    def test_future_observation_does_not_change_prediction(self):
        data = fixture()
        expected = predict(data, NOW)
        data['population'] += [observation(NOW+timedelta(minutes=1), 100000),
            observation(NOW-timedelta(days=7), 100000, received_at=(NOW+timedelta(seconds=1)).isoformat())]
        self.assertEqual(expected, predict(data, NOW))

    def test_input_not_mutated(self):
        data = fixture()
        before = copy.deepcopy(data)
        predict(data, NOW)
        self.assertEqual(before, data)

    def test_invalid_population_excluded(self):
        rows = [observation(NOW, 0), observation(NOW, 100), observation(NOW-timedelta(minutes=1), -1),
            observation(NOW-timedelta(minutes=2), float('nan')), observation(NOW-timedelta(minutes=3), 1, max=0),
            observation(NOW-timedelta(minutes=4), 1, demo=True), observation(NOW-timedelta(minutes=5), 1, replaced=True)]
        self.assertEqual([r['value'] for r in population(rows, NOW)], [0])

    def test_first_hour_observation_and_boundary(self):
        rows = population([observation(NOW+timedelta(minutes=6), 200),
                           observation(NOW+timedelta(minutes=5), 100), observation(NOW+timedelta(minutes=3), 90)], NOW+timedelta(hours=1))
        self.assertEqual(hourly(rows)[0]['value'], 90)

    def test_stale_current_skips_correction(self):
        data = fixture()
        data['population'] = [r for r in data['population'] if r['at'] < (NOW-timedelta(minutes=16)).isoformat()]
        self.assertEqual(predict(data, NOW)[0]['correction'], 0)

    def test_duplicate_does_not_increase_days(self):
        data = fixture()
        expected = predict(data, NOW)
        data['population'] *= 2
        self.assertEqual(expected, predict(data, NOW))

    def test_weather_versions_as_of(self):
        target = NOW+timedelta(hours=1)
        row = {'at': target.isoformat(), 'issued_at': NOW.isoformat(), 'received_at': NOW.isoformat(),
               'product': 'getUltraSrtFcst', 'temperature': 20, 'precipitation_type': 1}
        data = {'weather': [row, {**row, 'temperature': 40, 'issued_at': (NOW+timedelta(minutes=1)).isoformat()}]}
        self.assertEqual(weather(data, target, NOW, True), (20, 'rain'))

    def test_events_unknown_and_confirmed_absent(self):
        self.assertIsNone(events({}, NOW, NOW)[0])
        data = {'event_checks': [{'start_date': NOW.date().isoformat(), 'end_date': NOW.date().isoformat(),
                                 'received_at': NOW.isoformat(), 'events': []}]}
        self.assertEqual(events(data, NOW, NOW)[0], [])

    def test_new_event_falls_back(self):
        data = fixture()
        data['event_checks'] = [{'start_date': '2026-09-13', 'end_date': '2026-09-13',
            'received_at': NOW.isoformat(), 'events': [{'family': 'new', 'edition': '2026',
                'start_date': '2026-09-13', 'end_date': '2026-09-13'}]}]
        row = predict(data, NOW)[0]
        self.assertIn('event_unmodeled', row['reasons'])
        self.assertIn('event_time_unknown', row['reasons'])

    def test_later_event_revision_does_not_change_past(self):
        data = fixture()
        expected = predict(data, NOW)
        data['event_checks'] = [{'start_date': '2026-09-13', 'end_date': '2026-09-13',
                                 'received_at': (NOW+timedelta(seconds=1)).isoformat(), 'events': []}]
        self.assertEqual(expected, predict(data, NOW))

    def test_non_hour_and_naive_rejected(self):
        for now in (NOW.replace(tzinfo=None), NOW+timedelta(seconds=1)):
            with self.assertRaises(ValueError):
                predict(fixture(), now)

    def test_midnight_month_boundary(self):
        row = predict(fixture(), datetime(2026, 9, 30, 23, tzinfo=KST))[0]
        self.assertEqual(row['valid_at'], '2026-10-01T00:00:00+09:00')

    def test_weather_conditional_mean_by_hand(self):
        data = fixture()
        for row in data['population']:
            at = datetime.fromisoformat(row['at'])
            if at.date() < NOW.date():
                value = 200 if at.day % 2 else 100
                row['min'] = row['max'] = value
                data['weather'].append({'at': at.isoformat(), 'issued_at': at.isoformat(), 'received_at': at.isoformat(),
                    'product': 'getUltraSrtNcst', 'temperature': 20, 'precipitation_type': 1 if at.day % 2 else 0})
        target = NOW+timedelta(hours=1)
        data['weather'].append({'at': target.isoformat(), 'issued_at': NOW.isoformat(), 'received_at': NOW.isoformat(),
            'product': 'getUltraSrtFcst', 'temperature': 20, 'precipitation_type': 1})
        row = predict(data, NOW, {'tau': None, 'events': False})[0]
        self.assertGreater(row['conditional'], row['base'])
        self.assertAlmostEqual(row['population'], (1-row['alpha'])*row['base']+row['alpha']*row['conditional'])

    def test_same_event_edition_counts_once(self):
        data = fixture()
        data['event_checks'] = [{'start_date': '2026-06-01', 'end_date': '2026-09-30',
            'received_at': '2026-06-01T00:00:00+09:00', 'events': [{'family': 'festival', 'edition': 'one',
                'start_date': '2026-06-01', 'end_date': '2026-09-30'}]}]
        row = predict(data, NOW, {'weather': False})[0]
        self.assertEqual(row['event_editions'], 1)
        self.assertAlmostEqual(row['alpha'], 1/9)

    def test_multiple_events_do_not_multiply_effect(self):
        data = fixture()
        data['event_checks'] = [{'start_date': '2026-09-13', 'end_date': '2026-09-13',
            'received_at': NOW.isoformat(), 'events': [
                {'family': name, 'edition': name, 'start_date': '2026-09-13', 'end_date': '2026-09-13'}
                for name in ('a', 'b')]}]
        row = predict(data, NOW)[0]
        self.assertIn('multiple_events', row['reasons'])
        self.assertEqual(row['alpha'], 0)

    def test_negative_corrected_population_clamped(self):
        data = fixture()
        for row in data['population']:
            at = datetime.fromisoformat(row['at'])
            value = 0 if at.date() == NOW.date() else (1000 if at.hour <= 12 else 10)
            row['min'] = row['max'] = value
        self.assertEqual(predict(data, NOW)[0]['population'], 0)

    def test_day_group_fallback(self):
        data = fixture()
        data['population'] = [r for r in data['population'] if datetime.fromisoformat(r['at']) >= NOW-timedelta(days=30)]
        self.assertEqual(predict(data, NOW)[0]['fallback'], 'day_group')

    def test_missing_calendar_not_silently_confirmed(self):
        self.assertIn('calendar_unknown', predict(fixture(), NOW)[0]['reasons'])
