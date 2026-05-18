# CLAUDE.md — Project conventions and constraints

## Project context

Klaaryo Smart Candidate Routing MVP: three Django microservices that route
job candidates to specific store locations of multi-location enterprise
clients. Stack: Django + Postgres + Google Pub/Sub + gRPC.

Prioritize trade-offs, restraint, and clarity over cleverness.

## MVP constraints

- Keep code tight: target ~1500 LOC across services (excluding gRPC generated files, migrations, configs)
- Single `docker compose up` must boot everything
- Tests: a focused set of well-chosen ones, not coverage chasing

## Django: idiomatic style is REQUIRED

This codebase must read like written by an experienced Django developer.
Use these Django-native patterns whenever the situation calls for it:

1. F() expressions for any DB update that increments/decrements an existing value.
   Example: Location.objects.filter(id=x).update(current_load=F('current_load') + 1)
   Never: obj.field += 1; obj.save() for counters.

2. Custom QuerySet/Manager methods when a query is used in multiple places.
   Use models.QuerySet.as_manager() pattern.

3. transaction.atomic as decorator or context manager around multi-statement
   DB writes. Note transactional boundaries explicitly.

4. Management commands via BaseCommand, not standalone scripts.
   Use self.stdout.write(self.style.SUCCESS(...)) for output.

5. DRF APIView class-based views, not function-based with @api_view.
   Explicit Serializer classes with field-by-field declarations,
   not ModelSerializer auto-generated unless trivially appropriate.

6. select_related / prefetch_related when crossing FK in iterating querysets.

7. apps.py AppConfig properly set with default_auto_field.

8. Model Meta class with db_table, indexes, ordering where useful.
   Always include __str__ method on models.

9. Settings file: pure Django settings.py reading from os.environ.
   Never pydantic-settings, never a Settings class.

10. URL routing: urls.py with path() and include(). Never decorator routing.

## Django: anti-patterns from FastAPI-thinking — DO NOT produce

1. NO async def views. Django sync only.
2. NO Pydantic models for request/response. Use DRF Serializers.
3. NO type hints as schema definition source. Type hints are documentation.
4. NO dependency injection containers. Pass args.
5. NO @router.post mental model. URL config separately.
6. NO SQLAlchemy-style explicit sessions. Django ORM is QuerySet-based.
7. NO Pydantic Settings. Use os.environ in settings.py.
8. NO standalone Python scripts where a management command fits.

## General anti-patterns

1. Abstract base classes unless 2+ concrete subclasses planned NOW.
2. Custom exceptions beyond strictly needed (1-2 max per service).
3. Decorators for retry/circuit-breaker/cache unless explicitly asked.
4. Repository / Service / DTO patterns.
5. Async/await anywhere.
6. Logging configuration longer than 15 lines per service.
7. TODO comments without context. Every TODO references PRD section.
8. Type hints on every line. Public signatures yes, locals no.
9. Comments describing WHAT the code does. Only WHY comments.
10. Defensive programming on internal calls. Trust your own code.
11. Premature config externalization. Hardcode what won't change.

## Code style

- English everywhere in code (variables, functions, files, logs, errors)
- Italian only in demo.sh user-facing prints
- Comments: WHY not WHAT
- Naming: descriptive. routing_decision not rd. candidate_id not cid.
- Function size: 5-20 lines preferred. Split if longer, don't atomize.
- Files: prefer fewer larger files over many tiny ones.

## Architectural decisions already made

- Multi-tenancy: discriminator column (client_id) on every domain table.
- Field extraction: regex + keyword matching, NOT LLM. Justified in PRD section 3.1.
- Idempotency: ProcessedEvent(event_id, processed_at) with UNIQUE constraint.
- DB topology: single Postgres instance, separate logical databases per service.
- gRPC channels: created once per process, reused. Insecure (localhost).
- Pub/Sub: Google Pub/Sub emulator. Topics/subs created by init script.
- Event payloads include schema_version field for forward compatibility.

## Output format

When implementing:
- Plan first: list files to create/modify and why, ONE LINE each
- Then implement
- After implementing, note what was NOT done that someone might expect

## Boundary

Boilerplate is delegated. Architectural choices are not. Examples that
require explicit decision:
- Routing algorithm details
- Logging levels
- Trade-off justifications
- Test scenarios