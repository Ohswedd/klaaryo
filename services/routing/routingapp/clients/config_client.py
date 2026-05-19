import logging

import grpc
from django.conf import settings

from routingapp.grpc_gen import client_config_pb2, client_config_pb2_grpc


logger = logging.getLogger(__name__)


class ConfigServiceError(Exception):
    pass


_channel = None


# channel reuse: TCP+HTTP2 handshake is expensive, one per process
def get_channel():
    global _channel
    if _channel is None:
        _channel = grpc.insecure_channel(settings.CONFIG_GRPC_ADDR)
    return _channel


def _stub():
    return client_config_pb2_grpc.ClientConfigStub(get_channel())


# 2s: routing decision must fit within Pub/Sub ack deadline (10s default)
def get_client_routing_rules(client_id, timeout=2.0):
    try:
        return _stub().GetClientRoutingRules(
            client_config_pb2.GetClientRoutingRulesRequest(client_id=client_id),
            timeout=timeout,
        )
    except grpc.RpcError as e:
        logger.warning(
            f"GetClientRoutingRules({client_id}) failed: {e.code()}: {e.details()}"
        )
        raise ConfigServiceError(f"{e.code()}: {e.details()}") from e


def list_client_locations(client_id, timeout=2.0):
    try:
        response = _stub().ListClientLocations(
            client_config_pb2.ListClientLocationsRequest(client_id=client_id),
            timeout=timeout,
        )
        # Unwrap the proto repeated field here so business code stays decoupled
        # from the gRPC wire format.
        return response.locations
    except grpc.RpcError as e:
        logger.warning(
            f"ListClientLocations({client_id}) failed: {e.code()}: {e.details()}"
        )
        raise ConfigServiceError(f"{e.code()}: {e.details()}") from e
