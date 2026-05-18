import logging
from datetime import datetime, timezone

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

from configapp.grpc_gen import client_config_pb2, client_config_pb2_grpc
from configapp.models import Client, Location


logger = logging.getLogger(__name__)


class ClientConfigServicer(client_config_pb2_grpc.ClientConfigServicer):

    def GetClientRoutingRules(self, request, context):
        _log_call("GetClientRoutingRules", request.client_id)
        try:
            client = Client.objects.get(id=request.client_id)
        except Client.DoesNotExist:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details("client not found")
            return client_config_pb2.Client()

        return client_config_pb2.Client(
            id=client.id,
            name=client.name,
            routing_strategy=client.routing_strategy,
        )

    def ListClientLocations(self, request, context):
        _log_call("ListClientLocations", request.client_id)
        # prefetch_related avoids N+1 over LocationOpening; openings are
        # filtered in Python from the cached relation.
        locations = (
            Location.objects
            .filter(client_id=request.client_id)
            .prefetch_related("openings")
        )

        response = client_config_pb2.ListClientLocationsResponse()
        for loc in locations:
            open_roles = [o.role for o in loc.openings.all() if o.is_open]
            response.locations.append(client_config_pb2.Location(
                id=loc.id,
                client_id=loc.client_id,
                name=loc.name,
                city=loc.city,
                max_capacity=loc.max_capacity,
                current_load=loc.current_load,
                priority=loc.priority,
                open_roles=open_roles,
            ))
        return response


def _log_call(method, client_id):
    ts = datetime.now(timezone.utc).isoformat()
    logger.info(f"ts={ts} method={method} client_id={client_id}")


def add_servicers(server):
    client_config_pb2_grpc.add_ClientConfigServicer_to_server(
        ClientConfigServicer(), server,
    )
    health_svc = health.HealthServicer()
    health_svc.set("", health_pb2.HealthCheckResponse.SERVING)
    health_svc.set(
        "klaaryo.config.v1.ClientConfig",
        health_pb2.HealthCheckResponse.SERVING,
    )
    health_pb2_grpc.add_HealthServicer_to_server(health_svc, server)
