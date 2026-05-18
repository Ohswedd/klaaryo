class ConfigServiceError(Exception):
    pass


def get_client_routing_rules(client_id):
    raise NotImplementedError("get_client_routing_rules: implemented in next phase")


def list_client_locations(client_id):
    raise NotImplementedError("list_client_locations: implemented in next phase")
