import uuid

from django.db import models


class Candidate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client_id = models.CharField(max_length=64, db_index=True)
    raw_message = models.TextField()
    source = models.CharField(max_length=32, default="whatsapp")
    status = models.CharField(max_length=32, default="received")
    routing_location_id = models.CharField(max_length=64, null=True, blank=True)
    routing_reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "candidate"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["client_id", "-created_at"]),
        ]

    def __str__(self):
        return f"Candidate {self.id} [{self.client_id}] {self.status}"
