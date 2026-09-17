"""Offline, retrospective auxiliary model comparison. Never fetches or trains on model outputs."""
import argparse
import hashlib
import importlib.util
import json
import math
import platform
import sqlite3
import socket
import sys
import time
from collections import Counter
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
CAPTURE = ROOT / '.integration-artifacts/crowd-validation'
MODELS = ('mean', 'hour', 'area_median', 'hierarchy', 'persistence',
          'ridge', 'stump', 'hybrid_a', 'hybrid_b', 'hybrid_c')
TAG = 'retrospective_auxiliary'


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(name):
    return json.loads((CAPTURE / name).read_text(encoding='utf-8'))


def field_audit(records):
    """Flatten nested objects; array rows are audited in their own dataset."""
    def flatten(row, prefix=''):
        result = {}
        for key, value in row.items():
            key = prefix + key
            if isinstance(value, dict):
                result.update(flatten(value, key + '.'))
            elif not isinstance(value, list):
                result[key] = value
        return result
    rows = [flatten(row) for row in records]
    result = {}
    for key in sorted(set().union(*(r.keys() for r in rows))):
        values = [r[key] for r in rows if r.get(key) is not None and r.get(key) != '']
        counts = Counter(encode(v) for v in values)
        numeric = values and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values)
        result[key] = {'rows': len(rows), 'missing': len(rows)-len(values),
                       'missing_rate': (len(rows)-len(values))/len(rows), 'unique': len(counts),
                       'min': min(values) if numeric else None, 'max': max(values) if numeric else None,
                       'values': {k: n for k, n in sorted(counts.items())} if len(counts) <= 20 else None}
        if key.endswith(('_at', 'time')) and values and all(isinstance(v, str) for v in values):
            result[key]['string_range'] = [min(values), max(values)]
    return result


def audit():
    seoul, kto, weather = read('seoul.json'), read('kto.json'), read('weather.json')
    accepted, rejected = {}, []
    for row in seoul['observations']:
        p = row.get('population') or {}
        reason = None
        if row.get('is_demo') or p.get('is_replaced'):
            reason = 'DEMO_OR_REPLACED'
        elif not p.get('observed_at') or not row.get('fetched_at'):
            reason = 'MISSING_TIME'
        elif not isinstance(p.get('population_min'), (int, float)) or not isinstance(p.get('population_max'), (int, float)):
            reason = 'MISSING_RANGE'
        elif not 0 <= p['population_min'] <= p['population_max']:
            reason = 'INVALID_RANGE'
        if reason:
            rejected.append({'area': row.get('external_id'), 'reason': reason})
            continue
        key = row['external_id'] + '@' + p['observed_at']
        if key in accepted:
            old = accepted[key]
            assert old['population'] == p, 'Conflicting same-time observations require manual review'
            rejected.append({'id': key, 'reason': 'DUPLICATE_SOURCE_OBSERVATION'})
            if datetime.fromisoformat(old['fetched_at']) <= datetime.fromisoformat(row['fetched_at']):
                continue
        accepted[key] = row
    rows = []
    origin = min(datetime.fromisoformat(r['population']['observed_at']) for r in accepted.values())
    for key, r in accepted.items():
        p = r['population']
        at = datetime.fromisoformat(p['observed_at'])
        rows.append({'id': key, 'area': r['external_id'], 'category': r.get('category'),
                     'at': at.isoformat(), 'received': r['fetched_at'],
                     't': (at-origin).total_seconds()/600, 'hour': f'{at.weekday()}:{at.hour}',
                     'y': (p['population_min']+p['population_max'])/2})
    rows.sort(key=lambda r: (r['at'], r['area']))
    forward = sum(a['area'] == b['area'] and datetime.fromisoformat(a['received']) < datetime.fromisoformat(b['at'])
                  and a['at'] < b['at'] for a in rows for b in rows)
    transit = [dict(t, area=r['external_id']) for r in seoul['observations'] for t in r.get('transit', [])]
    weather_rows = [dict(d, product=p['product'], grid=r['grid'], issued_at=p['issued_at'])
                    for r in weather['places'] for p in r['products'] for d in p.get('data', [])]
    datasets = {'population': list(accepted.values()), 'transit': transit,
                'kto_selected': list(kto['selected'].values()), 'weather': weather_rows,
                'events': kto['events']['items']}
    files = []
    for path in sorted((ROOT / '.integration-artifacts').rglob('*')):
        if path.is_file() and path.suffix in ('.json', '.csv', '.sqlite3'):
            role = 'CONTEXT_ONLY'
            if path == CAPTURE/'seoul.json':
                role = 'ONLY_TRAINING_SOURCE'
            elif path not in (CAPTURE/'kto.json', CAPTURE/'weather.json', CAPTURE/'comparison.json'):
                role = 'EXCLUDED_BACKUP_REPLAY_SYNTHETIC_OR_DERIVED'
            entry = {'path': path.relative_to(ROOT).as_posix(), 'sha256': digest(path), 'bytes': path.stat().st_size, 'role': role}
            if path.suffix == '.sqlite3':
                with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
                    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    entry['counts'] = {t: db.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in
                                       ('places_crowddata', 'places_historicalsample', 'places_historicalbaseline', 'places_forecastevaluation') if t in tables}
            files.append(entry)
    prod = ROOT/'tourist_congestion_backend/db.sqlite3'
    if prod.exists():
        with sqlite3.connect(prod.as_uri()+'?mode=ro', uri=True) as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            production = {t: db.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in
                          ('places_crowddata', 'places_historicalsample', 'places_historicalbaseline', 'places_forecastevaluation') if t in tables}
    else:
        production = {'status': 'ABSENT'}
    return rows, {'tag': TAG, 'files': files, 'excluded_rows': rejected,
                  'independent_population_count': len(rows), 'per_area': dict(Counter(r['area'] for r in rows)),
                  'source_range': [rows[0]['at'], rows[-1]['at']], 'forward_pairs': forward,
                  'classes': dict(Counter(r['population']['crowd_level'] for r in accepted.values())),
                  'transit_raw': len(transit), 'transit_unique': len({(r['area'], r['mode'], r['fingerprint']) for r in transit}),
                  'weather_products': dict(Counter(r['product'] for r in weather_rows)),
                  'production_counts_read_only': production,
                  'fields': {name: field_audit(data) for name, data in datasets.items()}}


