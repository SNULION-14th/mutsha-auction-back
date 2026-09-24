from django.urls import path
from .views import PayReadyView, PayApproveView, PayApprovedView, PayDetailedView

app_name = "payment"
urlpatterns = [
    # CBV url path
    path("ready/", PayReadyView.as_view()),
    path("approve/", PayApproveView.as_view()),
    path("approved/<int:user_id>/", PayApprovedView.as_view()),
    path("detail/<str:tid>/", PayDetailedView.as_view()),
]