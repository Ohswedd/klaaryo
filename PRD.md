# PRD — Smart Candidate Routing

| Campo | Valore |
|---|---|
| Versione | 1.0 (MVP) |
| Data | 2026-05-19 |
| Ore impiegate | ~4 (wall-clock totali) |
| Stack | Django 5 · DRF · Postgres 16 · Google Pub/Sub (emulator) · gRPC · Docker Compose |
| LOC | 1311 / 1500 (margine 189) |
| Test | 5 pytest-django, 0.30s wall-clock |

## 0. Executive summary

Sistema di routing intelligente di candidature WhatsApp verso le sedi di clienti enterprise multi-tenant, composto da tre microservizi Django che comunicano via Google Pub/Sub (eventi asincroni) e gRPC (configurazione sincrona). L'MVP soddisfa i tre scenari richiesti — routing nominale, saturazione capacità, isolamento multi-tenant — più due percorsi critici di failure (idempotenza event-level, indisponibilità del config-service).

Due decisioni nate dal debug, non dalla pianificazione, sono il contributo ingegneristico più rilevante: (i) la race al cold-boot tra le migrazioni parallele di gateway e gateway-consumer, risolta con healthcheck HTTP DB-aware + `service_healthy` (sezione 3.9); (ii) il wrap in `transaction.atomic()` dell'INSERT idempotente su `ProcessedEvent`, scoperto come bug latente eseguendo i pytest e non in code review (sezione 3.4). Entrambe sono correzioni di poche righe ma dimostrano un loop "test → bug reale → fix canonico".

Fuori scope deliberato: outbox pattern, DLQ Pub/Sub esplicita, observability stack (presente solo structured logging JSON-line), authentication tra servizi, update atomico cross-service di `current_load` (rationale in sezione 3.8 e 6).

## 1. Problema e architettura

### Il problema

Klaaryo riceve candidature via WhatsApp per clienti enterprise multi-sede (es. catene retail con 50+ punti vendita). Il routing manuale via team di recruiter non scala: ogni candidatura deve essere instradata alla sede giusta in base a (i) posizioni aperte per ruolo, (ii) prossimità geografica del candidato, (iii) capienza residua della sede, (iv) regole di routing specifiche del cliente. Ogni cliente ha la propria configurazione e le proprie regole, che evolvono nel tempo.

### Decomposizione in servizi

| Servizio | Ruolo | Persistenza |
|---|---|---|
| `gateway-service` | Ingresso REST (webhook WhatsApp simulati), persistenza candidatura, publisher `candidate.received`, consumer `candidate.routed` per aggiornare lo status visibile via GET | `gateway_db.candidate` |
| `routing-service` | Consumer `candidate.received`, estrazione campi (regex), chiamata gRPC al config-service, applicazione strategia di routing, publisher `candidate.routed`. Idempotente. | `routing_db.processed_event`, `routing_db.routing_decision` |
| `client-config-service` | Server gRPC con `GetClientRoutingRules` e `ListClientLocations`. Multi-tenant. | `config_db.client`, `config_db.location`, `config_db.location_opening` |

### Diagramma

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

### Flusso eventi end-to-end

1. `POST /candidates` → gateway crea `Candidate(status="received")` → publish `candidate.received` (after commit).
2. routing consuma → INSERT su `processed_event` (dedup) → `extract_fields` (regex) → gRPC `GetClientRoutingRules` + `ListClientLocations` → `decide_routing` → INSERT su `routing_decision` (atomic) → publish `candidate.routed`.
3. gateway-consumer consuma `candidate.routed` → update `Candidate.status` + `routing_location_id` + `routing_reason` (idempotente: solo transizione da `received`).
4. `GET /candidates/{id}` ritorna lo stato corrente da `gateway_db`.

### Persistenza analytics

`routing_db.routing_decision` è la single-source-of-truth per analytics su decisioni: volume per sede, distribuzione status, motivi di fallimento, distribuzione ruolo/città. È indicizzata su `(client_id, -decided_at)` per query multi-tenant performanti.

## 2. Schema dati e contratti

