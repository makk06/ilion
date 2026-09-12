"""Offline sprint experiments from captured real inputs; no HTTP or DB writes.

A/B coefficients and all counterfactual stress inputs are hypotheses, not labels.
Run from repo root with .integration-venv/Scripts/python.exe.
"""
import argparse
import json
import math
import os
import sys
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tourist_congestion_backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.utils import timezone
from places.models import PlaceCrowdArea, CrowdData, HistoricalSample, HistoricalBaseline, ForecastEvaluation
from places.integrations.weather import weather_grid
from places.services.crowd_estimator import (KST, ANCHORS, estimate, prior, profiles,
    profile_for, percentile, event_effect, weather_effect, rounded, level)
from places.services.crowd_confidence import freshness, clip
from places.services.crowd_collector import seoul_interval

ARTIFACTS = ROOT / '.integration-artifacts/crowd-validation'


def read(name):
    return json.loads((ARTIFACTS / name).read_text(encoding='utf-8'))


def stamp(value):
    return datetime.fromisoformat(value)


def features(inp, now):
    """Unsmoothed C decomposition, also used to define comparable A/B experiments."""
    b = prior(inp['profile'], now, inp['calendars'].get(now.astimezone(KST).date()))
    baseline = inp.get('baselines', {}).get((now.weekday(), now.hour))
    if baseline and inp.get('distribution'):
        b = percentile(inp['distribution'], baseline['median'])
    p, qp = b, 0
    pop, mapping = inp.get('population'), inp.get('mapping', {})
    if pop and not pop.get('is_replaced') and not inp.get('is_demo'):
        qp = freshness(pop['observed_at'], now, 'population') * mapping.get('match_quality', 0) * mapping.get('representativeness', 0)
        if inp.get('distribution'):
            p = percentile(inp['distribution'], pop['value'])
        elif pop.get('level') in ANCHORS:
            p, qp = ANCHORS[pop['level']], min(qp, .45)
        else:
            qp = 0
    trans = []
    for t in inp.get('transit', []):
        if t.get('baseline', 0) < 10 or t.get('sample_days', 0) < 4:
            continue
        q = freshness(t['observed_at'], now, 'transit') * mapping.get('match_quality', 0) * mapping.get('representativeness', 0)
        q *= 1 if t.get('timestamp_quality') == 'source' else .6
        if q:
            trans.append((q, 15*math.tanh(math.log(clip(t['value']/t['baseline'], .25, 4))/math.log(2))))
    qt = sum(q for q, _ in trans)/len(trans) if trans else 0
    dt = sum(q*d for q, d in trans)/sum(q for q, _ in trans) if trans else 0
    qe = freshness(inp.get('events_checked_at'), now, 'event')*inp.get('event_coverage', 0)
    e = event_effect(inp.get('events', []), inp['latitude'], inp['longitude'], now) if qe else 0
    weather = inp.get('weather')
    w, quality = weather_effect(inp['profile'], inp.get('indoor_outdoor'), weather['values'] if weather else None)
    qw = freshness(weather['issued_at'], now, 'weather')*quality if weather else 0
    return {'B':b, 'P':p, 'qP':qp, 'deltaT':dt, 'qT':qt, 'E':e, 'qE':qe, 'W':w, 'qW':qw}


def candidates(f, scales=None):
    scales = scales or {}
    b, p, dt, e, w = (f[k] for k in ('B','P','deltaT','E','W'))
    qp, qt, qe, qw = (f[k] for k in ('qP','qT','qE','qW'))
    sp, st, se, sw = (scales.get(k, 1) for k in ('population','transit','event','weather'))
    weights = [.4, .4*qp*sp, .1*qt*st, .05*qe*se, .05*qw*sw]
    a_model = sum(x*y for x,y in zip(weights, (b,p,b+dt,b+12*e,b+10*w)))/sum(weights)
    # Score ratios are experimental bootstrap ratios, NEVER visitor count ratios.
    b_model = b*(max(p, .01)/max(b, 5))**(.8*qp*sp)
    b_model *= (1+dt/100)**(.2*qt*st)*(1+.12*qe*e*se)*(1+.10*qw*w*sw)
    up, ut = .8*qp*sp, .2*qt*st
    delta = (up*(p-b)+ut*dt)/(up+ut) if up+ut else 0
    a = min(.9, .85*qp*sp+.30*qt*st)
    context = clip(12*qe*e*se+10*qw*w*sw, -20, 20)
    c_model = b+a*delta+(1-a)*context
    return {k:round(clip(v,0,100),3) for k,v in zip(('A','B','C'), (a_model,b_model,c_model))}


