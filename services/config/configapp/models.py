from django.db import models
from django.db.models import F


class Client(models.Model):
    # String PK: client_id is a stable business identifier (e.g. "pizzeria_demo")
    # propagated across services in events and gRPC. Surrogate int would force a
    # lookup just to map externally-known IDs.
    id = models.CharField(max_length=64, primary_key=True)
    name = models.CharField(max_length=255)
    routing_strategy = models.CharField(max_length=64)

    class Meta:
        db_table = "client"
        ordering = ["name"]

    def __str__(self):
        return f"{self.id} ({self.routing_strategy})"


class LocationQuerySet(models.QuerySet):
    def with_available_capacity(self):
        return self.filter(current_load__lt=F("max_capacity"))


class Location(models.Model):
    id = models.CharField(max_length=64, primary_key=True)
    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, related_name="locations"
    )
    name = models.CharField(max_length=255)
    city = models.CharField(max_length=64)
    max_capacity = models.IntegerField()
    current_load = models.IntegerField(default=0)
    priority = models.IntegerField(default=0)

    objects = LocationQuerySet.as_manager()

    class Meta:
        db_table = "location"
        ordering = ["client", "priority"]

    def __str__(self):
        return f"{self.id} ({self.city}, {self.current_load}/{self.max_capacity})"


class LocationOpening(models.Model):
    location = models.ForeignKey(
        Location, on_delete=models.CASCADE, related_name="openings"
    )
    role = models.CharField(max_length=64)
    is_open = models.BooleanField(default=True)

    class Meta:
        db_table = "location_opening"
        unique_together = [("location", "role")]

    def __str__(self):
        suffix = "" if self.is_open else " (closed)"
        return f"{self.location_id}:{self.role}{suffix}"
