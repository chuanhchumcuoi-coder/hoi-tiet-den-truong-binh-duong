import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app as m

class OpenMeteoOnlyTests(unittest.TestCase):
    def setUp(self):
        m.WEATHER_CACHE.clear()
        m.LAST_GOOD_WEATHER.clear()

    @staticmethod
    def payload():
        return {
            "latitude":11.0,"longitude":106.7,"timezone":"Asia/Ho_Chi_Minh",
            "current":{"time":"2026-10-10T16:15", "temperature_2m":32.0,
                       "apparent_temperature":37.5,"relative_humidity_2m":72,
                       "precipitation":0.0,"rain":0.0,"weather_code":1,
                       "wind_speed_10m":10.0,"wind_direction_10m":90,"is_day":1},
            "hourly":{"time":["2026-10-10T16:00","2026-10-10T17:00","2026-10-10T18:00"],
                      "temperature_2m":[32,32,31], "apparent_temperature":[37,38,36],
                      "relative_humidity_2m":[72,75,78],"precipitation_probability":[30,55,45],
                      "precipitation":[0,0.1,0.2],"weather_code":[1,2,3],
                      "wind_speed_10m":[10,12,9],"is_day":[1,1,0]}}

    def test_single_provider_and_health(self):
        with m.app.test_client() as c:
            health=c.get('/api/health').get_json()
            self.assertEqual(health['weather_provider'],'Open-Meteo')
            self.assertEqual(c.get('/api/national-weather').status_code,404)

    def test_only_open_meteo_is_called(self):
        slot=m.current_weather_slot()
        with patch.object(m,'open_meteo_batch_request',return_value=[self.payload()]) as getter:
            results, flags, errors, _=m.resolve_weather_targets({'student':(11,106.7)},slot)
            self.assertEqual(getter.call_count,1)
            self.assertFalse(errors)
            self.assertEqual(results['student']['provider']['name'],'Open-Meteo')
            self.assertFalse(results['student']['stale'])

    def test_cache_if_api_temporarily_unavailable(self):
        slot=m.current_weather_slot()
        with patch.object(m,'open_meteo_batch_request',return_value=[self.payload()]):
            m.resolve_weather_targets({'student':(11,106.7)},slot)
        next_slot=slot+timedelta(minutes=5)
        with patch.object(m,'open_meteo_batch_request',side_effect=m.WeatherProviderError('Open-Meteo','Không kết nối','demo')):
            results, _, errors, _=m.resolve_weather_targets({'student':(11,106.7)},next_slot)
            self.assertFalse(errors)
            self.assertTrue(results['student']['stale'])
            self.assertEqual(results['student']['provider']['name'],'Open-Meteo')

    def test_batch_failure_retries_each_location_independently(self):
        slot=m.current_weather_slot()
        def response(points):
            if len(points) > 1:
                raise m.WeatherProviderError('Open-Meteo','batch lỗi','demo')
            if points[0][0] == 11.1:
                raise m.WeatherProviderError('Open-Meteo','điểm này lỗi','demo')
            return [self.payload()]
        with patch.object(m,'open_meteo_batch_request',side_effect=response):
            results, _, errors, _=m.resolve_weather_targets(
                {'student':(11.0,106.7),'school':(11.1,106.6)},slot)
        self.assertIn('student',results)
        self.assertNotIn('student',errors)
        self.assertNotIn('school',results)
        self.assertIn('school',errors)

    def test_no_fabricated_fallback(self):
        slot=m.current_weather_slot()
        with patch.object(m,'open_meteo_batch_request',side_effect=m.WeatherProviderError('Open-Meteo','Không kết nối','demo')):
            results, _, errors, _=m.resolve_weather_targets({'school':(11.1,106.6)},slot)
            self.assertFalse(results)
            self.assertIn('school',errors)

if __name__=='__main__': unittest.main()
