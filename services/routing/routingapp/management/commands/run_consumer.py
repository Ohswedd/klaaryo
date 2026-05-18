import json
import logging
import signal

import django
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Subscribe to routing.candidate-received-sub and dispatch each event to "
        "handle_candidate_received. Blocks until SIGTERM/SIGINT."
    )

    def handle(self, *args, **options):
        # django.setup() before importing handlers: they touch the ORM.
        django.setup()
        from django.conf import settings
        from google.cloud import pubsub_v1

        from routingapp.handlers import handle_candidate_received

        logger = logging.getLogger(__name__)

        subscriber = pubsub_v1.SubscriberClient()
        sub_path = subscriber.subscription_path(
            settings.PUBSUB_PROJECT_ID,
            settings.PUBSUB_SUBSCRIPTION_RECEIVED,
        )

        def callback(message):
            try:
                payload = json.loads(message.data.decode("utf-8"))
                handle_candidate_received(payload)
                message.ack()
            except Exception as e:
                logger.exception(f"handler failed, nack: {e}")
                message.nack()

        future = subscriber.subscribe(sub_path, callback=callback)

        self.stdout.write(self.style.SUCCESS(
            f"Listening on subscription {settings.PUBSUB_SUBSCRIPTION_RECEIVED}"
        ))

        def _shutdown(signum, frame):
            self.stdout.write(self.style.WARNING(
                f"signal {signum} received, cancelling subscription"
            ))
            future.cancel()

        signal.signal(signal.SIGTERM, _shutdown)
        signal.signal(signal.SIGINT, _shutdown)

        try:
            future.result()
        except Exception as e:
            logger.info(f"consumer stopped: {e}")