### Postgres — multi-tenant via discriminator column `client_id`

`gateway_db`:
```sql
candidate (
  id UUID PK,
  client_id VARCHAR(64) NOT NULL,
  raw_message TEXT NOT NULL,
  source VARCHAR(32) NOT NULL DEFAULT 'whatsapp',  -- extensible: 'telegram', 'web_form', ...
  status VARCHAR(32) NOT NULL,  -- 'received'|'routed'|'no_routing_available'|'extraction_failed'|'config_service_unavailable'
  routing_location_id VARCHAR(64) NULL,
  routing_reason TEXT NULL,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  INDEX (client_id, created_at)
)
```

`routing_db`:
```sql
processed_event (
  event_id UUID PK,
  processed_at TIMESTAMPTZ NOT NULL
)

routing_decision (
  candidate_id UUID PK,
  client_id VARCHAR(64) NOT NULL,
  extracted_role VARCHAR(64) NULL,
  extracted_city VARCHAR(64) NULL,
  status VARCHAR(32) NOT NULL,
  selected_location_id VARCHAR(64) NULL,
  reason TEXT,
  decided_at TIMESTAMPTZ NOT NULL,
  INDEX (client_id, decided_at)
)
```

`config_db`:
```sql
client (
  id VARCHAR(64) PK,
  name VARCHAR(255) NOT NULL,
  routing_strategy VARCHAR(64) NOT NULL  -- 'nearest_city'|'priority_based'|'round_robin'
)

location (
  id VARCHAR(64) PK,
  client_id VARCHAR(64) FK NOT NULL,
  name VARCHAR(255),
  city VARCHAR(64) NOT NULL,
  max_capacity INT NOT NULL,
  current_load INT NOT NULL DEFAULT 0,
  priority INT NOT NULL DEFAULT 0
)

location_opening (
  id SERIAL PK,
  location_id VARCHAR(64) FK NOT NULL,
  role VARCHAR(64) NOT NULL,
  is_open BOOLEAN NOT NULL DEFAULT TRUE,
  UNIQUE (location_id, role)
)
```

### Eventi Pub/Sub

`candidate.received` (gateway → routing):
```json
{
  "schema_version": 1,
  "event_id": "uuid",
  "candidate_id": "uuid",
  "client_id": "pizzeria_demo",
  "raw_message": "cerco lavoro come pizzaiolo a Milano zona Navigli",
  "source": "whatsapp",
  "received_at": "2026-..."
}
```

`candidate.routed` (routing → gateway + downstream futuri):
```json
{
  "schema_version": 1,
  "event_id": "uuid",
  "candidate_id": "uuid",
  "client_id": "pizzeria_demo",
  "status": "routed|no_routing_available|extraction_failed|config_service_unavailable",
  "selected_location_id": "milano_01|null",
  "extracted_role": "pizzaiolo|null",
  "extracted_city": "Milano|null",
  "reason": "matched role=pizzaiolo city=Milano, strategy=nearest_city, capacity=3/10",
  "decided_at": "2026-..."
}
```

Note: `schema_version` per forward-compatibility additiva. `source` permette canali futuri (Telegram, web form). `candidate.routed` è consumato anche da downstream futuri (notification-service per HR).

### Contratto gRPC — `client-config-service`

```proto
service ClientConfig {
  rpc GetClientRoutingRules(GetClientRoutingRulesRequest) returns (Client);
  rpc ListClientLocations(ListClientLocationsRequest) returns (ListClientLocationsResponse);
}
```

| Metodo | Scopo | Note |
|---|---|---|
| `GetClientRoutingRules` | Ritorna `Client` con `routing_strategy` per il client_id | `NOT_FOUND` se inesistente |
| `ListClientLocations` | Ritorna sedi del client con capacità + `open_roles` denormalizzati | Single-call per evitare N+1 lato consumer |

Definizione completa in `proto/client_config.proto`. Codegen a build time (vedi sezione 3.10).

### REST API — `gateway-service`