def splits(rows):
    ticks = sorted({r['t'] for r in rows})
    assert len(ticks) == 5 and len(rows) == 20, 'Frozen experiment expects the audited 20 rows'
    yield 'time_validation', [r for r in rows if r['t'] in ticks[:2]], [r for r in rows if r['t'] == ticks[2]]
    yield 'time_test', [r for r in rows if r['t'] in ticks[:3]], [r for r in rows if r['t'] in ticks[3:]]
    for area in sorted({r['area'] for r in rows}):
        yield 'area_'+area, [r for r in rows if r['area'] != area], [r for r in rows if r['area'] == area]
        yield 'joint_'+area, [r for r in rows if r['area'] != area and r['t'] in ticks[:3]], [r for r in rows if r['area'] == area and r['t'] in ticks[3:]]


def grouped(rows, field, reducer):
    return {key: float(reducer([r['y'] for r in rows if r.get(field) == key])) for key in sorted({r[field] for r in rows})}


class Model:
    """One frozen training snapshot; predict accepts metadata only, never a target."""
    def __init__(self, name, rows, no_id=False, no_time=False):
        self.name, self.no_id, self.no_time = name, no_id, no_time
        self.rows = [{k: r[k] for k in ('area', 'category', 't', 'hour', 'y')} for r in rows]
        self.mean = float(np.mean([r['y'] for r in rows]))
        self.median = float(np.median([r['y'] for r in rows]))
        self.area = grouped(rows, 'area', np.median)
        self.category = grouped(rows, 'category', np.median)
        self.hour = grouped(rows, 'hour', np.mean)
        self.hour_median = grouped(rows, 'hour', np.median)
        self.area_hour = {a+'|'+h: float(np.median([r['y'] for r in rows if r['area'] == a and r['hour'] == h]))
                          for a in self.area for h in self.hour if any(r['area'] == a and r['hour'] == h for r in rows)}
        self.last = {a: max((r for r in self.rows if r['area'] == a), key=lambda r: r['t']) for a in self.area}
        self.ids = sorted(self.area) if not no_id else []
        self.categories = sorted(self.category)
        numerator = denominator = 0.
        for area in self.area:
            history = sorted((r for r in rows if r['area'] == area), key=lambda r: r['t'])
            for a, b in zip(history, history[1:]):
                dt = b['t']-a['t']
                numerator += dt*(math.log1p(b['y'])-math.log1p(a['y']))
                denominator += dt*dt
        self.rate = 0. if no_time else numerator/(denominator+1)
        # Area intercepts are unpenalized; without ID use category intercepts instead.
        self.groups = self.ids or self.categories
        self.group_field = 'area' if self.ids else 'category'
        z = np.log1p([r['y'] for r in rows])
        self.coef = []
        self.tree = None
        if name in ('ridge', 'hybrid_b', 'hybrid_c'):
            x = np.array([self.design(r, name == 'hybrid_b') for r in rows])
            penalty = np.diag([0.]*len(self.groups) + [1.]*(x.shape[1]-len(self.groups)))
            self.coef = np.linalg.pinv(x.T@x+penalty)@x.T@z
        if name == 'stump':
            x = np.array([self.tree_features(r) for r in rows])
            self.tree = {'feature': None, 'left': float(np.mean(z)), 'right': float(np.mean(z))}
            best = float(np.sum((z-np.mean(z))**2))
            for j in range(x.shape[1]):
                unique = np.unique(x[:, j])
                for cut in (unique[:-1]+unique[1:])/2:
                    mask = x[:, j] <= cut
                    if min(sum(mask), sum(~mask)) < 2:
                        continue
                    left, right = float(np.mean(z[mask])), float(np.mean(z[~mask]))
                    loss = float(np.sum((z[mask]-left)**2)+np.sum((z[~mask]-right)**2))
                    if loss < best-1e-12:
                        best = loss
                        self.tree = {'feature': j, 'cut': float(cut), 'left': left, 'right': right}

    def design(self, r, hybrid=False):
        features = [float(r.get(self.group_field) == g) for g in self.groups]
        t = 0. if self.no_time else r['t']
        if hybrid:
            # Same training-only hour baseline and common rate for every row, including train diagnostics.
            features += [math.log1p(self.hour.get(r.get('hour'), self.mean)), self.rate*t]
        else:
            features += [t]
        return features

    def tree_features(self, r):
        return [float(r.get('area') == a) for a in self.ids] + [float(r.get('category') == c) for c in self.categories] + [0. if self.no_time else r['t']]

    def predict(self, r, scenario='full'):
        assert 'y' not in r, 'Target must be stripped at the prediction boundary'
        area = r.get('area') if not self.no_id else None
        if scenario in ('no_history', 'baseline_only'):
            return self.mean
        if r.get('t') is None or r.get('hour') is None:
            return self.mean
        name = self.name
        if name == 'mean':
            return self.mean
        if name == 'hour':
            return self.mean if self.no_time else self.hour.get(r['hour'], self.mean)
        if name == 'area_median':
            return self.area.get(area, self.mean) if self.no_time else self.area_hour.get(str(area)+'|'+r['hour'], self.mean)
        if name == 'hierarchy':
            return self.area.get(area, self.category.get(r.get('category'), self.hour_median.get(r['hour'], self.median)))
        if name in ('persistence', 'hybrid_a'):
            if area not in self.last:
                return self.mean
            last = self.last[area]
            change = self.rate*(r['t']-last['t']) if name == 'hybrid_a' else 0.
            return max(0., math.expm1(math.log1p(last['y'])+change))
        if (self.ids and area not in self.ids) or (not self.ids and r.get('category') not in self.categories):
            return self.mean
        if name == 'hybrid_c' and (area not in self.last or not r.get('category')):
            return self.mean
        if name == 'stump':
            node = self.tree
            z = node['left'] if node['feature'] is None or self.tree_features(r)[node['feature']] <= node['cut'] else node['right']
        else:
            z = float(np.dot(self.design(r, name == 'hybrid_b'), self.coef))
        return max(0., math.expm1(z))

    def state(self):
        return {**self.__dict__, 'coef': list(self.coef)}


