from django.urls import include, path


urlpatterns = [
    path("", include("gatewayapp.urls")),
]