def make_inputs(now):
    kto, seoul, weather = read('kto.json'), read('seoul.json'), read('weather.json')
    areas = {}
    for row in seoul['observations']:
        if row.get('status') == 'success' and stamp(row['fetched_at']) <= now:
            areas[row['external_id']] = row
    # Existing verified source mapping is accepted only for the matching KTO ID.
    manual = {}
    for m in PlaceCrowdArea.objects.filter(verified=True, match_method__in=('manual','source')).select_related('crowd_area','place'):
        if m.valid_from and m.valid_from > now or m.valid_until and m.valid_until <= now:
            continue
        for source in m.place.sources.filter(source='tour_api', match_status='matched'):
            manual[source.external_id] = m
    holidays = weather['calendar'].get('holidays', {})
    calendars = {now.astimezone(KST).date()+timedelta(days=i): {
        'is_holiday': (now.astimezone(KST).date()+timedelta(days=i)).isoformat() in holidays,
        'holiday_run':0} for i in range(2)}
    events = []
    for row in kto['events']['items']:
        if not row.get('latitude') or not row.get('longitude'):
            continue
        events.append({'external_id':row['contentid'], 'latitude':row['latitude'], 'longitude':row['longitude'],
            'start_date':datetime.strptime(row['eventstartdate'],'%Y%m%d').date(),
            'end_date':datetime.strptime(row['eventenddate'],'%Y%m%d').date(), 'time_quality':'date_only'})
    output = []
    for label, poi in kto['selected'].items():
        mapping, area_code = {}, None
        if poi['contentid'] in manual:
            m=manual[poi['contentid']]
            area_code=m.crowd_area.external_id
            mapping={'area_id':m.crowd_area_id,'area_name':m.crowd_area.name,'match_method':m.match_method,
                     'match_quality':m.match_quality,'representativeness':m.representativeness}
        elif poi.get('polygon_match'):
            area_code=poi['polygon_match']['code']
            mapping={'area_id':area_code,'area_name':poi['polygon_match']['name'],'match_method':'polygon',
                     'match_quality':.9,'representativeness':.65}
        inp={'place_id':int(poi['contentid']),'latitude':poi['latitude'],'longitude':poi['longitude'],
             'profile':profile_for(poi),'profile_version':profiles()['version'],'indoor_outdoor':'unknown',
             'mapping':mapping,'calendars':calendars,'events':events,'event_coverage':.5,
             'events_checked_at':max(stamp(e['fetched_at']) for e in kto['events']['items']),
             'distribution':[],'baselines':{},'transit':[],'population':None,'weather':None,'forecast_weather':{},
             'sources':[{'provider':'tour_api','role':'place_metadata','fetched_at':poi['fetched_at']},
                        {'provider':'tour_api','role':'events_partial_date_window','coverage':.5},
                        {'provider':'kasi','role':'calendar','fetched_at':weather['checked_at']}]}
        obs=areas.get(area_code)
        if obs:
            pop=obs['population']
            inp['population']={'min':pop['population_min'],'max':pop['population_max'],
                'value':(pop['population_min']+pop['population_max'])/2,'observed_at':stamp(pop['observed_at']),
                'is_replaced':pop['is_replaced'],'level':pop['crowd_level']}
            inp['sources'].append({'provider':'seoul_citydata','role':'area_population','observed_at':pop['observed_at'],
                                   'fetched_at':obs['fetched_at']})
            for t in obs['transit']:
                inp['transit'].append({'mode':t['mode'],'value':(t['arrivals_min']+t['arrivals_max'])/2,
                    'observed_at':stamp(t['observed_at']),'timestamp_quality':t['timestamp_quality'],
                    'baseline':0,'sample_days':0})
        grid=weather_grid(poi['latitude'],poi['longitude'])
        rows=[]
        for place in weather['places']:
            if tuple(place['grid']) != grid:
                continue
            for product in place['products']:
                if product['status'] != 'passed' or stamp(product.get('fetched_at', weather['checked_at'])) > now:
                    continue
                for row in product['data']:
                    rows.append({'issued_at':stamp(product['issued_at']), 'valid_at':stamp(row['valid_at']),
                                 'values':row['values'],'product':product['product']})
        rows.sort(key=lambda r:r['issued_at'],reverse=True)
        inp['weather']=next((r for r in rows if r['product']=='getUltraSrtNcst' and r['valid_at']<=now),None)
        for h in (1,2,3):
            target=(now+timedelta(hours=h)).replace(minute=0,second=0,microsecond=0)
            found=next((r for r in rows if r['product']!='getUltraSrtNcst' and r['valid_at']==target),None)
            if found: inp['forecast_weather'][h]=found
        inp['sources'].append({'provider':'kma','role':'weather','grid':list(grid)})
        output.append((label,poi,inp,obs))
    return output