| Endpoint | Risposta |
|---|---|
| `POST /candidates` | `202 Accepted` · `{candidate_id, status}` |
| `GET /candidates/{id}` | `200 OK` · `{id, client_id, status, source, routing_location_id, routing_reason, created_at, updated_at}` (no `raw_message` in GET — PII) |
| `GET /health/live` | `200 OK` · liveness (no DB) |
| `GET /health/ready` | `200 OK` o `503 Service Unavailable` · readiness (DB query) |

### Strategia di testing — 5 test mirati

| Test | Scope | Cosa verifica |
|---|---|---|
| `test_routing_scenario_a_nominal` | Pipeline happy path | Extraction + decision + persist + publish, strategy `nearest_city` |
| `test_routing_scenario_b_no_capacity` | Logica filtraggio | Saturated locations → `no_routing_available` con motivazione |
| `test_routing_scenario_c_multitenancy` | Isolamento multi-tenant | Stesso payload, due `client_id` con strategie diverse → due decisioni indipendenti |
| `test_idempotency_duplicate_event` | At-least-once Pub/Sub | Stesso `event_id` processato 2× → 1 `ProcessedEvent`, 1 `RoutingDecision`, 1 publish |
| `test_config_service_unavailable` | Failure mode gRPC | `ConfigServiceError` → `status="config_service_unavailable"`, no crash del consumer |

Filosofia: mock dei soli confini esterni (gRPC, Pub/Sub publish), DB Postgres reale (`@pytest.mark.django_db`). Sabotaggio del codice produce assertion failure reale — i test non sono finti.

## 3. Decisioni e trade-off

1. **Estrazione campi: regex/keyword, non LLM.**
   *Alternative*: LLM con structured output, NER fine-tuned.
   *Scelta*: regex con alternation singola in `routingapp/extraction.py` (7 ruoli + 11 città, prima occorrenza posizionale vince).
   *Perché*: deterministico, zero latenza/costo/dipendenze, testabile. LLM è il passo successivo quando i messaggi diventano sfumati. Soglia di refactor: >5% di estrazioni mancate in produzione.

2. **Multi-tenancy via discriminator column.**
   *Alternative*: schema-per-tenant, DB-per-tenant.
   *Scelta*: colonna `client_id VARCHAR(64)` indicizzata su tutte le tabelle di dominio.
   *Perché*: a 50 clienti schema-per-tenant esplode l'overhead di migrations; DB-per-tenant è eccessivo per il volume. Threshold per cambiare: cliente top con SLA isolato a livello DB.

3. **DB-per-servizio logicamente, singola istanza fisica.**
   *Alternative*: database condiviso, istanze Postgres separate.
   *Scelta*: 3 logical database (`gateway_db`, `routing_db`, `config_db`) sulla stessa istanza, creati da `scripts/init-databases.sql`.
   *Perché*: ownership chiara dei dati per servizio (no shared schema), semplicità di docker-compose. Trade-off intenzionale: cross-service joins impossibili, forza l'uso di gRPC o eventi.

4. **Idempotenza event-level via `ProcessedEvent` + `transaction.atomic()`.**
   *Alternative*: outbox pattern, idempotency-token via header.
   *Scelta*: tabella `processed_event(event_id UUID PK)`; INSERT prima del processing, `IntegrityError` → log e ritorno anticipato. L'INSERT è racchiuso in `transaction.atomic()`.
   *Perché il wrap atomico*: scoperto come bug latente da `test_idempotency_duplicate_event`. Senza wrap, l'`IntegrityError` non gestita avvelena qualsiasi transazione esterna (pytest-django default, caller in batch processor, signal handler `post_save`). In autocommit funziona per coincidenza; con wrap ovunque. Pattern Django canonico per try-INSERT-catch-duplicate — il test ha rivelato il bug, non la code review.

5. **gRPC sync per il config-service.**
   *Alternative*: REST + JSON.
   *Scelta*: gRPC con contratto `proto/client_config.proto`, codegen a build time.
   *Perché*: contratto tipizzato versionato, stack production di Klaaryo. Trade-off (tooling più pesante, debug meno immediato) mitigato dal wrapper anti-corruption (sezione 3.11).

