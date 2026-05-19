import logging
from datetime import datetime, timezone

from django.db import IntegrityError, transaction

from routingapp.models import ProcessedEvent, RoutingDecision
from routingapp.extraction import extract_fields
from routingapp.decision import decide_routing
from routingapp.clients.config_client import (
    ConfigServiceError,
    get_client_routing_rules,
    list_client_locations,
)
from routingapp.pubsub import publish_candidate_routed


logger = logging.getLogger(__name__)


def handle_candidate_received(payload):
    event_id = payload['event_id']

    # at-least-once Pub/Sub semantics require event-level dedup.
    # atomic() isolates the failing INSERT so an IntegrityError doesn't poison
    # an outer transaction (canonical Django try-INSERT-catch-dup pattern).
    try:
        with transaction.atomic():
            ProcessedEvent.objects.create(event_id=event_id)
    except IntegrityError:
        logger.info("duplicate event_id %s, skipping", event_id)
        return

    extracted = extract_fields(payload['raw_message'])

    try:
        client = get_client_routing_rules(payload['client_id'])
        locations = list_client_locations(payload['client_id'])
        decision = decide_routing(
            client, locations, extracted['role'], extracted['city']
        )
    except ConfigServiceError as e:
        decision = {
            "status": "config_service_unavailable",
            "selected_location_id": None,
            "reason": f"config service unreachable: {e}",
        }

    with transaction.atomic():
        RoutingDecision.objects.create(
            candidate_id=payload['candidate_id'],
            client_id=payload['client_id'],
            extracted_role=extracted['role'],
            extracted_city=extracted['city'],
            status=decision['status'],
            selected_location_id=decision['selected_location_id'],
            reason=decision['reason'],
        )
        # NOTE: current_load increment NOT done here to avoid cross-service DB write.
        # In production, emit a separate 'location.capacity_consumed' event for
        # config-service to handle with F() expression. See PRD section 3.8.

    publish_candidate_routed({
        'schema_version': 1,
        'event_id': event_id,
        'candidate_id': payload['candidate_id'],
        'client_id': payload['client_id'],
        'status': decision['status'],
        'selected_location_id': decision['selected_location_id'],
        'extracted_role': extracted['role'],
        'extracted_city': extracted['city'],
        'reason': decision['reason'],
        'decided_at': datetime.now(timezone.utc).isoformat(),
    })

    logger.info(
        "routed candidate_id=%s status=%s location=%s",
        payload['candidate_id'], decision['status'], decision['selected_location_id'],
    )
