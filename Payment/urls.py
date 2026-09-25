from django.urls import path
from .views import PaymentApprovalView, PaymentHistoryView, PaymentReadyView

urlpatterns = [
    path("ready/", PaymentReadyView.as_view()),
    path("approve/", PaymentApprovalView.as_view()),
    path("history/", PaymentHistoryView.as_view()),
]