6. **Pub/Sub emulator vs RabbitMQ/Redis Streams.**
   *Scelta*: Google Pub/Sub emulator (`google/cloud-sdk:emulators`).
   *Perché*: stack production di Klaaryo, semantics reali (ack deadline, at-least-once). Trade-off: snapshot/seek non coperti in MVP.

7. **Decision engine: switch + funzioni private, non strategy pattern OO.**
   *Alternative*: `class RoutingStrategy(ABC)` con 3 sottoclassi.
   *Scelta*: funzioni `_strategy_nearest_city`, `_strategy_priority_based`, `_strategy_round_robin` in `routingapp/decision.py`, switch su `client.routing_strategy`.
   *Perché*: 3 strategie in ~40 righe non giustificano una gerarchia di classi. A 10+ strategie: registry pattern (dict nome→funzione). Per regole custom-per-cliente: mini-DSL JSON (sezione 6).

8. **`current_load` NON aggiornato dal routing-service (cross-service DB write evitato).**
   *Alternative*: cross-DB write con `F()` expression, evento dedicato `location.capacity_consumed`.
   *Scelta*: nessun update automatico in MVP; commento esplicito in `handlers.py`.
   *Perché*: cross-DB write rompe il boundary microservizi. La soluzione corretta in prod è evento dedicato + config-service che applica `Location.objects.filter(...).update(current_load=F('current_load')+1)` (F-expression atomic). In MVP `demo.sh` scenario B aggiorna manualmente via SQL.

9. **Cold-boot race tra migrazioni parallele — healthcheck HTTP.**
   *Sintomo*: con `migrate` su entrambi gateway e gateway-consumer, il primo `docker compose up` falliva nel 50% dei casi su DB fresh con `duplicate key value violates unique constraint "pg_type_typname_nsp_index"`.
   *Causa*: il `pg_advisory_xact_lock` di Django serializza l'applicazione delle migrazioni ma non `ensure_schema()` che crea `django_migrations`. Due processi che la creano in parallelo competono sui lock di sistema di Postgres.
   *Scelta*: healthcheck HTTP `GET /health/ready` su gateway (DB-aware via `Candidate.objects.exists()`), `gateway-consumer.depends_on.gateway: service_healthy`. Solo gateway esegue migrate. Verificato su 3 cold boot consecutivi (3/3 puliti). Affiancato: `/health/live` (no DB) per separare liveness da readiness alla K8s.
   *Alternative scartate*: `restart: on-failure` (nasconde il problema), servizio `gateway-migrate` dedicato (over-engineering), `sleep N` (fragile).

10. **gRPC codegen a build time, no commit di `*_pb2*.py`.**
    *Scelta*: `services/{config,routing}/scripts/codegen.sh` invocato dal Dockerfile prima della COPY del codice; output in `<app>/grpc_gen/`.
    *Perché*: `.proto` come single source of truth, nessun drift tra contratto e stub. Trade-off: build context dei due Dockerfile spostato a root per accedere a `/proto/`. La `codegen.sh` include una `sed` che riscrive `import client_config_pb2` in `from . import client_config_pb2` (workaround a un quirk di `grpc_tools.protoc`).

11. **Client wrapper come anti-corruption layer.**
    *Scelta*: `config_client.list_client_locations()` fa `return response.locations` internamente; `decision.py` e `handlers.py` ricevono la lista già unwrap-ata, mai il proto `ListClientLocationsResponse`.
    *Migrazione futura concreta*: se il config-service passasse da gRPC a REST, cambierebbe solo l'implementazione interna del wrapper, zero modifiche al business code.

12. **Config via `settings.py`, non `os.environ` inline.**
    *Scelta*: business code legge `settings.CONFIG_GRPC_ADDR`, popolato in `routing/settings.py` da `os.environ.get(...)`.
    *Perché*: layout Django classico, testabilità via `@override_settings`, single source of truth per i default.

