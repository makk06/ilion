"""Replay captured live inputs into an isolated SQLite copy; never call providers."""
import json
import os
from pathlib import Path
import sqlite3
import sys
from datetime import datetime, timedelta
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
DIR=ROOT/'.integration-artifacts/crowd-validation'
source=ROOT/'tourist_congestion_backend/db.sqlite3'
target=DIR/'replay.sqlite3'
if target.exists():
    raise SystemExit('Refusing to overwrite existing replay database')
assert target.resolve().parent==DIR.resolve() and target.resolve()!=source.resolve()
with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as original, sqlite3.connect(target) as replay:
    original.backup(replay)
os.environ['DJANGO_DB_PATH']=str(target)
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
sys.path.insert(0,str(ROOT/'tourist_congestion_backend'))
import django
django.setup()
from django.conf import settings
assert Path(settings.DATABASES['default']['NAME']).resolve()==target.resolve()
from django.test import Client, override_settings
from places.models import (Place,PlaceSource,PlaceCrowdArea,CrowdArea,CrowdData,CrowdEstimate,
    TransitObservation,WeatherSnapshot,TourEvent,CalendarDay,HistoricalBaseline,CollectorState)
from places.integrations.seoul_realtime import SeoulPopulationRecord
from places.services.input_sync import save_weather,save_calendar,save_event,save_citydata
from places.services.place_resolver import resolve_places
from places.services.crowd_inputs import load_inputs,estimates_for

kto=json.loads((DIR/'kto.json').read_text(encoding='utf-8'))
weather=json.loads((DIR/'weather.json').read_text(encoding='utf-8'))
seoul=json.loads((DIR/'seoul.json').read_text(encoding='utf-8'))
stamp=datetime.fromisoformat
now=max([stamp(weather.get('extended_at',weather['checked_at'])),stamp(kto['finished_at'])]+[stamp(r['fetched_at']) for r in seoul['observations']])+timedelta(seconds=1)
report={'kind':'isolated_live_capture_replay_not_accuracy_evaluation','replayed_at':now.isoformat(),
        'database':str(target),'production_database_access':'SQLite read-only backup source; all ORM writes isolated',
        'event_coverage':.5,'external_http_attempts':0,'places':[],'checks':[]}

