import logging
import signal
import sys
from concurrent import futures

import django
import grpc
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Start the gRPC server for client-config-service on 0.0.0.0:<port>. "
        "Blocks until SIGTERM/SIGINT, then drains for up to 5 seconds."
    )

    def add_arguments(self, parser):
        parser.add_argument("--port", type=int, default=50051)

    def handle(self, *args, **options):
        port = options["port"]

        # django.setup() before importing the servicer module: the servicer
        # imports models at top level and would fail if apps aren't ready.
        django.setup()
        from configapp.grpc_server import add_servicers

        logging.basicConfig(
            level=logging.INFO,
            format="%(message)s",
            stream=sys.stdout,
        )

        server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        add_servicers(server)
        server.add_insecure_port(f"0.0.0.0:{port}")
        server.start()

        self.stdout.write(self.style.SUCCESS(
            f"gRPC server listening on 0.0.0.0:{port}"
        ))

        def _shutdown(signum, frame):
            self.stdout.write(self.style.WARNING(
                f"signal {signum} received, draining (grace=5s)"
            ))
            server.stop(grace=5)

        signal.signal(signal.SIGTERM, _shutdown)
        signal.signal(signal.SIGINT, _shutdown)

        server.wait_for_termination()
