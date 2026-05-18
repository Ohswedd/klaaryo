FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY services/config/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Codegen step before COPY of app source. Output goes to /app/configapp/grpc_gen/;
# the subsequent COPY does not overwrite *_pb2*.py since they are gitignored on
# the host. __init__.py is identical and harmless to overwrite.
COPY proto /proto
COPY services/config/scripts/codegen.sh /usr/local/bin/codegen.sh
RUN chmod +x /usr/local/bin/codegen.sh && /usr/local/bin/codegen.sh

COPY services/config /app

EXPOSE 50051
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py seed_data && python manage.py run_grpc_server"]
