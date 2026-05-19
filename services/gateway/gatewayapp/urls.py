from django.urls import path

from gatewayapp import views


urlpatterns = [
    path(
        "candidates",
        views.CandidateCreateView.as_view(),
        name="candidate-create",
    ),
    path(
        "candidates/<uuid:candidate_id>",
        views.CandidateDetailView.as_view(),
        name="candidate-detail",
    ),
    path("health/live", views.HealthLiveView.as_view(), name="health-live"),
    path("health/ready", views.HealthReadyView.as_view(), name="health-ready"),
]
