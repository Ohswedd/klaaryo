# Klaaryo Smart Candidate Routing

Pipeline a microservizi che instrada candidature WhatsApp di clienti enterprise multi-sede verso la sede giusta in base a ruolo richiesto, città, capienza e regole specifiche del cliente.

## Architettura

```
                          POST /candidates
                                │
                                ▼
                       ┌────────────────┐
                       │ gateway-service│──► Postgres (gateway_db: Candidate)
                       │                │◄────────┐
                       └────────┬───────┘         │
                                │                 │
                                │ publish:        │ subscribe:
                                │ candidate.      │ candidate.routed
                                │ received        │ (update status)
                                ▼                 │
                       ┌────────────────┐         │
                       │  Pub/Sub topics│─────────┘
                       └────────┬───────┘
                                │ subscribe
                                ▼
                       ┌────────────────┐         gRPC          ┌──────────────────────┐
                       │ routing-service├──────────────────────►│ client-config-service│
                       │                │◄──────────────────────│                      │
                       └────────┬───────┘  rules + locations    └──────────┬───────────┘
                                │                                          │
                                │ publish: candidate.routed                │
                                ▼                                          ▼
                       ┌────────────────┐                       Postgres (config_db:
                       │  Pub/Sub topic │                       Client, Location,
                       └────────────────┘                       LocationOpening)
```

**gateway-service** — ingresso REST (`POST/GET /candidates`), persiste lo stato candidatura in `gateway_db`, pubblica `candidate.received` e consuma `candidate.routed` per aggiornare lo status visibile via GET.

**routing-service** — consuma `candidate.received`, estrae ruolo e città via regex deterministico, chiama il config-service via gRPC per regole e sedi, applica la strategia di routing del tenant e pubblica `candidate.routed`.

**client-config-service** — server gRPC che espone configurazione multi-tenant (clienti, sedi, ruoli aperti, capienza) backed da `config_db`.

## Come avviare

```bash
docker compose up --build
# attendi ~30s che lo stack diventi healthy
./demo.sh
```

## Testing

```bash
docker compose run --rm routing pytest -v
```

5 test pytest-django che coprono: routing nominale, no capacity, multi-tenancy, idempotenza event-level, gRPC config-service unavailable.

## Struttura repo

```
klaaryo/
├── docker-compose.yml          # 7-service runtime stack
├── demo.sh                     # scenari E2E A/B/C
├── PRD.md                      # decisioni, schema, failure modes
├── AI_NOTES.md                 # note su Claude Code come pair-programmer
├── proto/
│   └── client_config.proto     # contratto gRPC
├── scripts/
│   ├── init-databases.sql      # 3 logical DB
│   ├── pubsub_bootstrap.py     # crea topic + subscription (idempotente)
│   └── Dockerfile.pubsub-init
└── services/
    ├── gateway/                # REST + Pub/Sub publisher + consumer
    ├── routing/                # Pub/Sub consumer + gRPC client + decision
    │   └── routingapp/tests/   # 5 pytest tests
    └── config/                 # gRPC server + seed data
```

## Documenti

- [PRD.md](PRD.md) — problema, schema dati, contratti, decisioni e trade-off, failure modes, scalabilità.
- [AI_NOTES.md](AI_NOTES.md) — note sull'uso di Claude Code come pair-programmer durante lo sviluppo.

## Stack

Django 5 · Postgres 16 · Google Pub/Sub Emulator · gRPC · Docker Compose.

## Note

Container effimeri: i dati Postgres vivono dentro il container, nessun volume persistente. `docker compose down -v` pulisce tutto e `docker compose up --build` ricostruisce lo stack con i dati di seed dimostrativi (2 clienti, 5 sedi).

Gateway espone `/health/live` (liveness, senza accesso al DB) e `/health/ready` (readiness, con verifica DB). Il healthcheck di compose usa `/health/ready` per subordinare l'avvio di `gateway-consumer` tramite `service_healthy`.

## Decisioni notevoli

Due problemi scoperti empiricamente durante lo sviluppo, documentati nella sezione 3 del PRD:

- **Race al cold-boot tra migrate paralleli** di gateway e gateway-consumer (l'advisory lock di Django non copre `ensure_schema()` su DB fresh). Fix: healthcheck HTTP su gateway + `gateway-consumer.depends_on.gateway: service_healthy`.
- **Bug latente nell'idempotenza event-level**: `IntegrityError` non gestita avvelena la transazione esterna nei test (e in qualsiasi caller transazionale futuro). Fix: wrap di `ProcessedEvent.create()` in `transaction.atomic()`, pattern canonico Django per try-INSERT-catch-duplicate.
