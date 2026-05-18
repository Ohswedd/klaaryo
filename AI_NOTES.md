# AI Notes

## Setup

Ho usato Claude Code (Opus 4.7, 1M context) come pair-programmer per tutte le ~3 ore di sviluppo, ma il setup preparato prima di iniziare è la parte di lavoro AI di cui sono più soddisfatto. Tre pezzi hanno fatto la differenza:

- **`CLAUDE.md` alla root**, scritto a mano da me prima di scrivere una riga di codice. Contiene le convenzioni di progetto e — soprattutto — una sezione esplicita "Django: anti-patterns from FastAPI-thinking" che vieta Pydantic, async views, `ModelSerializer` auto-generati, `@api_view`, dependency injection containers, e una lista "General anti-patterns" (abstract base classes per gerarchie < 2 sottoclassi, retry decorators, repository pattern, type hints come schema). Senza questi vincoli espliciti il modello tende a riusare pattern da altri framework (FastAPI, SQLAlchemy) anche su una codebase Django pura. È il pezzo di prompt-engineering che ha avuto il ritorno più alto: ogni prompt successivo poteva essere più corto perché i "no" erano centralizzati.
- **File-based persistent memory** (`~/.claude/projects/.../memory/`) come blocco appunti per le decisioni tecniche da preservare nel PRD finale. Ho aperto tre file durante lo sviluppo (`prd_pending_tradeoffs.md` con 8 trade-off accumulati, `routing_dockerfile_context.md` come promemoria di un vincolo strutturale per una fase successiva, `ai_notes_pending.md` per esempi narrativi). Ogni volta che emergeva una decisione con valore di trade-off, la annotavo subito; al momento di finalizzare la sezione 3 del PRD erano tutte lì pronte, ordinate, con il "perché" già scritto.
- **Workflow-based**: Promts con vincoli rigidi (lista file da creare riga per riga, LOC budget, sezioni richieste, stack obbligatorio). Ognuno terminato con uno smoke test concreto e preciso scritto nel prompt (`curl POST + GET, atteso X`, `psql query atteso Y`). Ha tenuto il modello sui binari: senza, sarebbe stato facile derivare verso "una feature in più, un'astrazione preventiva".

## Cosa ho scritto io a mano

L'**architettura completa** (3 servizi con boundary precise, multi-tenancy via discriminator column, idempotenza event-level via `ProcessedEvent`, decision engine come switch + funzioni). Lo **schema dati** completo (tabelle, eventi, contratto gRPC, REST API). L'inquadramento dei **13 trade-off della sezione 3 del PRD** — ognuno è stato formulato direttamente nei prompt come vincolo ("usa pattern X, non Y, perché Z") o esplicitato in revisione intermedia con la sua motivazione. La **selezione dei 5 test** e il loro razionale. La **struttura narrativa del PRD** e dell'AI_NOTES. I criteri di **smoke test** dopo ogni fase. L'intera negoziazione architetturale della cold-boot race (vedi sotto).

## Cosa ho delegato all'AI

L'implementazione meccanica: scaffold Django (`manage.py`, `settings.py`, app skeleton), Dockerfile per i 3 servizi + entry `docker-compose.yml`, codegen gRPC con sed-patch del relative import, publisher/consumer Pub/Sub + management commands, i 5 test pytest-django con `unittest.mock.patch`, `demo.sh` end-to-end. Più l'esecuzione operativa: smoke test (curl, psql, docker compose), word counting, LOC analysis, verifica di consistency PRD ↔ codice. Tutto verificabile, niente scelte architetturali nascoste.

## Quattro esempi concreti di revisione che hanno cambiato il codice

1. **Bug latente nell'idempotenza scoperto dai test.** Il primo handler era `try ProcessedEvent.create / except IntegrityError` senza wrap. `test_idempotency_duplicate_event` falliva con `TransactionManagementError`. Il primo istinto del modello è stato correggere il test (`@pytest.mark.django_db(transaction=True)`). L'ho reindirizzato al pattern canonico Django: wrap in `transaction.atomic()` nel handler. Fix di due righe che funziona in autocommit *e* in transazione esterna. È il trade-off che racconto per primo nella sezione 3.4 del PRD: "test green ≠ code OK".
2. **Race al cold-boot, 4 opzioni, 3 rifiutate.** Dopo 2 cold-boot consecutivi falliti con esiti simmetrici (50/50 chi crashava tra gateway e gateway-consumer), il modello ha presentato 4 opzioni di fix. Ho rifiutato `restart: on-failure` (nasconde il problema invece di risolverlo), il servizio `gateway-migrate` dedicato (over-engineering per un MVP), e `sleep N` (fragile, non scala con cold cache). Scelta finale: healthcheck HTTP su gateway + `service_healthy`. Verificato su 3 cold boot consecutivi.
3. **Anti-corruption layer del `config_client`.** La prima versione di `handlers.py` faceva `list_client_locations(...).locations` lato caller. L'ho reindirizzato a `return response.locations` dentro il wrapper: il proto `ListClientLocationsResponse` non esce più dal modulo `clients/`, e una migrazione futura a REST richiederebbe modifiche solo al wrapper.
4. **Split di `/health` in `/health/live` + `/health/ready`** in fase di finalizzazione. La prima versione aveva un solo endpoint che faceva la query al DB. Lo split separa liveness (processo Python attivo) da readiness (DB raggiungibile) seguendo la convenzione K8s.

## Cosa è stato scivoloso lato AI

Il modello è troppo difensivo per default — tende a try/except eccessivi, retry policy non richieste, abstract bases per gerarchie da 3 elementi. Le sezioni di anti-pattern del `CLAUDE.md` hanno fatto da vaccino, ma ho dovuto rifiutare esplicitamente più volte ("niente restart policy", "niente outbox pattern in MVP", "niente factory_boy nei test", "niente classe astratta per 3 strategie"). Anche su prompt esplicito, deviazioni emergono e vanno corrette in review (es. il `.locations` sopra). La regola operativa: ogni file generato va letto, niente "accept all". L'AI accelera l'esecuzione, non sostituisce la decisione architetturale.

## Tempo

~4 ore wall-clock totali dal primo commit.