13. **Scelte di infrastruttura minori — consapevoli.**
    - **Credenziali Postgres hardcoded** in `docker-compose.yml` (`klaaryo:klaaryo`): zero-config in dev; in prod env vars + secret manager.
    - **`pubsub-init` come mini-image dedicata** (`scripts/Dockerfile.pubsub-init`): disaccoppia bootstrap tooling dal servizio applicativo.
    - **Duplicazione di `logging_config.py`** tra gateway e routing: ogni servizio self-contained, zero infrastruttura cross-servizio. Threshold di refactor in shared package: 3+ servizi.

## 4. Failure modes

| Scenario | Comportamento osservabile | Mitigazione MVP | Mitigazione prod |
|---|---|---|---|
| **Broker (Pub/Sub) giù** | `gateway-service` ritorna `502` con `event_publish_failed`. `Candidate` committato a `received` ma senza evento. | Il chiamante può ritentare. | Outbox pattern (record + evento in stessa transazione, job separato pubblica). |
| **`client-config-service` giù** | `routing-service` con timeout 2s, nessun retry. Publish `candidate.routed` con `status="config_service_unavailable"`, consumer non bloccato. | Pub/Sub redelivery + nuovo tentativo al riavvio del config-service. | Cache TTL 60s lato routing + retry esponenziale al wrapper. |
| **Evento duplicato** | `INSERT` su `processed_event(event_id)` → `IntegrityError` → ack & skip. | Dedup tecnico (stesso event_id) garantito. | Stesso pattern; dedup business-level (3 messaggi dello stesso candidato) richiede chiave logica diversa. |
| **`routing-service` crasha a metà** | Prima dell'INSERT: Pub/Sub riconsegna. Tra INSERT e publish: decisione in DB ma evento non parte (<1% dei casi). | Downstream riconcilia leggendo `routing_decision`. | Outbox pattern risolve sia il pre-INSERT sia il post-INSERT. |
| **Gateway consumer di `candidate.routed` crasha** | `Candidate.status` resta `received` anche se è già stato routed. | Pub/Sub riconsegna al riavvio; GET espone sempre lo stato corrente del DB. | Healthcheck del consumer + restart automatico in orchestratore. |

## 5. Scalabilità

**Oggi** (100 cand/giorno/cliente · ~5k/giorno totali per 50 clienti): carico irrisorio. Single subscription Pub/Sub, single replica `routing-service`, Postgres su una macchina. Utilizzo sotto il 5%.

**100k/giorno totali**: `routing-service` scala orizzontalmente (Pub/Sub fa load balancing nativo tra consumer della stessa subscription, 3-5 repliche). `client-config-service` diventa il bottleneck (100k call/giorno) → cache in-process per regole con TTL 30s, invalidation via channel separato. Postgres regge. Costo Pub/Sub ~$5/mese.

**1M/giorno totali**: read replica Postgres per `config-service`. Sharding lato `candidate` per `client_id` o partitioning per `created_at`. Routing autoscaling su subscription backlog (`num_undelivered_messages` > threshold). Monitorare `ack_deadline` e `oldest_unacked_message_age`. Costo Pub/Sub ~$40/mese; a volumi sostenuti superiori, valutare batching o migrazione a Kafka self-hosted.

## 6. Riflessioni sulle scelte

### Cosa è deliberatamente fuori scope

- **Notifica HR** (Slack/email/Whatsapp): `candidate.routed` è il punto di estensione per un futuro `notification-service`. Architettura pronta, 4° servizio non core all'MVP.
- **Outbox pattern**: complessità non giustificata per il volume MVP. Trade-off in sezione 3.4.
- **Dead Letter Queue Pub/Sub**: feature nativa configurabile sul subscription, non attivata in MVP.
- **Authentication tra servizi**: interno, fidato in MVP.
- **Observability stack** (metriche/tracing): solo structured logging JSON-line via `JsonLineFormatter` in gateway + routing.
- **Audit/history config**: in prod, Django signals `post_save` + tabella append-only `location_history`, oppure temporal table pattern.
- **Geocoding e distanze**: il match per città è sufficiente per il dataset osservato.
- **`current_load` atomic update cross-service**: sezione 3.8.

