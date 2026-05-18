from rest_framework import serializers


class CandidateInputSerializer(serializers.Serializer):
    client_id = serializers.CharField(max_length=64)
    raw_message = serializers.CharField(max_length=2000)
    source = serializers.CharField(max_length=32, default="whatsapp", required=False)

    def validate_raw_message(self, value):
        stripped = value.strip()
        if not stripped:
            raise serializers.ValidationError("raw_message must be non-empty")
        return stripped


class CandidateOutputSerializer(serializers.Serializer):
    # raw_message intentionally omitted from GET: it can contain PII from the
    # WhatsApp message and is not needed by the status-polling caller. The
    # raw payload stays in gateway_db for analytics/replay.
    id = serializers.UUIDField()
    client_id = serializers.CharField()
    status = serializers.CharField()
    source = serializers.CharField()
    routing_location_id = serializers.CharField(allow_null=True)
    routing_reason = serializers.CharField(allow_null=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
