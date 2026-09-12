"""Synthetic adversarial checks seeded with normalized live weather, not accuracy tests."""
from copy import deepcopy
from datetime import datetime, timedelta
import json
import math
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tourist_congestion_backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from places.services.crowd_estimator import estimate
from places.services.crowd_confidence import confidence, freshness

DIR = ROOT/'.integration-artifacts/crowd-validation'
live = json.loads((DIR/'weather.json').read_text(encoding='utf-8'))
now = datetime.fromisoformat(live['checked_at'])
weather_place = live['places'][0]
observed = next(r for r in weather_place['products'] if r['product']=='getUltraSrtNcst')
predicted = next(r for r in weather_place['products'] if r['product']=='getUltraSrtFcst')
def normalized(row, item):
    return {'issued_at':datetime.fromisoformat(row['issued_at']), 'valid_at':datetime.fromisoformat(item['valid_at']), 'values':item['values']}
base = {'place_id': -1, 'latitude':37.5796, 'longitude':126.9770, 'profile':'park', 'indoor_outdoor':'outdoor',
        'events':[], 'sources':[], 'calendars':{}, 'mapping':{}, 'baselines':{}, 'distribution':[],
        'weather':normalized(observed, observed['data'][0]), 'forecast_weather':{}}
for h in (1,2,3):
    hour = (now+timedelta(hours=h)).replace(minute=0,second=0,microsecond=0)
    item = next(r for r in predicted['data'] if datetime.fromisoformat(r['valid_at'])==hour)
    base['forecast_weather'][h] = normalized(predicted,item)

def full():
    d=deepcopy(base)
    d.update(mapping={'area_id':-1,'match_quality':1,'representativeness':1},
        population={'value':80,'min':75,'max':85,'observed_at':now,'level':'busy'},
        distribution=list(range(100)),baseline_version='SYNTHETIC_STRESS_ONLY',
        baselines={(day,hour):{'median':50,'sample_days':8,'coverage':1,'context':{}} for day in range(7) for hour in range(24)})
    return d

checks=[]
def add(name, passed, evidence, classification='regression_check'):
    checks.append({'name':name,'passed':bool(passed),'classification':classification,'evidence':evidence})
def calc(d):
    return estimate(d,now)[0]

normal=calc(base)
missing=deepcopy(base); missing['forecast_weather']={}
absent=calc(missing)
add('missing_future_weather_lowers_evidence',all(a['confidence']<=b['confidence'] and not a['weather_available'] for a,b in zip(absent['forecast'],normal['forecast'])),{'present':[r['confidence'] for r in normal['forecast']],'missing':[r['confidence'] for r in absent['forecast']]})
for source in ('population','weather','forecast_weather'):
    confs=[]
    for minutes in (0,10,20,30,60,90,120,180,240,300):
        d=full()
        if source=='population':d['population']['observed_at']=now-timedelta(minutes=minutes)
        elif source=='weather':d['weather']['issued_at']=now-timedelta(minutes=minutes)
        else:
            for w in d['forecast_weather'].values():w['issued_at']=now-timedelta(minutes=minutes)
        r=calc(d)
        confs.append(r['forecast'][0]['confidence'] if source=='forecast_weather' else r['confidence'])
    add(source+'_age_monotonic',all(a>=b for a,b in zip(confs,confs[1:])),{'ages_minutes':[0,10,20,30,60,90,120,180,240,300],'confidence':confs})
for key in ('match_quality','representativeness'):
    confs=[]
    for q in (0,.1,.3,.65,.9,1):
        d=full();d['mapping'][key]=q;confs.append(calc(d)['confidence'])
    add(key+'_monotonic',all(a<=b for a,b in zip(confs,confs[1:])),{'quality':[0,.1,.3,.65,.9,1],'confidence':confs})
for flag in ('is_demo','is_replaced'):
    d=full(); d['distribution']=[]; d['baselines']={}
    if flag=='is_demo':d[flag]=True
    else:d['population'][flag]=True
    r=calc(d)
    add(flag+'_excluded_as_observation',r['estimate_kind']=='prior_based' and not next(f for f in r['factors'] if f['key']=='population')['available'],{'tier':r['tier'],'confidence':r['confidence'],'estimate_kind':r['estimate_kind']})

# Horizon history reliability should use the horizon's sample count and coverage.
d=full()
horizon=(now+timedelta(hours=1))
key=(horizon.weekday(),horizon.hour)
d['baselines'][key].update(sample_days=4,coverage=1)
r=calc(d)
qweather=freshness(d['forecast_weather'][1]['issued_at'],now,'weather')
_,expected_quality=confidence(1,0,0,qweather,(4/8)*1,empirical=True,fresh_population=True)
expected=round(min(r['confidence'],expected_quality)*math.exp(-.12),2)
add('horizon_uses_own_sample_reliability',r['forecast'][0]['confidence']==expected,{'current_samples':8,'current_coverage':1,'future_samples':4,'future_coverage':1,'actual':r['forecast'][0]['confidence'],'expected_using_future_samples':expected},'production_reachable_bug')

# Pure functions assume normalized valid-hour inputs; loader normally guarantees this.
d=deepcopy(base)
for w in d['forecast_weather'].values():w['valid_at']=now-timedelta(days=1)
r=calc(d)
add('wrong_forecast_valid_hour_rejected_by_pure_function',not any(f['weather_available'] for f in r['forecast']),{'weather_available':[f['weather_available'] for f in r['forecast']],'loader_guards_exact_target_hour':True},'defense_in_depth_only')
d=deepcopy(base);d['weather']['valid_at']=now-timedelta(days=1)
r=calc(d)
add('old_observation_valid_hour_rejected_by_pure_function',not next(f for f in r['factors'] if f['key']=='weather')['available'],{'weather_available':next(f for f in r['factors'] if f['key']=='weather')['available'],'normalizer_sets_observation_valid_at_to_issue':True},'invalid_normalized_input_only')
d=deepcopy(base)
for w in d['forecast_weather'].values():w['issued_at']=now-timedelta(hours=4)
r=calc(d)
add('forecast_hard_ttl',not any(f['weather_available'] for f in r['forecast']),{'weather_available':[f['weather_available'] for f in r['forecast']]})

report={'kind':'synthetic_adversarial_checks_not_accuracy_evaluation','live_weather_source_at':live['checked_at'],
        'assumptions':'Population, distributions, mappings, history sample counts and manipulated timestamps are synthetic stress inputs. Weather values originate from live KMA normalization.',
        'checks':checks,'passed':sum(c['passed'] for c in checks),'total':len(checks)}
(DIR/'confidence_checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=True,indent=2))