### Se avessi 4 ore invece di 8

1. Taglio il gateway-consumer di `candidate.routed`. Lo `status` resta `received`; il GET fa cross-DB read di `routing_decision` per lo stato real-time.
2. Riduco i test da 5 a 2: un E2E + un multi-tenancy.
3. Taglio il decision engine a una sola strategia (`nearest_city`); `routing_strategy` ignorato.

### Decisione futura aperta (50 clienti con regole custom tra 6 mesi)

Non rifarei l'MVP diversamente. A 50 clienti lo switch in `decision.py` cresce a 5-10 strategie nominate, ancora gestibili. Per regole davvero custom-per-cliente (es. "Pizzeria X preferisce sedi con `current_load` < 50%"), valuterei un mini-DSL JSON valutato dal routing-service. La condizione scatenante è quantitativa: 3° cliente con richiesta custom → refactor a registry pattern; 6° cliente → DSL.

## 7. gRPC, in pratica

Non l'ho usato in produzione prima di questo progetto. L'approccio è stato di capire prima i concetti critici per un MVP in docker-compose, poi implementare.

### Tre concetti chiave

1. **Channel lifecycle e reuse.** Un canale gRPC è costoso da aprire (TCP + HTTP/2 handshake). Il client deve riusarlo a livello di processo. Pattern adottato: lazy singleton module-level in `routingapp/clients/config_client.py:get_channel()`, inizializzato al primo uso.

2. **Deadlines vs timeouts.** La deadline è un timestamp assoluto, il timeout è relativo; in Python il client espone `timeout=` per semplicità. Settato a 2s in `get_client_routing_rules` e `list_client_locations`: deve stare comodamente dentro l'ack deadline di Pub/Sub (10s default), altrimenti il consumer rischia redelivery durante il processing — e il messaggio verrebbe processato due volte prima che la prima decisione sia committata.

3. **Status codes vs Python exceptions.** Server-side, sollevare un'eccezione Python normale diventa `UNKNOWN` lato client (perdita di informazione). Per errori prevedibili uso `context.set_code(grpc.StatusCode.NOT_FOUND)` esplicitamente — vedi `configapp/grpc_server.py:GetClientRoutingRules` per il caso "client non trovato". Lato client, ogni errore arriva come `grpc.RpcError` con `.code()` per discriminare; il wrapper lo cattura e rilancia `ConfigServiceError` con il code formattato.

### Cose scivolose

- **Codegen path.** `grpc_tools.protoc` genera il `_grpc.py` con un `import client_config_pb2` top-level. Eseguito da un package Python (`routingapp.grpc_gen`) fallisce a runtime. Risolto con `sed` in `codegen.sh` che riscrive in `from . import client_config_pb2`. Workaround standard, ma costa tempo capirlo la prima volta.
- **`UNAVAILABLE` vs timeout.** Server down → il client riceve `StatusCode.UNAVAILABLE` quasi immediatamente (TCP refused), non timeout. Entrambi mappati a `ConfigServiceError` nel wrapper, con il codice originale preservato nel `.details()`.
- **Docker startup ordering.** Il server gRPC parte veloce ma il listener `accept` impiega 1-2s; `depends_on` semplice non basta. Soluzione robusta: `grpc_health.v1.health` (già esposto dal server con status `SERVING`). In MVP `depends_on: service_started` + primo RPC con timeout 2s e nessun retry: failure → `config_service_unavailable`, Pub/Sub riconsegna. Per prod: retry con backoff esponenziale al wrapper.

### Cose non approfondite (per restare nei limiti)

- Streaming RPC (server/bidi): non necessari per il dominio.
- Interceptors: in prod li userei per logging/metrics trasversali.
- TLS/mTLS: insecure in locale, in prod service mesh o cert-manager.
- Reflection: utile per `grpcurl`, non MVP.

In sintesi: gRPC è maturo ma poco forgiving per chi parte da REST. Errori meno verbosi, tooling più povero. I contratti `.proto` restano un beneficio reale per RPC internal-to-internal e abilitano l'anti-corruption layer di sezione 3.11.
