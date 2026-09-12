from datetime import timedelta

from django.test import TestCase
from places.models import CrowdArea, CrowdData, HistoricalBaseline, HistoricalSample
from places.services.crowd_baseline import rebuild_baselines
from places.test_crowd_estimator import NOW


class BaselineTests(TestCase):
    def test_hourly_median_not_twelve_independent_days_and_excludes_samples(self):
        area=CrowdArea.objects.create(source='seoul_realtime',external_id='POI001',name='test',last_synced_at=NOW)
        at=(NOW-timedelta(days=1)).replace(minute=0)
        for i in range(12):
            CrowdData.objects.create(crowd_area=area,observed_at=at+timedelta(minutes=5*i),
                fetched_at=at+timedelta(minutes=5*i),population_min=i*10,population_max=i*10)
        for i,raw in enumerate(({'dev_seed':True},{'is_demo':True})):
            CrowdData.objects.create(crowd_area=area,observed_at=at+timedelta(hours=i+1),
                fetched_at=at,population_min=9000,population_max=9000,raw_data=raw)
        CrowdData.objects.create(crowd_area=area,observed_at=at+timedelta(hours=3),fetched_at=at,
            population_min=9999,population_max=9999,is_replaced=True)
        rebuild_baselines(NOW)
        sample=HistoricalSample.objects.get()
        self.assertEqual(sample.value,55); self.assertEqual(sample.sample_count,12)
        global_row=HistoricalBaseline.objects.get(weekday=-1)
        self.assertEqual(global_row.sample_days,1)
        self.assertEqual(global_row.distribution,[55])
        rebuild_baselines(NOW); self.assertEqual(HistoricalSample.objects.count(),1)
