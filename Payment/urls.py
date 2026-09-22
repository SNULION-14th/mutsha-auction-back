from django.urls import path
from .views import PayReadyView

app_name = "payment"
urlpatterns = [
    # CBV url path
    path("ready/", PayReadyView.as_view()),
]