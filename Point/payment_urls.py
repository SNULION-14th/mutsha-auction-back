from django.urls import path

from .views import PaymentApproveView, PaymentHistoryView, PaymentReadyView


app_name = "payment"

urlpatterns = [
    path("ready/", PaymentReadyView.as_view()),
    path("approve/", PaymentApproveView.as_view()),
    path("orders/", PaymentHistoryView.as_view()),
]
