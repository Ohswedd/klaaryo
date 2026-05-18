import logging

from gatewayapp.models import Candidate


logger = logging.getLogger(__name__)


def update_candidate_from_routed(payload):
    candidate_id = payload["candidate_id"]

    try:
        candidate = Candidate.objects.get(id=candidate_id)
    except Candidate.DoesNotExist:
        logger.warning(f"candidate.routed for unknown id={candidate_id}, dropping")
        return

    # Idempotent transition: only the first non-'received' update wins. Pub/Sub
    # redelivers are no-ops once status has moved past 'received'.
    if candidate.status != "received":
        logger.info(
            f"candidate {candidate_id} already at status={candidate.status}, skip"
        )
        return

    candidate.status = payload["status"]
    if payload.get("selected_location_id"):
        candidate.routing_location_id = payload["selected_location_id"]
    if payload.get("reason"):
        candidate.routing_reason = payload["reason"]
    candidate.save(update_fields=[
        "status", "routing_location_id", "routing_reason", "updated_at",
    ])

    logger.info(
        f"candidate {candidate_id} -> status={candidate.status} "
        f"loc={candidate.routing_location_id}"
    )
