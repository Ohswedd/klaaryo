#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

GATEWAY_URL="http://localhost:8000"

# ---------- helpers ----------

# Postgres superuser in this stack is 'klaaryo' (see docker-compose.yml). The
# prompt sketch used '-U postgres', but POSTGRES_USER=klaaryo so that fails.
sql_routing() {
    docker compose exec -T postgres psql -U klaaryo -d routing_db -c "$1"
}

sql_config() {
    docker compose exec -T postgres psql -U klaaryo -d config_db -c "$1"
}

post_candidate() {
    local client_id="$1"
    local raw_message="$2"
    local body
    body=$(printf '{"client_id":"%s","raw_message":"%s"}' "$client_id" "$raw_message")
    curl -fsS -X POST "$GATEWAY_URL/candidates" \
        -H "Content-Type: application/json" \
        -d "$body" \
    | python3 -c "import sys, json; print(json.load(sys.stdin)['candidate_id'])"
}

get_candidate() {
    curl -fsS "$GATEWAY_URL/candidates/$1" | python3 -m json.tool
}

# ---------- banner ----------

echo "================================================="
echo "  Klaaryo Smart Candidate Routing — Demo"
echo "================================================="
echo ""

# ---------- health check ----------

echo "Verifico che lo stack sia in esecuzione..."
REQUIRED=("config" "gateway" "gateway-consumer" "postgres" "pubsub-emulator" "routing")
for svc in "${REQUIRED[@]}"; do
    status=$(docker compose ps --format '{{.Service}} {{.Status}}' \
        | awk -v s="$svc" '$1 == s {print $2}')
    if [[ -z "$status" || "$status" != "Up" ]]; then
        echo "  ERRORE: servizio '$svc' non in esecuzione (status: ${status:-mancante})"
        echo "  Lancia prima: docker compose up -d"
        exit 1
    fi
done
echo "  Tutti i servizi sono attivi."
echo ""

# ============================================================
# SCENARIO A — Routing nominale
# ============================================================
echo "--- SCENARIO A: Routing nominale ---"
echo "Invio candidatura: pizzaiolo a Milano, cliente=pizzeria_demo"
CAND_A=$(post_candidate "pizzeria_demo" "cerco lavoro come pizzaiolo a Milano zona Navigli")
echo "  candidate_id=$CAND_A"
echo "Attendo elaborazione (5s)..."
sleep 5

echo ""
echo "Stato del candidate (atteso: status=routed, routing_location_id=milano_01):"
get_candidate "$CAND_A"

echo ""
echo "Riga RoutingDecision corrispondente:"
sql_routing "SELECT status, selected_location_id, reason FROM routing_decision WHERE candidate_id='$CAND_A';"

echo ""

# ============================================================
# SCENARIO B — Nessuna sede disponibile
# ============================================================
echo "--- SCENARIO B: Nessuna sede disponibile ---"
echo "Saturo la capacità di tutte le sedi di pizzeria_demo (current_load = max_capacity)..."
sql_config "UPDATE location SET current_load = max_capacity WHERE client_id='pizzeria_demo';"

echo ""
echo "Invio stessa candidatura..."
CAND_B=$(post_candidate "pizzeria_demo" "cerco lavoro come pizzaiolo a Milano zona Navigli")
echo "  candidate_id=$CAND_B"
echo "Attendo elaborazione (5s)..."
sleep 5

echo ""
echo "Stato del candidate (atteso: status=no_routing_available):"
get_candidate "$CAND_B"

echo ""
echo "Cleanup: ripristino current_load=0 sulle sedi di pizzeria_demo..."
sql_config "UPDATE location SET current_load = 0 WHERE client_id='pizzeria_demo';"

echo ""

# ============================================================
# SCENARIO C — Multi-tenancy
# ============================================================
echo "--- SCENARIO C: Multi-tenancy ---"
echo "Invio lo stesso raw_message ('cassiere a Milano') a due tenant differenti."
echo ""
echo "1) pizzeria_demo (cassiere NON è un ruolo aperto qui)"
CAND_C1=$(post_candidate "pizzeria_demo" "cerco lavoro come cassiere a Milano")
echo "   candidate_id=$CAND_C1"

echo ""
echo "2) supermercato_demo (cassiere è un ruolo aperto qui)"
CAND_C2=$(post_candidate "supermercato_demo" "cerco lavoro come cassiere a Milano")
echo "   candidate_id=$CAND_C2"

echo ""
echo "Attendo elaborazione (5s)..."
sleep 5

echo ""
echo "Stato pizzeria_demo (atteso: status=no_routing_available, ruolo non offerto):"
get_candidate "$CAND_C1"

echo ""
echo "Stato supermercato_demo (atteso: status=routed, location milano_02 o milano_03):"
get_candidate "$CAND_C2"

echo ""
echo "================================================="
echo "  Demo completata"
echo "================================================="
