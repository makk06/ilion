"""56/14/14 day chronological selection and locked holdout. Synthetic data is never added."""
import itertools
from datetime import timedelta
from .mean_forecast import predict, dt, population, hourly
from .mean_study import dataset, label, annotate, frozen_scales
from .mean_validation import metrics, assess


def replay(datasets, start, end, parameters, available_at):
    result = []
    at = start
    while at < end:
        for area, data in datasets.items():
            for row in predict(data, at, parameters):
                annotate(row, data, at)
                actual = label(data, dt(row['valid_at']), available_at)
                result.append({**row, **row['comparisons'], 'actual': actual['value'] if actual else None})
        at += timedelta(hours=1)
    return result


def event_support(datasets, start, end, rows):
    """Require independent historical editions per family and a new held-out edition."""
    used = {(r['area_id'], family) for r in rows for family in r.get('target_families', [])}
    if not used:
        return False
    for area, family in used:
        past = set()
        for check in datasets[area].get('event_checks', []):
            if dt(check['received_at']) > start:
                continue
            for event in check['events']:
                if event['family'] == family and event['end_date'] < start.date().isoformat():
                    # An event catalog alone is insufficient: require population labels in its dates.
                    if any(event['start_date'] <= r['bucket'].date().isoformat() <= event['end_date']
                           for r in hourly(population(datasets[area]['population'], start))):
                        past.add(event['edition'])
        held = {edition for r in rows if r['area_id'] == area and family in r.get('target_families', [])
                for edition in r.get('target_editions', []) if r.get('actual') is not None}
        if len(past) < 3 or not held-past:
            return False
    return True


def run(study, now):
    areas = study.state.get('areas', [])
    start = dt(study.state.get('selection_at', (study.started_at+timedelta(days=7)).isoformat())).replace(minute=0, second=0, microsecond=0)
    selection_start, test_start, test_end = (start+timedelta(days=d) for d in (56, 70, 84))
    report = {'status': 'NEEDS_MORE_DATA', 'accuracy_validated': False, 'phase': 'forward_as_of',
              'split': {'train_start': start.isoformat(), 'selection_start': selection_start.isoformat(),
                        'test_start': test_start.isoformat(), 'test_end': test_end.isoformat()}}
    if len(areas) != 3 or now < test_end+timedelta(hours=27):
        report['reasons'] = ['requires_three_fixed_areas_and_84_days_plus_label_delay']
        return report
    datasets = {a: dataset(a, study.config['grids'][str(a)], now) for a in areas}
    # Exclude selection-week records from fixed scale and peak definitions.
    training = {a: {**data, 'population': [r for r in data['population'] if start <= dt(r['at']) < selection_start]}
                for a, data in datasets.items()}
    scales, peaks = frozen_scales(training, selection_start)
    if any(len(hourly(population(d['population'], selection_start))) < 56*24*.9 for d in training.values()):
        report['reasons'] = ['insufficient_training_coverage']
        return report
    choices = []
    for half, tau, weather, events in itertools.product((14, 28, 56), (None, .5, 1.5, 3), (False, True), (False, True)):
        params = {'half_life': half, 'tau': tau, 'weather': weather, 'events': events}
        rows = replay(datasets, selection_start, test_start, params, now)
        score = metrics(rows, 'population', scales, peaks)['nmae']
        if score is None:
            continue
        verified = event_support(datasets, selection_start, test_start, rows)
        if events and not verified:
            continue
        complexity = int(tau is not None)+int(weather)+int(events)
        choices.append((score, complexity, half, tau or 0, weather, events, params, rows))
    if not choices:
        report['reasons'] = ['no_eligible_selection_model']
        return report
    winner = min(choices, key=lambda r: r[:6])
    params, selection = winner[-2:]
    refs = ('weekly', 'persistence', 'arithmetic', 'recent', 'conditional')
    paired = [r for r in selection if all(r.get(f) is not None for f in (*refs, 'actual'))]
    if not paired:
        report['reasons'] = ['no_paired_reference_selection']
        return report
    reference = min(refs, key=lambda f: (metrics(paired, f, scales, peaks)['nmae'], refs.index(f)))
    # These weights/reference are chosen strictly before the holdout is inspected.
    held = replay(datasets, test_start, test_end, params, now)
    result = assess(held, areas, scales, peaks, reference, event_support(datasets, test_start, test_end, held))
    report.update(result, parameters=params, scales=scales, peaks=peaks,
                  selection_scores=[{'parameters': c[-2], 'nmae': c[0]} for c in choices],
                  accuracy_validated=result['status'] == 'PASS')
    return report
