from copy import deepcopy
from datetime import timedelta
from unittest import TestCase

from places.test_crowd_estimator import NOW, inputs
from places.services.crowd_estimator import estimate, weather_effect


class WeatherQualityTests(TestCase):
    def weather(self, **values):
        return {'issued_at': NOW, 'valid_at': NOW, 'product': 'getUltraSrtNcst',
                'values': {'temperature': 28, 'precipitation_type': 0, 'wind_speed': 0, 'sky': 1, **values}}

    def test_clear_sky_is_not_sunlight_or_positive_demand(self):
        for hour in (12, 23):
            data = inputs(); data['profile'] = 'beach'
            at = NOW.replace(hour=hour)
            baseline = estimate(data, at)[0]['crowd_score']
            data['weather'] = self.weather()
            data['weather'].update(issued_at=at, valid_at=at)
            self.assertEqual(estimate(data, at)[0]['crowd_score'], baseline)
        self.assertEqual(weather_effect('beach', 'outdoor', self.weather(precipitation_type=1)['values']), (-.9, 1))

    def test_missing_and_invalid_outdoor_components_are_not_zero(self):
        for key in ('temperature', 'precipitation_type', 'wind_speed'):
            for value in (None, float('nan'), float('inf'), '0', True):
                values = self.weather()['values']; values[key] = value
                self.assertEqual(weather_effect('park', 'outdoor', values), (0, 0))
            values = self.weather()['values']; del values[key]
            self.assertEqual(weather_effect('park', 'outdoor', values), (0, 0))
        values = self.weather()['values']; del values['wind_speed']
        self.assertEqual(weather_effect('shopping', 'indoor', values), (0, 1))

    def test_missing_wind_is_explained_and_lowers_confidence(self):
        data = inputs(); data['weather'] = self.weather(precipitation_type=1)
        full = estimate(data, NOW)[0]
        del data['weather']['values']['wind_speed']
        partial = estimate(data, NOW)[0]
        factor = next(f for f in partial['factors'] if f['key'] == 'weather')
        self.assertFalse(factor['available'])
        self.assertEqual(factor['unavailable_reason'], 'WEATHER_COMPONENT_MISSING')
        self.assertLess(partial['confidence'], full['confidence'])

    def test_current_weather_requires_source_and_target_times(self):
        for change in ({'valid_at': NOW+timedelta(hours=1)}, {'issued_at': NOW+timedelta(minutes=1)},
                       {'valid_at': NOW-timedelta(hours=4)}, {'valid_at': None}):
            data = inputs(); data['weather'] = self.weather(); data['weather'].update(change)
            self.assertFalse(next(f for f in estimate(data, NOW)[0]['factors'] if f['key'] == 'weather')['available'])

    def test_forecast_requires_exact_target_hour_and_not_observation(self):
        data = inputs(); data['weather'] = self.weather()
        row = self.weather(); row.update(product='getUltraSrtFcst', valid_at=NOW+timedelta(hours=1))
        data['forecast_weather'] = {1: row}
        self.assertTrue(estimate(data, NOW)[0]['forecast'][0]['weather_available'])
        for changes in ({'valid_at': NOW+timedelta(hours=2)}, {'product': 'getUltraSrtNcst'}, {'valid_at': None}):
            invalid = deepcopy(data); invalid['forecast_weather'][1].update(changes)
            self.assertFalse(estimate(invalid, NOW)[0]['forecast'][0]['weather_available'])
