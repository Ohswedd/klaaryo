from django.db import OperationalError, ProgrammingError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from gatewayapp.models import Candidate
from gatewayapp.pubsub import PublishError, publish_candidate_received
from gatewayapp.serializers import (
    CandidateInputSerializer,
    CandidateOutputSerializer,
)


class CandidateCreateView(APIView):
    def post(self, request):
        serializer = CandidateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            candidate = Candidate.objects.create(
                client_id=data["client_id"],
                raw_message=data["raw_message"],
                source=data.get("source", "whatsapp"),
                status="received",
            )

        # Publish AFTER commit: avoids publishing an event for a row that
        # rolled back. Documented failure mode in PRD section 4 (broker giù row).
        try:
            publish_candidate_received(candidate)
        except PublishError as e:
            return Response(
                {"error": "event_publish_failed", "detail": str(e)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(
            {"candidate_id": str(candidate.id), "status": candidate.status},
            status=status.HTTP_202_ACCEPTED,
        )


class CandidateDetailView(APIView):
    def get(self, request, candidate_id):
        candidate = get_object_or_404(Candidate, id=candidate_id)
        return Response(CandidateOutputSerializer(candidate).data)


class HealthLiveView(APIView):
    # Process-level liveness: no DB or external calls. Cheap to poll.
    def get(self, request):
        return Response({"status": "ok"})


class HealthReadyView(APIView):
    # Readiness: validates DB reachability. Used by docker-compose healthcheck
    # and gateway-consumer.depends_on (service_healthy gate).
    def get(self, request):
        try:
            Candidate.objects.exists()
        except (OperationalError, ProgrammingError):
            return Response(
                {"status": "degraded"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"status": "ok"})
