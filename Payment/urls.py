from django.urls import path

from .views import PayApproveView, PayReadyView, PaymentHistoryView

app_name = "payment"

urlpatterns = [
    path("ready/", PayReadyView.as_view()),
    path("approve/", PayApproveView.as_view()),
    path("history/", PaymentHistoryView.as_view()),
]