def run(now):
    results, sensitivity = [], []
    for label, poi, inp, obs in make_inputs(now):
        payload,_=estimate(inp,now)
        f=features(inp,now)
        models=candidates(f)
        assert rounded(models['C'])==payload['crowd_score'], (label, models, payload['crowd_score'])
        missing={}
        for scenario,keys in {'ALL':(), 'NO_POPULATION':('population',),'NO_TRANSIT':('transit',),
                              'ONLY_BASELINE':('population','transit','weather','events'),
                              'NO_REALTIME':('population','transit')}.items():
            removed=deepcopy(inp)
            for key in keys:
                removed[key]=[] if key in ('events','transit') else None
                if key=='events': removed['event_coverage']=0; removed['events_checked_at']=None
            result,_=estimate(removed,now)
            missing[scenario]={'models':candidates(features(removed,now)), 'C_score':result['crowd_score'],
                               'confidence':result['confidence'], 'tier':result['tier']}
        for signal in ('population','transit','event','weather'):
            for scale in (.8,1.2):
                changed=candidates(f,{signal:scale})
                sensitivity.append({'place':label,'signal':signal,'scale':scale,'scores':changed,
                                    'deltas':{m:round(changed[m]-models[m],3) for m in models}})
        nearby=[{'id':e['external_id'],'effect':round(event_effect([e],inp['latitude'],inp['longitude'],now),4)}
                for e in inp['events'] if event_effect([e],inp['latitude'],inp['longitude'],now)>0]
        results.append({'place':label,'contentid':poi['contentid'],'title':poi['title'],
            'coordinate':[poi['latitude'],poi['longitude']],'profile':inp['profile'],'grid':weather_grid(poi['latitude'],poi['longitude']),
            'mapping':inp['mapping'],'polygon_diagnostics':poi.get('polygon_diagnostics'),
            'features':f,'models':models,'result':payload,'missing':missing,'nearby_active_events':nearby,
            'transit_observed':obs['transit'] if obs else [],'transit_used':False,
            'weather_input':inp['weather'],'calendars':{str(k):v for k,v in inp['calendars'].items()}})
    # Controlled counterfactuals use captured metadata/weather, but hypothetical timing/counts.
    base=deepcopy(make_inputs(now)[0][2])
    base.update(population=None, transit=[], mapping={}, events=[], event_coverage=0, events_checked_at=None,
                profile='park',indoor_outdoor='outdoor',weather=None,forecast_weather={})
    weekday=datetime(2026,9,14,3,tzinfo=KST)
    timing={at.isoformat():estimate(base,at)[0]['crowd_score'] for at in (weekday,weekday.replace(hour=15),weekday+timedelta(days=5,hours=12))}
    rain=deepcopy(base); rain['weather']={'issued_at':now,'values':{'temperature':20,'precipitation_type':1}}
    event=deepcopy(base); event['events_checked_at']=now; event['event_coverage']=1
    event['events']=[{'external_id':'hypothetical','latitude':base['latitude'],'longitude':base['longitude'],
        'start_date':now.date(),'end_date':now.date(),'starts_at':now-timedelta(minutes=1),'ends_at':now+timedelta(hours=1),
        'time_quality':'verified','size_evidence':'counterfactual only','size_valid_until':now.date(),'size_weight':1}]
    baseline_only=estimate(base,now)[0]['crowd_score']
    empirical=deepcopy(base)
    empirical.update(mapping={'match_quality':1,'representativeness':1},distribution=list(range(1,101)),
        baselines={(now.weekday(),now.hour):{'median':50,'sample_days':8,'coverage':1,'context':{}}})
    outliers=[]
    for value in (50,100,1000000000):
        empirical['population']={'min':value,'max':value,'value':value,'observed_at':now,'level':'normal'}
        outliers.append({'hypothetical_population':value,'models':candidates(features(empirical,now)),
                         'C_score':estimate(empirical,now)[0]['crowd_score']})
    no_pop=deepcopy(empirical); no_pop['population']=None
    transit_extremes=[]
    for count in (25,100,200,400,1000000000):
        case=deepcopy(no_pop)
        case['transit']=[{'mode':'subway','value':count,'baseline':100,'sample_days':4,
                         'observed_at':now,'timestamp_quality':'source'}]
        transit_extremes.append({'hypothetical_arrivals':count,'models':candidates(features(case,now)),
                                'C_score':estimate(case,now)[0]['crowd_score']})
    double_low=deepcopy(empirical)
    double_low['distribution']=list(range(1,1001))
    double_low['baselines'][now.weekday(),now.hour]['median']=20
    double_low['population'].update(min=40,max=40,value=40)
    relative=estimate(double_low,now)[0]
    stress={'evidence_kind':'counterfactual software checks, NOT observed visits or accuracy labels',
            'weekday_dawn_afternoon_weekend':timing, 'baseline_score':baseline_only,
            'rain_score':estimate(rain,now)[0]['crowd_score'], 'nearby_large_event_score':estimate(event,now)[0]['crowd_score'],
            'population_outliers':outliers, 'transit_outliers':transit_extremes,
            'empirical_drop_population':estimate(no_pop,now)[0]['crowd_score'],
            'twice_normal_low_absolute_day_distribution':{'score':relative['crowd_score'],
                'relative_to_normal':relative['relative_to_normal'],'level':relative['crowd_level']}}
    assert list(timing.values())==sorted(timing.values())
    assert stress['rain_score']<baseline_only<stress['nearby_large_event_score']
    assert outliers[-1]['C_score']==outliers[-2]['C_score']<100
    assert transit_extremes[-1]['C_score']==transit_extremes[-2]['C_score']<100
    interval=seoul_interval(1000)
    quota={'daily_cap':1000,'normal_budget':800,'areas':121,'interval_minutes':interval,
           'max_hourly_coverage':60/interval,'population_usable_fraction_zero_source_delay':60/interval,
           'population_usable_fraction_30min_source_delay':30/interval,
           'minimum_daily_cap_for_5min_all_areas':math.ceil(121*288/.8)}
    counts={m.__name__:m.objects.count() for m in (CrowdData,HistoricalSample,HistoricalBaseline,ForecastEvaluation)}
    sensitivity_summary={}
    for model in ('A','B','C'):
        flips=[]
        for signal in ('population','transit','event','weather'):
            for scale in (.8,1.2):
                changed={r['place']:r['scores'][model] for r in sensitivity if r['signal']==signal and r['scale']==scale}
                for i,left in enumerate(results):
                    for right in results[i+1:]:
                        original=left['models'][model]-right['models'][model]
                        altered=changed[left['place']]-changed[right['place']]
                        if original*altered<0:
                            flips.append({'signal':signal,'scale':scale,'pair':[left['place'],right['place']],
                                          'original_gap':round(abs(original),3),'new_gap':round(abs(altered),3)})
        sensitivity_summary[model]={'max_abs_score_change':max(abs(s['deltas'][model]) for s in sensitivity),
                                    'pairwise_rank_flips':flips}
    return {'evaluated_at':now.isoformat(),'profile_version':profiles()['version'],
            'ground_truth_available':False,'production_history_counts':counts,
            'event_coverage_assumption':.5,'places':results,'sensitivity':sensitivity,
            'sensitivity_summary':sensitivity_summary,'stress':stress,'quota':quota}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--at',help='Replay timestamp in ISO8601, no future input selection')
    args=parser.parse_args()
    now=stamp(args.at) if args.at else timezone.now().astimezone(KST)
    report=run(now)
    (ARTIFACTS/'comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    print(json.dumps({'evaluated_at':report['evaluated_at'],'places':[
        {'place':p['place'],'score':p['result']['crowd_score'],'confidence':p['result']['confidence'],
         'tier':p['result']['tier'],'models':p['models']} for p in report['places']],
         'stress':report['stress'],'quota':report['quota']},ensure_ascii=True))
