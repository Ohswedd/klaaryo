"""Idempotent bootstrap of Pub/Sub topics and subscriptions against the emulator.

Runs as a one-shot container at compose-up. Other services depend on this via
service_completed_successfully so they only start after topology is in place.
"""
import os
import sys
import time

from google.api_core.exceptions import AlreadyExists
from google.cloud import pubsub_v1


TOPICS = ["candidate.received", "candidate.routed"]

SUBSCRIPTIONS = [
    ("routing.candidate-received-sub", "candidate.received"),
    ("gateway.candidate-routed-sub", "candidate.routed"),
]


def wait_for_emulator(publisher, project_id, attempts=5, delay=2):
    last_err = None
    for attempt in range(1, attempts + 1):
        try:
            list(publisher.list_topics(request={"project": f"projects/{project_id}"}))
            return
        except Exception as e:
            last_err = e
            print(f"emulator not ready (attempt {attempt}/{attempts}): {e}", flush=True)
            time.sleep(delay)
    raise RuntimeError(f"emulator unreachable after {attempts} attempts: {last_err}")


def main():
    project_id = os.environ["PUBSUB_PROJECT_ID"]
    emulator = os.environ["PUBSUB_EMULATOR_HOST"]
    print(f"bootstrap pubsub: emulator={emulator} project={project_id}", flush=True)

    publisher = pubsub_v1.PublisherClient()
    subscriber = pubsub_v1.SubscriberClient()

    wait_for_emulator(publisher, project_id)

    for topic in TOPICS:
        path = publisher.topic_path(project_id, topic)
        try:
            publisher.create_topic(request={"name": path})
            print(f"created topic {topic}", flush=True)
        except AlreadyExists:
            print(f"topic {topic} already exists", flush=True)

    for sub_name, topic in SUBSCRIPTIONS:
        sub_path = subscriber.subscription_path(project_id, sub_name)
        topic_path = publisher.topic_path(project_id, topic)
        try:
            subscriber.create_subscription(
                request={"name": sub_path, "topic": topic_path}
            )
            print(f"created subscription {sub_name} -> {topic}", flush=True)
        except AlreadyExists:
            print(f"subscription {sub_name} already exists", flush=True)

    print("bootstrap done", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"bootstrap failed: {e}", file=sys.stderr, flush=True)
        sys.exit(1)
