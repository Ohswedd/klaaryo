from django.db import models


class ProcessedEvent(models.Model):
    # Idempotency mark: a row here means the event_id has been processed.
    # UNIQUE on PK guarantees at-most-once decision even under Pub/Sub redelivery.
    event_id = models.UUIDField(primary_key=True)
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "processed_event"

    def __str__(self):
        return f"ProcessedEvent {self.event_id} at {self.processed_at.isoformat()}"


class RoutingDecision(models.Model):
    candidate_id = models.UUIDField(primary_key=True)
    client_id = models.CharField(max_length=64, db_index=True)
    extracted_role = models.CharField(max_length=64, null=True, blank=True)
    extracted_city = models.CharField(max_length=64, null=True, blank=True)
    status = models.CharField(max_length=32)
    selected_location_id = models.CharField(max_length=64, null=True, blank=True)
    reason = models.TextField()
    decided_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "routing_decision"
        ordering = ["-decided_at"]
        indexes = [
            models.Index(fields=["client_id", "-decided_at"]),
        ]

    def __str__(self):
        return (
            f"RoutingDecision {self.candidate_id} [{self.client_id}] "
            f"{self.status} -> {self.selected_location_id or 'none'}"
        )
