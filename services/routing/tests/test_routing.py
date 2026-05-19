import uuid
from unittest.mock import Mock, patch

import pytest

from routingapp.clients.config_client import ConfigServiceError
from routingapp.handlers import handle_candidate_received
from routingapp.models import ProcessedEvent, RoutingDecision


def _locations(roles, current_load=0, max_capacity=10):
    return [
        Mock(id="milano_01", city="Milano", open_roles=roles,
             current_load=current_load, max_capacity=max_capacity, priority=0),
        Mock(id="roma_01", city="Roma", open_roles=roles,
             current_load=current_load, max_capacity=max_capacity, priority=0),
        Mock(id="torino_01", city="Torino", open_roles=roles,
             current_load=current_load, max_capacity=max_capacity, priority=0),
    ]


def _payload(client_id="pizzeria_demo", raw_message="cerco lavoro come pizzaiolo a Milano"):
    return {
        "event_id": str(uuid.uuid4()),
        "candidate_id": str(uuid.uuid4()),
        "client_id": client_id,
        "raw_message": raw_message,
        "source": "whatsapp",
        "received_at": "2026-05-19T00:00:00Z",
    }


@pytest.mark.django_db
@patch("routingapp.handlers.publish_candidate_routed")
@patch("routingapp.handlers.list_client_locations")
@patch("routingapp.handlers.get_client_routing_rules")
def test_routing_scenario_a_nominal(mock_client, mock_locs, mock_publish):
    """Scenario A: nearest_city strategy routes to milano_01 on extracted city match."""
    mock_client.return_value = Mock(id="pizzeria_demo", routing_strategy="nearest_city")
    mock_locs.return_value = _locations(["pizzaiolo"])

    payload = _payload()
    handle_candidate_received(payload)

    decision = RoutingDecision.objects.get(candidate_id=payload["candidate_id"])
    assert decision.status == "routed"
    assert decision.selected_location_id == "milano_01"
    assert decision.extracted_role == "pizzaiolo"
    assert decision.extracted_city == "Milano"

    assert mock_publish.call_count == 1
    published = mock_publish.call_args[0][0]
    assert published["status"] == "routed"
    assert published["selected_location_id"] == "milano_01"
    assert published["candidate_id"] == payload["candidate_id"]


@pytest.mark.django_db
@patch("routingapp.handlers.publish_candidate_routed")
@patch("routingapp.handlers.list_client_locations")
@patch("routingapp.handlers.get_client_routing_rules")
def test_routing_scenario_b_no_capacity(mock_client, mock_locs, mock_publish):
    """Scenario B: all locations saturated (current_load == max_capacity) → no_routing_available."""
    mock_client.return_value = Mock(id="pizzeria_demo", routing_strategy="nearest_city")
    mock_locs.return_value = _locations(["pizzaiolo"], current_load=10, max_capacity=10)

    payload = _payload()
    handle_candidate_received(payload)

    decision = RoutingDecision.objects.get(candidate_id=payload["candidate_id"])
    assert decision.status == "no_routing_available"
    assert "no location" in decision.reason


@pytest.mark.django_db
@patch("routingapp.handlers.publish_candidate_routed")
@patch("routingapp.handlers.list_client_locations")
@patch("routingapp.handlers.get_client_routing_rules")
def test_routing_scenario_c_multitenancy(mock_client, mock_locs, mock_publish):
    """Scenario C: two tenants with different configs route independently and coherently."""
    pizzeria_locs = _locations(["pizzaiolo"])
    supermercato_locs = [
        Mock(id="milano_02", city="Milano", open_roles=["cassiere"],
             current_load=0, max_capacity=8, priority=10),
        Mock(id="milano_03", city="Milano", open_roles=["cassiere"],
             current_load=0, max_capacity=8, priority=5),
    ]
    mock_client.side_effect = lambda cid, timeout=2.0: Mock(
        id=cid,
        routing_strategy="nearest_city" if cid == "pizzeria_demo" else "priority_based",
    )
    mock_locs.side_effect = lambda cid, timeout=2.0: (
        pizzeria_locs if cid == "pizzeria_demo" else supermercato_locs
    )

    p1 = _payload(client_id="pizzeria_demo", raw_message="pizzaiolo a Milano")
    p2 = _payload(client_id="supermercato_demo", raw_message="cassiere a Milano")
    handle_candidate_received(p1)
    handle_candidate_received(p2)

    d1 = RoutingDecision.objects.get(candidate_id=p1["candidate_id"])
    d2 = RoutingDecision.objects.get(candidate_id=p2["candidate_id"])
    assert d1.client_id == "pizzeria_demo" and d1.selected_location_id == "milano_01"
    assert d2.client_id == "supermercato_demo" and d2.selected_location_id == "milano_02"


@pytest.mark.django_db
@patch("routingapp.handlers.publish_candidate_routed")
@patch("routingapp.handlers.list_client_locations")
@patch("routingapp.handlers.get_client_routing_rules")
def test_idempotency_duplicate_event(mock_client, mock_locs, mock_publish):
    """Idempotency: same event_id processed twice → single ProcessedEvent + RoutingDecision + publish."""
    mock_client.return_value = Mock(id="pizzeria_demo", routing_strategy="nearest_city")
    mock_locs.return_value = _locations(["pizzaiolo"])

    payload = _payload()
    handle_candidate_received(payload)
    handle_candidate_received(payload)

    assert ProcessedEvent.objects.filter(event_id=payload["event_id"]).count() == 1
    assert RoutingDecision.objects.filter(candidate_id=payload["candidate_id"]).count() == 1
    assert mock_publish.call_count == 1


@pytest.mark.django_db
@patch("routingapp.handlers.publish_candidate_routed")
@patch("routingapp.handlers.list_client_locations")
@patch("routingapp.handlers.get_client_routing_rules")
def test_config_service_unavailable(mock_client, mock_locs, mock_publish):
    """gRPC failure: ConfigServiceError yields config_service_unavailable status; handler does not crash."""
    mock_client.return_value = Mock(id="pizzeria_demo", routing_strategy="nearest_city")
    mock_locs.side_effect = ConfigServiceError("StatusCode.UNAVAILABLE: config service down")

    payload = _payload()
    handle_candidate_received(payload)

    decision = RoutingDecision.objects.get(candidate_id=payload["candidate_id"])
    assert decision.status == "config_service_unavailable"
    assert "config service unreachable" in decision.reason
    assert mock_publish.call_count == 1
