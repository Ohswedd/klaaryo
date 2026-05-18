FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY services/routing/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Codegen step before the app COPY: same pattern as config-service. Generated
# *_pb2*.py files end up at /app/routingapp/grpc_gen/ and survive the COPY
# because they're gitignored on the host.
COPY proto /proto
COPY services/routing/scripts/codegen.sh /usr/local/bin/codegen.sh
RUN chmod +x /usr/local/bin/codegen.sh && /usr/local/bin/codegen.sh

COPY services/routing /app

CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py run_consumer"]