with patch('requests.Session.request',side_effect=AssertionError('External HTTP forbidden in replay')) as network, patch('django.utils.timezone.now',return_value=now), override_settings(ALLOWED_HOSTS=['testserver'],CROWD_ESTIMATION_ENABLED=True):
    # The isolated copy contains only captured evidence for this replay, no old snapshots/history.
    for model in (CrowdEstimate,HistoricalBaseline,CrowdData,TransitObservation,WeatherSnapshot,TourEvent,CalendarDay):
        model.objects.all().delete()
    places=[]
    for label,row in kto['selected'].items():
        src=PlaceSource.objects.filter(source='tour_api',external_id=row['contentid']).first()
        place=src.place if src and src.place_id else Place.objects.filter(name=row['title']).first()
        if place is None:
            place=Place.objects.create(name=row['title'],category='관광지',region_code=row.get('lDongRegnCd',''),address=row.get('addr1',''),latitude=row['latitude'],longitude=row['longitude'])
        else:
            place.name=row['title'];place.latitude=row['latitude'];place.longitude=row['longitude'];place.address=row.get('addr1','');place.save()
        PlaceSource.objects.update_or_create(source='tour_api',external_id=row['contentid'],defaults={'place':place,'source_name':row['title'],'source_category':row['contenttypeid'],
            'source_latitude':row['latitude'],'source_longitude':row['longitude'],'source_address':row.get('addr1',''),'match_status':'matched','raw_data':{**row,'showflag':'1'},'last_synced_at':stamp(row['fetched_at'])})
        places.append(place)
    preserved=list(PlaceCrowdArea.objects.filter(place__in=places,verified=True,match_method__in=('manual','source')).values('id','place_id','crowd_area_id'))
    resolve_places(places)
    report['preserved_manual_mappings']=preserved
    for p in weather['places']:
        for product in p['products']:
            if product['status']!='passed':continue
            save_weather(tuple(p['grid']),product['product'],stamp(product['issued_at']),{stamp(r['valid_at']):r['values'] for r in product['data']},stamp(product.get('fetched_at',weather['checked_at'])))
    calendar=weather['calendar']
    save_calendar(calendar['year'],calendar['month'],{datetime.fromisoformat(day).date():name for day,name in calendar['holidays'].items()},stamp(weather['checked_at']))
    saved_events=sum(save_event(row,stamp(row['fetched_at'])) for row in kto['events']['items'])
    CollectorState.objects.update_or_create(provider='tour_api',key='events',defaults={'last_success_at':max(stamp(r['fetched_at']) for r in kto['events']['items']),'cursor':{'coverage':.5}})
    for row in sorted(seoul['observations'],key=lambda r:r['fetched_at']):
        if row['status']!='success':continue
        area=CrowdArea.objects.get(source='seoul_realtime',external_id=row['external_id'])
        p=row['population'];pop=None
        if p:
            pop=SeoulPopulationRecord(external_id=row['external_id'],name=row['name'],observed_at=stamp(p['observed_at']),crowd_level=p['crowd_level'],crowd_message='',population_min=p['population_min'],population_max=p['population_max'],is_replaced=p['is_replaced'],raw_data={'AREA_CD':row['external_id'],'AREA_NM':row['name'],'PPLTN_TIME':p['observed_at'],'AREA_CONGEST_LVL':p['provider_category'],'REPLACE_YN':'Y' if p['is_replaced'] else 'N'})
        transit=[{**r,'observed_at':stamp(r['observed_at'])} for r in row['transit']]
        save_citydata(area,pop,transit,stamp(row['fetched_at']))
    inputs=load_inputs(places,now)
    calculated=estimates_for(places,now)
    client=Client()
    for label,p in zip(kto['selected'],places):
        response=client.get(f'/api/places/{p.pk}/crowd')
        assert response.status_code==200,(label,response.status_code)
        payload=response.json();assert payload['success']
        data=payload['data'];assert data['status']=='available' and len(data['forecast'])==3
        assert data['crowd_level'] in ('VERY_LOW','LOW','NORMAL','HIGH','VERY_HIGH') and data['estimated_visitors'] is None
        assert data['crowd_score']==calculated[p.pk]['crowd_score']
        detail=client.get(f'/api/places/{p.pk}')
        assert detail.status_code==200 and detail.json()['data']['crowd_estimate']['crowd_level']==data['crowd_level']
        report['places'].append({'label':label,'place_id':p.pk,'grid':next(r['grid'] for r in weather['kto_grid_matches'] if r['label']==label),
            'mapping':inputs[p.pk]['mapping'],'current_weather':inputs[p.pk]['weather'] is not None,'forecast_weather_hours':list(inputs[p.pk]['forecast_weather']),
            'crowd':data})
    for level in ('VERY_LOW','LOW','NORMAL','HIGH','VERY_HIGH'):
        response=client.get('/api/places',{'estimate_level':level,'page_size':100})
        assert response.status_code==200
        assert all(r['crowd_estimate']['crowd_level']==level for r in response.json()['data']['items'])
    assert client.get('/api/places',{'estimate_level':'LOW','crowd_level':'relaxed'}).status_code==400
    assert client.get('/api/places',{'estimate_level':'INVALID'}).status_code==400
    assert client.get('/api/places/999999999/crowd').status_code==404
    report['checks']=['six crowd endpoints 200, available, five-level, three forecasts','six detail summaries equal computed level','five level filters enforce requested level','mixed legacy/new filter 400','invalid new filter 400','missing place 404','zero external requests']
    report['external_http_attempts']=network.call_count
    assert network.call_count==0
    report['stored_counts']={'events':saved_events,'weather':WeatherSnapshot.objects.count(),'population':CrowdData.objects.count(),'transit':TransitObservation.objects.count(),'calendar':CalendarDay.objects.count()}
report['status']='passed'
(DIR/'replay_pipeline.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':report['status'],'external_http_attempts':report['external_http_attempts'],'stored_counts':report['stored_counts'],'places':[{'label':p['label'],'mapping':p['mapping'],'score':p['crowd']['crowd_score'],'tier':p['crowd']['tier']} for p in report['places']]},ensure_ascii=True))