def features(row):
    return {k: row[k] for k in ('area', 'category', 't', 'hour')}


def metrics(rows, predicted):
    actual = np.array([r['y'] for r in rows])
    p = np.array(predicted)
    delta, logdelta = p-actual, np.log1p(p)-np.log1p(actual)
    total = float(np.sum((actual-np.mean(actual))**2))
    per_area = {a: metrics([r for r in rows if r['area'] == a], [v for r, v in zip(rows, p) if r['area'] == a])
                for a in sorted({r['area'] for r in rows})} if len({r['area'] for r in rows}) > 1 else {}
    return {'n': len(rows), 'log_mae': float(np.mean(abs(logdelta))), 'log_rmse': float(np.sqrt(np.mean(logdelta**2))),
            'mae': float(np.mean(abs(delta))), 'rmse': float(np.sqrt(np.mean(delta**2))),
            'r2': 1-float(np.sum(delta**2))/total if total > 0 else None,
            'macro_area_log_mae': float(np.mean([m['log_mae'] for m in per_area.values()])) if per_area else float(np.mean(abs(logdelta))),
            'per_area': per_area}


def benchmark(fn):
    for _ in range(10):
        fn()
    samples = []
    for _ in range(100):
        start = time.perf_counter_ns()
        fn()
        samples.append((time.perf_counter_ns()-start)/1000)
    return {'p50_us': float(np.percentile(samples, 50)), 'p95_us': float(np.percentile(samples, 95)), 'repeats': 100}


