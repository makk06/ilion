"""Create a NEW disposable SQLite database and measure database-backed HTTP views."""
import argparse
import json
import math
import os
from pathlib import Path
import sys
import time

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--database',required=True)
parser.add_argument('--places',type=int,default=100000)
parser.add_argument('--runs',type=int,default=30)
args=parser.parse_args()
database=Path(args.database).resolve()
if database.exists():
    raise SystemExit('Use a new disposable database path; existing databases are never modified.')
database.parent.mkdir(parents=True,exist_ok=True)
os.environ['DJANGO_DB_PATH']=str(database)
os.environ['DJANGO_SETTINGS_MODULE']='config.settings'
os.environ['DJANGO_ALLOWED_HOSTS']='testserver,localhost,127.0.0.1'
os.environ['DJANGO_DEBUG']='false'
sys.path.insert(0,str(root/'tourist_congestion_backend'))
import django
django.setup()
from django.core.management import call_command
from django.test import Client
from django.utils import timezone
from places.models import Place,PlaceSource,PlaceCrowdArea,CrowdArea,CrowdData,PlaceCrowdProfile
from places.services.place_resolver import import_geometry

call_command('migrate',verbosity=0)
import_geometry()
now=timezone.now()
for offset in range(0,args.places,1000):
    batch=Place.objects.bulk_create([Place(name=f'측정 관광지 {i:06}',latitude=37.55+(i%100)*.0001,
        longitude=126.95+(i%100)*.0001,category='관광지',region_code='11',address='서울 측정 데이터')
        for i in range(offset,min(offset+1000,args.places))])
    PlaceSource.objects.bulk_create([PlaceSource(place=p,source='tour_api',external_id=f'benchmark-{p.pk}',
        match_status='matched',last_synced_at=now,raw_data={'is_demo':True,'contenttypeid':'12'}) for p in batch])
areas=list(CrowdArea.objects.order_by('id'))
for i,p in enumerate(Place.objects.order_by('id')[:1000]):
    PlaceCrowdArea.objects.create(place=p,crowd_area=areas[i%121],verified=True,is_primary=True)
    PlaceCrowdProfile.objects.create(place=p,profile='day_visit',grid_x=60,grid_y=127)
CrowdData.objects.bulk_create([CrowdData(crowd_area=a,observed_at=now,fetched_at=now,population_min=1000,
    population_max=2000,crowd_level='normal',raw_data={'is_demo':True}) for a in areas])
client=Client()
report={'places':args.places,'areas':len(areas),'runs':args.runs,'database':'disposable SQLite',
        'mode':'Django test client, warm local process; no network latency or concurrent writers'}
for name,path in [('detail','/api/places/1/crowd'),('list','/api/places?page_size=20')]:
    times=[]
    for _ in range(args.runs+1):
        started=time.perf_counter(); response=client.get(path); elapsed=(time.perf_counter()-started)*1000
        if response.status_code!=200: raise SystemExit(f'{name}: HTTP {response.status_code}')
        times.append(elapsed)
    times=sorted(times[1:])
    report[name]={'p50_ms':round(times[len(times)//2],2),'p95_ms':round(times[math.ceil(.95*len(times))-1],2)}
print(json.dumps(report,ensure_ascii=False,indent=2))
