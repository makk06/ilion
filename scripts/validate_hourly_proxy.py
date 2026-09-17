"""Read-only replay of already examined living-population data; never imports evidence.

python scripts/validate_hourly_proxy.py --input population.csv --output output/proxy
"""
import argparse
import csv
import hashlib
import json
import os
import sys
from datetime import timedelta
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tourist_congestion_backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
from django.conf import settings
settings.DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
django.setup()
from places.services.hourly_forecast import predict, dt, PARAMETERS, VERSION
from places.services.mean_validation import assess, metrics
from places.services.hourly_reporting import export_report
from places.services.hourly_decisions import distribution, annotate, assess_decisions, CONTRACT

START = dt('2026-03-01T00:00:00+09:00')
TUNE, TEST, END = START+timedelta(days=56), START+timedelta(days=70), dt('2026-06-01T00:00:00+09:00')
HOLIDAYS = {'2026-03-01', '2026-03-02', '2026-05-05', '2026-05-24', '2026-05-25'}
AREAS = ('11110530', '11110540', '11110600')


def key(p):
    return f"half={p['half_life']};tau={p['tau']}"


def run(input_path, output):
    series = {a: {} for a in AREAS}
    names = {}
    with Path(input_path).open(encoding='utf-8-sig', newline='') as stream:
        for r in csv.DictReader(stream):
            a, at, value = r['area_id'], dt(r['observed_at']), float(r['population'])
            if a not in series:
                continue
            if at in series[a] or not 0 <= value < float('inf'):
                raise ValueError('Duplicate or invalid source observation')
            series[a][at] = value
            names[a] = r['area_name']
    if any(len(v) != 92*24 or any(START+timedelta(hours=i) not in v for i in range(92*24)) for v in series.values()):
        raise ValueError('Expected the original complete March-May 2026 cohort')
    calendar = {(START+timedelta(days=i)).date().isoformat(): (START+timedelta(days=i)).date().isoformat() in HOLIDAYS for i in range(93)}
    sources = {a: {'provider': 'seoul', 'external_id': a, 'metric': 'population_count', 'calendar': calendar,
                  # Hypothetical instantaneous availability, in memory ONLY. Not actual receipt evidence.
                  'observations': [{'observed_at': t, 'received_at': t, 'value': v} for t, v in values.items()]}
               for a, values in series.items()}
    scales = {a: mean(v for t, v in values.items() if START <= t < TUNE) for a, values in series.items()}
    peaks = {a: sorted(v for t, v in values.items() if START <= t < TUNE)[int(.9*(56*24-1))] for a, values in series.items()}

    def generate(start, end, params, scenario='normal'):
        rows = []
        for a, original in sources.items():
            at = start
            while at+timedelta(hours=3) < end:
                source = original
                if scenario != 'normal':
                    # Change only availability at issuance; keep independent future truth intact.
                    age = 0 if scenario == 'current_missing' else 1
                    source = {**original, 'observations': [r for r in original['observations'] if r['observed_at'] < at-timedelta(hours=age)]}
                dist = distribution(source, at)
                for f in predict(source, at, params):
                    valid = dt(f['valid_at'])
                    tag = 'holiday' if calendar[valid.date().isoformat()] else 'weekend' if valid.weekday() >= 5 else 'weekday'
                    rows.append(annotate({'area_id': a, 'issued_at': f['issued_at'], 'valid_at': f['valid_at'],
                                 'provider': 'seoul_living_population_proxy', 'external_id': a,
                                 'metric': 'population_count', 'unit': 'persons', 'scope': 'administrative_dong_domestic_population',
                                 'hours_ahead': f['hours_ahead'], 'population': f['value'],
                                 'actual': series[a].get(valid), **f['comparisons'],
                                 'parameters': f['parameters'], 'reasons': f['reasons'], 'tags': [tag]}, dist))
                at += timedelta(hours=1)
        return rows

    choices = {}
    for i, p in enumerate(PARAMETERS, 1):
        choices[key(p)] = generate(TUNE, TEST, p)
        print(f'Selection {i}/16 {key(p)}', flush=True)
    good = [i for i in range(len(next(iter(choices.values())))) if all(
        all(rs[i].get(k) is not None for k in ('population', 'actual', 'arithmetic', 'weekly', 'persistence')) for rs in choices.values())]
    scores = {k: metrics([rs[i] for i in good], 'population', scales, peaks)['nmae'] for k, rs in choices.items()}
    decision_selection = {k: assess_decisions([rs[i] for i in good], peaks, AREAS) for k, rs in choices.items()}
    safe = [p for p in PARAMETERS if decision_selection[key(p)]['guidance']['status'] == 'PASS']
    rank_safe = [p for p in safe if decision_selection[key(p)]['ranking']['status'] == 'PASS']
    winner = min(rank_safe or safe or PARAMETERS, key=lambda p: (scores[key(p)], sum(v is not None for v in p.values()), key(p)))
    basic = [next(iter(choices.values()))[i] for i in good]
    refs = {k: metrics(basic, k, scales, peaks)['nmae'] for k in ('arithmetic', 'weekly', 'persistence')}
    refs.update({key(p): scores[key(p)] for p in PARAMETERS if p['tau'] is None})
    reference = min(refs, key=lambda k: (refs[k], k))
    recent = min((p for p in PARAMETERS if p['tau'] is None and p['half_life'] is not None), key=lambda p: (scores[key(p)], key(p)))
    rows = generate(TEST, END, winner)
    recent_rows = generate(TEST, END, recent)
    ref_params = next((p for p in PARAMETERS if key(p) == reference), None)
    reference_rows = generate(TEST, END, ref_params) if ref_params else None
    for i, r in enumerate(rows):
        r['reference'] = reference_rows[i]['population'] if reference_rows else r[reference]
        r['recent'] = recent_rows[i]['population']
    report = assess(rows, list(AREAS), scales, peaks, reference='reference', required_areas=None,
                    date_field='valid_at', strict_coverage=True, relative_peak_threshold=CONTRACT['very_busy_above'])
    report['numerical_gate'] = report['status']
    report['usability'] = assess_decisions(rows, peaks, AREAS)
    report['decision_selection'] = decision_selection
    report['selection_guidance_pass'] = bool(safe)
    report['selection_ranking_pass'] = bool(rank_safe)
    report['decision_contract_version'] = CONTRACT['version']
    report.update(status='AUXILIARY_ONLY', evaluation_kind='previously_examined_retrospective_proxy',
                  reasons=['Previously examined holdout; no independent confirmation.',
                           'Receipt timestamps are hypothetical in-memory availability, never operational evidence.',
                           'Administrative dong domestic population; not tourism area counts or TMAP density.'],
                  parameters=winner, reference=reference, recent_parameters=recent, selection_scores=scores,
                  reference_scores=refs, model_version=VERSION, provider='seoul_living_population_proxy',
                  metric='population_count', unit='persons', areas=names, scales=scales, peaks=peaks,
                  input_sha256=hashlib.sha256(Path(input_path).read_bytes()).hexdigest(),
                  model_sha256=hashlib.sha256((Path(__file__).resolve().parents[1]/'tourist_congestion_backend/places/services/hourly_forecast.py').read_bytes()).hexdigest(),
                  periods={'training': [str(START), str(TUNE)], 'selection': [str(TUNE), str(TEST)], 'evaluation': [str(TEST), str(END)]})
    report['metrics']['value'] = report['metrics'].pop('population')
    report['sensitivity'] = {}
    for scenario in ('current_missing', 'one_hour_delay'):
        varied = generate(TEST, END, winner, scenario)
        report['sensitivity'][scenario] = metrics(varied, 'population', scales, peaks)
        export_report(Path(output)/scenario, {'status': 'SENSITIVITY_ONLY', 'evaluation_kind': scenario,
                      'metrics': {'value': report['sensitivity'][scenario]}}, varied)
        print(f'Sensitivity {scenario} complete', flush=True)
    export_report(output, report, rows)
    print(json.dumps({'status': report['status'], 'parameters': winner, 'nmae': report['metrics']['value']['nmae']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    run(args.input, args.output)
