"""Read-only, fixed-ID development/holdout snapshot for exposure classification."""

import json

from django.core.management.base import BaseCommand

from places.models import Place, PlaceInfo
from places.services.classification import current_description_evidence, name_decision
from places.services.description_classification import classify_description


# Development labels were fixed by the reviewer before v2 rules were edited.
DEV_EXPECTED = {
    3997: 'outdoor', 28656: 'outdoor', 45367: 'outdoor', 25349: 'mixed',
    39603: 'mixed', 27051: 'indoor', 26220: 'mixed', 42070: 'outdoor',
    11357: 'indoor', 34931: 'indoor', 38914: 'indoor', 31488: 'indoor',
    8489: 'outdoor', 2565: 'mixed', 3184: 'mixed', 29634: 'indoor',
    30: 'mixed', 2687: 'mixed', 31471: 'indoor', 1213: 'indoor',
}
# Holdout labels deliberately do not live in this repository or command.
HOLDOUT_IDS = (
    41298, 42481, 9571, 12040, 19457, 9065, 36314, 10374, 29977,
    18194, 32583, 2906, 30746, 19042, 11293, 24241, 40448, 824,
    883, 2346,
)


class Command(BaseCommand):
    help = 'Print read-only fixed 20+20 exposure evaluation; never calls AI or writes data.'

    def add_arguments(self, parser):
        parser.add_argument('--cohort', choices=('dev', 'holdout', 'all'), default='all')

    def handle(self, *args, **options):
        cohort = options['cohort']
        ids = (list(DEV_EXPECTED) if cohort in {'dev', 'all'} else []) + (
            list(HOLDOUT_IDS) if cohort in {'holdout', 'all'} else [])
        places = Place.objects.filter(id__in=ids).select_related('info', 'classification_record')
        by_id = {place.id: place for place in places}
        for place_id in ids:
            place = by_id.get(place_id)
            if place is None:
                self.stdout.write(json.dumps({'id': place_id, 'missing': True}))
                continue
            try:
                description = place.info.description
            except PlaceInfo.DoesNotExist:
                description = ''
            rule = classify_description(place.name, place.category, description)
            if rule is not None:
                predicted, method = rule.label, 'description_rule'
            elif place.indoor_outdoor_source == 'luna_validated' and current_description_evidence(place):
                predicted, method = place.indoor_outdoor, 'luna_validated'
            else:
                name = name_decision(place)
                predicted, method = ((name[0], name[1]) if name else ('unknown', ''))
            row = {'cohort': 'dev' if place_id in DEV_EXPECTED else 'holdout',
                   'id': place_id, 'name': place.name, 'stored': place.indoor_outdoor,
                   'stored_source': place.indoor_outdoor_source,
                   'rule': rule.label if rule else None,
                   'effective': predicted, 'method': method}
            if place_id in DEV_EXPECTED:
                row['expected'] = DEV_EXPECTED[place_id]
                row['match'] = predicted == row['expected']
            self.stdout.write(json.dumps(row, ensure_ascii=False))
