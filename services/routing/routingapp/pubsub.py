import json
import logging

from django.conf import settings
from google.cloud import pubsub_v1


logger = logging.getLogger(__name__)


_publisher = None


def get_publisher():
    global _publisher
    if _publisher is None:
        _publisher = pubsub_v1.PublisherClient()
    return _publisher


def publish_candidate_routed(payload):
    publisher = get_publisher()
    topic_path = publisher.topic_path(
        settings.PUBSUB_PROJECT_ID, settings.PUBSUB_TOPIC_ROUTED,
    )
    data = json.dumps(payload).encode("utf-8")

    try:
        future = publisher.publish(topic_path, data)
        message_id = future.result(timeout=5)
        logger.info(
            f"published candidate.routed event_id={payload.get('event_id')} "
            f"message_id={message_id}"
        )
    except Exception as e:
        # decision is persisted; downstream pipeline can reconcile from routing_decision table
        logger.error(f"failed to publish candidate.routed: {e}")
