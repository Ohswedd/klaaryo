def decide_routing(client, locations, extracted_role, extracted_city):
    if extracted_role is None:
        return {
            "status": "extraction_failed",
            "selected_location_id": None,
            "reason": "could not extract role from raw_message",
        }

    eligible = [
        loc for loc in locations
        if extracted_role in loc.open_roles
        and loc.current_load < loc.max_capacity
    ]
    if not eligible:
        return {
            "status": "no_routing_available",
            "selected_location_id": None,
            "reason": (
                f"no location offers role={extracted_role} with spare capacity "
                f"(checked {len(locations)} locations)"
            ),
        }

    # City filter: prefer exact match; fallback to all eligible if no match.
    # Fallback rationale: if a candidate names a city we don't operate in, we
    # still route somewhere rather than fail — extraction is best-effort.
    if extracted_city is not None:
        city_matches = [loc for loc in eligible if loc.city == extracted_city]
        if city_matches:
            eligible = city_matches

    strategy = client.routing_strategy
    if strategy == "nearest_city":
        selected = _strategy_nearest_city(eligible)
    elif strategy == "priority_based":
        selected = _strategy_priority_based(eligible)
    elif strategy == "round_robin":
        selected = _strategy_round_robin(eligible)
    else:
        return {
            "status": "no_routing_available",
            "selected_location_id": None,
            "reason": f"unknown routing_strategy={strategy}",
        }

    return {
        "status": "routed",
        "selected_location_id": selected.id,
        "reason": (
            f"matched role={extracted_role} city={extracted_city or 'any'}, "
            f"strategy={strategy}, "
            f"capacity={selected.current_load}/{selected.max_capacity}"
        ),
    }


def _strategy_nearest_city(eligible):
    # City filter applied upstream; break ties on priority DESC.
    return sorted(eligible, key=lambda loc: -loc.priority)[0]


def _strategy_priority_based(eligible):
    return sorted(eligible, key=lambda loc: -loc.priority)[0]


def _strategy_round_robin(eligible):
    # Approximation: pick least-loaded as a proxy for "next in rotation".
    # True round-robin needs external state (e.g. Redis counter per client_id).
    return sorted(eligible, key=lambda loc: loc.current_load)[0]
