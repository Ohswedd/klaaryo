import json
import logging
import uuid
from datetime import timezone

from django.conf import settings
from google.cloud import pubsub_v1


logger = logging.getLogger(__name__)


class PublishError(Exception):
    pass


_publisher = None


def get_publisher():
    # Lazy singleton: PublisherClient owns a connection pool; one per process.
    global _publisher
    if _publisher is None:
        _publisher = pubsub_v1.PublisherClient()
    return _publisher


def publish_candidate_received(candidate):
    publisher = get_publisher()
    topic_path = publisher.topic_path(
        settings.PUBSUB_PROJECT_ID, settings.PUBSUB_TOPIC_RECEIVED,
    )

    payload = {
        "schema_version": 1,
        "event_id": str(uuid.uuid4()),
        "candidate_id": str(candidate.id),
        "client_id": candidate.client_id,
        "raw_message": candidate.raw_message,
        "source": candidate.source,
        "received_at": candidate.created_at.astimezone(timezone.utc).isoformat(),
    }
    data = json.dumps(payload).encode("utf-8")

    try:
        future = publisher.publish(topic_path, data)
        message_id = future.result(timeout=5)
    except Exception as e:
        raise PublishError(f"failed to publish candidate.received: {e}") from e

    logger.info(
        f"published candidate.received event_id={payload['event_id']} "
        f"message_id={message_id}"
    )
    return message_id
