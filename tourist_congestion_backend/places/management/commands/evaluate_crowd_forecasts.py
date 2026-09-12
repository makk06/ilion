import json
from django.core.management.base import BaseCommand
from places.services.crowd_evaluation import evaluate_forecasts


class Command(BaseCommand):
    help = 'Evaluate frozen forecasts against later actual area observations.'

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(evaluate_forecasts(),ensure_ascii=False))
