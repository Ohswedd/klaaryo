import random

from django.core.management.base import BaseCommand
from django.db import transaction

from configapp.models import Client, Location, LocationOpening


# Two clients with intentionally different routing_strategy values exercise
# both code paths in routing-service decision logic during the demo.
SEED = [
    {
        "id": "pizzeria_demo",
        "name": "Pizzeria Demo",
        "routing_strategy": "nearest_city",
        "locations": [
            {"id": "milano_01", "name": "Milano Navigli", "city": "Milano",
             "max_capacity": 10, "priority": 0,
             "roles": ["pizzaiolo", "cameriere"]},
            {"id": "roma_01", "name": "Roma Trastevere", "city": "Roma",
             "max_capacity": 10, "priority": 0,
             "roles": ["pizzaiolo", "cameriere"]},
            {"id": "torino_01", "name": "Torino Centro", "city": "Torino",
             "max_capacity": 10, "priority": 0,
             "roles": ["pizzaiolo", "cameriere"]},
        ],
    },
    {
        "id": "supermercato_demo",
        "name": "Supermercato Demo",
        "routing_strategy": "priority_based",
        "locations": [
            {"id": "milano_02", "name": "Milano Centrale", "city": "Milano",
             "max_capacity": 8, "priority": 10,
             "roles": ["cassiere", "scaffalista"]},
            {"id": "milano_03", "name": "Milano Porta Romana", "city": "Milano",
             "max_capacity": 8, "priority": 5,
             "roles": ["cassiere", "scaffalista"]},
        ],
    },
]


class Command(BaseCommand):
    help = (
        "Seed two demo clients (pizzeria_demo, supermercato_demo) with locations "
        "and openings covering both nearest_city and priority_based strategies. "
        "Idempotent: safe to re-run; current_load is randomized 0-3 each time."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        for spec in SEED:
            client, _ = Client.objects.update_or_create(
                id=spec["id"],
                defaults={
                    "name": spec["name"],
                    "routing_strategy": spec["routing_strategy"],
                },
            )
            for loc in spec["locations"]:
                location, _ = Location.objects.update_or_create(
                    id=loc["id"],
                    defaults={
                        "client": client,
                        "name": loc["name"],
                        "city": loc["city"],
                        "max_capacity": loc["max_capacity"],
                        "current_load": random.randint(0, 3),
                        "priority": loc["priority"],
                    },
                )
                for role in loc["roles"]:
                    LocationOpening.objects.update_or_create(
                        location=location,
                        role=role,
                        defaults={"is_open": True},
                    )
            self.stdout.write(self.style.SUCCESS(
                f"seeded {client.id} ({spec['routing_strategy']}, "
                f"{len(spec['locations'])} locations)"
            ))

        self.stdout.write(self.style.SUCCESS("seed_data complete"))
