import json
import logging
import signal

import django
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Subscribe to gateway.candidate-routed-sub and apply routing outcomes "
        "to Candidate.status. Idempotent; blocks until SIGTERM/SIGINT."
    )

    def handle(self, *args, **options):
        # django.setup() before importing app modules that touch the ORM.
        django.setup()
        from django.conf import settings
        from google.cloud import pubsub_v1

        from gatewayapp.handlers import update_candidate_from_routed

        logger = logging.getLogger(__name__)

        subscriber = pubsub_v1.SubscriberClient()
        sub_path = subscriber.subscription_path(
            settings.PUBSUB_PROJECT_ID,
            settings.PUBSUB_SUBSCRIPTION_ROUTED,
        )

        def callback(message):
            try:
                payload = json.loads(message.data.decode("utf-8"))
                update_candidate_from_routed(payload)
                message.ack()
            except Exception as e:
                logger.exception(f"handler failed, nack: {e}")
                message.nack()

        future = subscriber.subscribe(sub_path, callback=callback)

        self.stdout.write(self.style.SUCCESS(
            f"gateway consumer subscribed to {settings.PUBSUB_SUBSCRIPTION_ROUTED}"
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