def experiments(rows):
    result, timings, split_manifest, checks = [], [], [], []
    for split, train, test in splits(rows):
        split_manifest.append({'name': split, 'train': [r['id'] for r in train], 'evaluation': [r['id'] for r in test]})
        for name in MODELS:
            start = time.perf_counter_ns()
            model = Model(name, train)
            elapsed = (time.perf_counter_ns()-start)/1000
            state = encode(model.state())
            again = Model(name, deepcopy(train))
            assert state == encode(again.state())
            mutated_test = [dict(r, y=r['y']*123+17) for r in test]
            assert [features(r) for r in test] == [features(r) for r in mutated_test]
            assert state == encode(model.state())
            predictions = [model.predict(features(r)) for r in test]
            assert predictions == [again.predict(features(r)) for r in mutated_test]
            checks.append({'split': split, 'model': name, 'deterministic': True, 'target_mutation_invariant': True})
            entry = {'tag': TAG, 'split': split, 'model': name, 'state': model.state(),
                     'train_resubstitution': metrics(train, [model.predict(features(r)) for r in train]),
                     'evaluation': metrics(test, predictions), 'predictions': [dict(id=r['id'], actual=r['y'], predicted=p,
                          error=p-r['y'], log_error=math.log1p(p)-math.log1p(r['y'])) for r, p in zip(test, predictions)], 'ablation': {}}
            for scenario in ('full', 'no_history', 'no_transit', 'no_event', 'no_weather', 'baseline_only', 'missing_time'):
                inp = [dict(features(r), t=None) if scenario == 'missing_time' else features(r) for r in test]
                pred = [model.predict(r, scenario) for r in inp]
                entry['ablation'][scenario] = {'status': 'NOT_USED' if scenario in ('no_transit', 'no_event', 'no_weather') else 'EVALUATED',
                                               'metrics': metrics(test, pred), 'predictions': pred}
            for option in ('no_id', 'no_time'):
                ablated = Model(name, train, **{option: True})
                pred = [ablated.predict(features(r)) for r in test]
                entry['ablation'][option] = {'status': 'EVALUATED', 'metrics': metrics(test, pred), 'predictions': pred}
            prepared = [features(r) for r in test]
            timing = benchmark(lambda: [model.predict(r) for r in prepared])
            timings.append({'split': split, 'model': name, 'train_us': elapsed, 'state_bytes': len(state.encode()),
                            'batch_rows': len(test), 'prepared_metadata_batch_inference': timing})
            result.append(entry)
    return result, timings, split_manifest, checks


