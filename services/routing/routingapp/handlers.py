import logging


logger = logging.getLogger(__name__)


def handle_candidate_received(payload):
    # Scaffold: logs the payload. Real implementation (idempotency check,
    # extraction, gRPC config call, decision, publish) lands in next phase.
    logger.info(
        f"received candidate.received event_id={payload.get('event_id')} "
        f"candidate_id={payload.get('candidate_id')} "
        f"client_id={payload.get('client_id')}"
    )
