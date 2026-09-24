from django.urls import path
from .views import PayReadyView, PayApproveView, PaymentOrderListView

app_name = "payment"
urlpatterns = [
    # CBV url path
    path("ready/", PayReadyView.as_view()),
    path("approve/", PayApproveView.as_view()),
    path("orders/", PaymentOrderListView.as_view()),
]