def heuristic_replay():
    """Reuse capture normalizer with frozen mappings; reject any accidental DB access."""
    spec = importlib.util.spec_from_file_location('offline_comparison', ROOT/'scripts/crowd-validation/compare_models.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from django.db import connection
    def deny(execute, sql, params, many, context):
        raise AssertionError('Experiment must not query the ORM')
    frozen = []
    codes = {r['name']: r['external_id'] for r in read('seoul.json')['observations']}
    for row in read('comparison.json')['places']:
        mapping = row['mapping']
        if mapping.get('match_method') not in ('manual', 'source'):
            continue
        sources = SimpleNamespace(filter=lambda contentid=row['contentid'], **kwargs: [SimpleNamespace(external_id=contentid)])
        frozen.append(SimpleNamespace(valid_from=None, valid_until=None, place=SimpleNamespace(sources=sources),
            crowd_area_id=mapping['area_id'], crowd_area=SimpleNamespace(external_id=codes[mapping['area_name']], name=mapping['area_name']),
            match_method=mapping['match_method'], match_quality=mapping['match_quality'], representativeness=mapping['representativeness']))
    module.PlaceCrowdArea = SimpleNamespace(objects=SimpleNamespace(filter=lambda **kw: SimpleNamespace(select_related=lambda *a: frozen)))
    now = datetime.fromisoformat('2026-09-12T23:26:14.771409+09:00')
    with connection.execute_wrapper(deny):
        inputs = module.make_inputs(now)
        results = []
        for label, poi, data, _ in inputs:
            cases = {}
            for scenario, keys in {'full': (), 'no_history': ('population', 'transit'), 'no_transit': ('transit',),
                                   'no_event': ('events',), 'no_weather': ('weather', 'forecast_weather'),
                                   'baseline_only': ('population', 'transit', 'events', 'weather', 'forecast_weather')}.items():
                changed = deepcopy(data)
                for key in keys:
                    changed[key] = [] if key in ('transit', 'events') else {} if key == 'forecast_weather' else None
                if 'events' in keys:
                    changed.update(event_coverage=0, events_checked_at=None)
                payload, _ = module.estimate(changed, now)
                assert 0 <= payload['crowd_score'] <= 100
                cases[scenario] = {k: payload.get(k) for k in ('crowd_score', 'confidence', 'tier', 'normalization', 'limitations')}
            results.append({'place': label, 'cases': cases, 'inference': benchmark(lambda: module.estimate(data, now)),
                            'input_bytes': len(repr(data).encode()), 'input_size_format': 'python_repr_utf8',
                            'target': 'original_0_100', 'mae': None})
    return {'tag': 'captured_input_functional_replay', 'model': module.estimate.__module__, 'results': results,
            'warning': 'No crowd labels. Timing includes current and three forecasts; not comparable work to one population regression.'}


def report(audit_data, results, heuristic, timing):
    lookup = {(r['split'], r['model']): r for r in results}
    table = '| Model | validation log-MAE | time test log-MAE | area holdout log-MAE | joint holdout log-MAE | test raw MAE |\n|---|---:|---:|---:|---:|---:|\n'
    for name in MODELS:
        values = [lookup[(s, name)]['evaluation']['log_mae'] for s in ('time_validation', 'time_test')]
        values += [float(np.mean([r['evaluation']['log_mae'] for r in results if r['model'] == name and r['split'].startswith(prefix)])) for prefix in ('area_', 'joint_')]
        values += [lookup[('time_test', name)]['evaluation']['mae']]
        table += '| '+name+' | '+' | '.join(f'{v:.6f}' for v in values)+' |\n'
    winner = min(MODELS, key=lambda n: lookup[('time_test', n)]['evaluation']['log_mae'])
    ablation_table = '| Model | full | no ID | no time | no history |\n|---|---:|---:|---:|---:|\n'
    for name in MODELS:
        cases = lookup[('time_test', name)]['ablation']
        ablation_table += '| '+name+' | '+' | '.join(f"{cases[k]['metrics']['log_mae']:.6f}" for k in ('full', 'no_id', 'no_time', 'no_history'))+' |\n'
    performance_table = '| Model | train µs | JSON bytes | 8-row p50 µs | 8-row p95 µs |\n|---|---:|---:|---:|---:|\n'
    for row in timing['models']:
        if row['split'] == 'time_test':
            latency = row['prepared_metadata_batch_inference']
            performance_table += f"| {row['model']} | {row['train_us']:.1f} | {row['state_bytes']} | {latency['p50_us']:.2f} | {latency['p95_us']:.2f} |\n"
    fit_table = '| Model | train log-MAE (12 rows) | test log-RMSE | test raw RMSE | test R² |\n|---|---:|---:|---:|---:|\n'
    for name in MODELS:
        row = lookup[('time_test', name)]
        m = row['evaluation']
        fit_table += f"| {name} | {row['train_resubstitution']['log_mae']:.6f} | {m['log_rmse']:.6f} | {m['rmse']:.2f} | {m['r2']:.6f} |\n"
    # Auxiliary selection objective is the predeclared primary log-MAE on the fixed temporal replay.
    sections = [
        ('Executive Summary', f'운영 후보는 **heuristic-v1.2 Baseline + Delta**, fallback은 기존 낮은 신뢰도의 유형·시간 prior다. 운영 코드·DB·키·수집 설정은 변경하지 않았다. 보조 실험의 시간 평가 log-MAE 최저 모델은 **{winner}**다. 이는 회고적 영역 인구 재현 결과이며 실제 혼잡도 정확도나 배포 우수성의 증거가 아니다.\n\n새 API 호출·다운로드·의존성 설치 없이 실행했다. 모든 학습 결과는 `retrospective_auxiliary`다.'),
        ('Dataset Audit', f"독립 인구 {audit_data['independent_population_count']}행, 영역별 {audit_data['per_area']}. 원천 범위 {audit_data['source_range']}. 단계 분포 {audit_data['classes']}. 교통 {audit_data['transit_raw']}행 / 고유 {audit_data['transit_unique']}행, 모두 collection_only. 날씨 상품별 {audit_data['weather_products']}. KTO 선정 6곳, 행사 297개.\n\n`results/manifest.json`에 파일별 SHA-256·제외 사유·DB 읽기 전용 건수·필드별 결측률과 고유값을 저장했다. 백업·재생 DB는 추가 표본이 아니며 benchmark와 모델 출력은 학습에서 제외한다. 학습 파일은 seoul.json 한 개뿐이다. 실제 경험적 기준선·독립 평가 정답은 없다."),
        ('Target Definition', '`P=(min+max)/2`, `y=log1p(P)`. 공급자 영역 인구가 목표이며 POI 방문객 수·밀도·체감 혼잡도가 아니다. 로그 회귀 출력은 expm1으로 되돌린다. 상수 모델은 원 단위 산술평균을 사용한다. 공식 4단계는 한 클래스뿐, 자체 점수는 모델 출력, 상대 비율은 기준선 부재, 체감 5단계는 정답 부재로 평가하지 않는다. 분류 100%나 임의 5단계 지표를 만들지 않았다.'),
        ('Validation Methodology', f"시간 검증 8→4행, 시간 평가 12→8행. 영역 제외 4-fold 15→5행, 영역+시간 제외 4-fold 9→2행. 동일 원천 시각을 시간 분할 경계에서 함께 이동한다. 영역 제외는 공간 진단이므로 다른 영역의 같은 시각을 포함한다. 학습 후 평가 행을 순차 업데이트하지 않는다. `splits.json`은 관측 ID를 고정한다.\n\n실제 수신 시점을 지키는 미래 쌍 **{audit_data['forward_pairs']}개**. 수신 지연을 무시한 보조 실험이며 이미 예비 확인한 표본으로 새 독립 테스트가 아니다. 조정·탐색 없이 λ=1, stump depth=1/min_leaf=2를 고정했다. train_resubstitution은 학습 집계 및 마지막 값 재사용을 포함하는 적합 진단으로, 순방향 학습 성능이 아니다.\n\n`synthetic_checks.json`의 정답 변조·재실행 검사는 학습 지표와 분리한다. 훈련 모델은 target을 받지 않는 predict 경계로 평가한다. 입력 범주·평균·중앙값·변화율은 학습 데이터에서만 산출한다."),
        ('Algorithm Baselines', 'mean: 원 인구 산술평균. hour: 요일×시간 평균→전체 평균. area_median: 영역×요일×시간 median→전체 평균. hierarchy: 영역 median→공식 분류 median→요일·시간 median→전체 median. persistence: 학습 마지막 영역 인구→전체 평균. 20행은 모두 같은 요일·시간이므로 시간 기준은 상수 기준과 같다. 정규화가 불필요한 작은 시간 변수(원천 시작 이후 10분 단위)를 사용한다.'),
        ('Classical ML Results', 'Ridge는 영역 절편을 비규제하고 공통 시간 기울기만 λ=1로 규제한다. ID 제거 시 공식 분류 절편을 사용한다. 미관측 영역 ID는 전체 학습 평균으로 fallback한다. Stump는 학습 영역 one-hot·공식 분류 one-hot·시간 후보의 로그 SSE 최소 분할이며 동률은 고정 순서로 결정한다. 예비 stump에는 분류 입력이 없었으나 본 실행은 계획대로 분류도 포함한다. 결과를 트리 계열 전체로 일반화하지 않는다.\n\n'+table),
        ('Neural Network Results', 'MLP·embedding 및 Random Forest·Gradient Boosting은 DEFERRED_INSUFFICIENT_VALIDATION. 4영역·5시각으로 용량 선택과 일반화를 검증하기 어렵다. 신경망 프레임워크를 설치하거나 가짜 성능값을 채우지 않았다. 보류는 모델 계열의 무용성을 뜻하지 않는다.'),
        ('Hybrid Results', 'A: 학습 마지막 log 인구 + Σ(dt·dlogP)/(Σdt²+1) × 마지막 시각 이후 경과. B: 영역 절편에 학습 요일·시간 log 평균과 공통 변화율×시간을 추가한 Ridge, 추가 두 열 λ=1. 한 시간대뿐이라 시간 기준 열은 사실상 상수이며 효과를 식별하기 어렵다. C: 사전 고정 Ridge에 미관측 영역·시간 또는 분류 누락 시 전체 학습 평균을 반환하는 guardrail. 기본 Ridge도 미관측 ID fallback하므로 정상 조건에서 C는 Ridge와 같을 수 있다. C의 기반 모델은 테스트 성적을 보고 선택하지 않았다.'),
        ('Model Comparison', table+'\n로그 MAE·RMSE, 원 단위 MAE·RMSE·R², 영역별 오차 및 영역 균등 log-MAE를 `metrics.json`에 저장했다. 상수 정답 등 R² 분모 0은 null. 공간 fold 평균은 영역 균등 평균이다. 통계적 우수성·전국 일반화 신뢰구간은 계산하지 않았다.\n\n`timings.json`은 데이터 로딩과 모델 학습·상태 직렬화 크기·준비된 메타데이터 배치 추론 p50/p95를 구분한다. 각 10회 워밍업 후 100회, 실행 환경을 기록했다. 상태 크기는 추론용 통계와 감사용 학습 행을 포함하는 JSON 크기이며 최적화된 배포 바이너리 크기가 아니다. 기존 heuristic은 1현재+3예측을 반환하므로 작업량이 다르다. 벽시계 시간은 재실행 때 달라진다.'),
        ('Ablation / Feature Importance', '모든 후보에 full/no_history/no_transit/no_event/no_weather/baseline_only/missing_time를 적용했다. no_history는 장소별 이력을 사용하지 못하는 배포 상황으로 고정 전체 학습 평균을 반환한다. 학습 데이터 자체를 삭제한 재학습을 뜻하지 않는다. baseline_only 역시 동일 상수 fallback 진단이다. 교통·행사·날씨는 NOT_USED이며 제거 효과 0으로 무용성을 주장하지 않는다. no_id/no_time는 학습부터 다시 수행하며 no_id의 Ridge는 공식 분류 절편을 사용한다. SHAP 없이 입력 제거에 따른 지표 변화를 기록했다. heuristic은 실제 캡처 입력에서 별도로 신호를 제거하며 원래 0~100 점수·confidence를 보존한다.'),
        ('Failure Cases', '검증과 시간 평가의 순위가 달라 4~8행 결과는 불안정하다. 미관측 영역의 절대 규모를 시간만으로 알 수 없고 전체 평균 fallback은 작은 궁궐 영역과 큰 상권에서 큰 오차를 만든다. hierarchy의 분류도 표본이 매우 작고 미관측 분류는 보장하지 못한다. 시간은 25분 야간 한 구간, 클래스는 relaxed뿐이다. 22:50 target은 22:55 입력으로 재사용하지 않았다. 교통은 늦게 수신되어 같은 응답의 과거 인구 target에 붙이지 않는다. 매핑 중첩과 넓은 영역 대표성 문제는 인구 재현 오차로 해소되지 않는다.'),
        ('Final Decision', f'**운영 주 모델: heuristic-v1.2. Fallback: 낮은 신뢰도의 유형·시간 prior.** 제품 5단계 target과 독립 정답이 없어 ML로 교체할 근거가 없다. 정확도 우승에 의한 선택이 아니다.\n\n**보조 시간 재생의 기술적 최저 오차: {winner}.** 고정 시간 평가 log-MAE를 기준으로 한 기술적 순위다. 공간 제외·결측 결과는 위 표와 ablation에 함께 보고하며, 미관측 영역 일반화 성공 또는 안정된 단일 우승 모델로 해석하지 않는다. 배포 승격은 보류한다. 기존 모델 역시 실제 정확도는 UNKNOWN이다.'),
        ('Production Design', '운영 API·confidence·121개 균등 수집·전국 예상 5단계는 유지한다. 실험 코드만 experiments/crowd-model에 격리했다. 기존 heuristic은 함수 재생만 하며 ORM 조회를 차단한다. ML 잔차나 회귀값을 evidence-quality confidence로 바꾸지 않는다. 학습 artifact를 웹 요청 경로에서 읽거나 외부 작업을 생성하지 않는다. 새 데이터로 재실험하려면 분할 정책을 별도 검토해야 하며 현재 진입점은 20행·5시각을 검증한다.'),
        ('Next Data To Collect', '새 API 조사는 하지 않았다. 기존 실패 근거에 따른 우선순위다.\n\n1. 발행 이후 실제 수신되는 동일 영역 미래 관측: 현재 순방향 평가 쌍 0개를 해결한다.\n2. 서로 다른 혼잡 상태의 독립 평가 표본: relaxed 한 클래스 및 체감 정답 부재를 해결한다.\n3. 더 다양한 영역의 동일 정의 인구: 미관측 영역의 규모 오차를 검증한다.\n4. 주말·주간·계절을 포함한 반복 시계열: 25분 야간 편향과 기준선 미충족을 해결한다.\n5. POI와 영역의 대표성·운영시간 검증 자료: 중첩 매핑과 시설 내부 해석 문제를 줄인다.\n\n계산할 수 없는 날씨·행사 feature 중요도로 순위를 꾸미지 않았다. 현 호출 예산의 220분 주기는 기준선과 1~3시간 평가 확보를 보장하지 않는다.')]
    sections[8] = (sections[8][0], sections[8][1]+'\n\n'+fit_table+'\n'+performance_table)
    sections[9] = (sections[9][0], sections[9][1]+'\n\n시간 평가 log-MAE 진단:\n\n'+ablation_table)
    return '# 기존 데이터 기반 모델 선정 보고서\n\n구현 검증의 최신 실행 증거는 [단계별 검증 완료 보고서](VALIDATION_COMPLETION_REPORT.md)를 참고한다.\n\n'+ '\n\n'.join(f'## {i}. {title}\n\n{body}' for i, (title, body) in enumerate(sections, 1))+'\n'


def protected_hashes():
    paths = list((ROOT/'tourist_congestion_backend').rglob('*.py'))
    paths += list((ROOT/'tourist_congestion_backend').glob('*.sqlite3'))
    paths += list((ROOT/'tourist_congestion_backend').glob('.env*'))
    return {str(p.relative_to(ROOT)): digest(p) for p in paths if '__pycache__' not in p.parts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path(__file__).parent/'results')
    args = parser.parse_args()
    def deny_network(*args, **kwargs):
        raise AssertionError('Network is forbidden in this offline experiment')
    socket.socket.connect = deny_network
    socket.socket.connect_ex = deny_network
    before = protected_hashes()
    start = time.perf_counter()
    rows, manifest = audit()
    loading = time.perf_counter()-start
    assert manifest['forward_pairs'] == 0
    results, timings, split_manifest, checks = experiments(rows)
    heuristic = heuristic_replay()
    assert before == protected_hashes(), 'Protected production files changed during experiment'
    args.output.mkdir(parents=True, exist_ok=True)
    timing = {'environment': {'python': platform.python_version(), 'numpy': np.__version__, 'platform': platform.platform()},
              'audit_and_loading_seconds': loading, 'models': timings}
    output = {'manifest.json': manifest, 'observations.json': {'tag': TAG, 'rows': rows}, 'splits.json': split_manifest,
              'metrics.json': results, 'timings.json': timing, 'heuristic.json': heuristic,
              'synthetic_checks.json': {'is_training_data': False, 'checks': checks, 'protected_files_unchanged': True,
                                       'forward_pairs_zero': True},
              'deferred.json': {n: {'status': 'DEFERRED_INSUFFICIENT_VALIDATION', 'metrics': None} for n in ('random_forest', 'gradient_boosting', 'mlp', 'embedding')}}
    for name, value in output.items():
        (args.output/name).write_text(encode(value)+'\n', encoding='utf-8')
    (ROOT/'MODEL_SELECTION_REPORT.md').write_text(report(manifest, results, heuristic, timing), encoding='utf-8')
    print(encode({'population_rows': len(rows), 'fold_model_runs': len(results), 'forward_pairs': manifest['forward_pairs'],
                  'checks': len(checks), 'output': str(args.output)}))


if __name__ == '__main__':
    main()
