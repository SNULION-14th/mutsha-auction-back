from django.urls import path
from .views import PayApproveView, PayHistoryView, PayReadyView

app_name = "payment"
urlpatterns = [
    # CBV url path
    path("ready/", PayReadyView.as_view()),
    path("approve/", PayApproveView.as_view()),
    path("orders/", PayHistoryView.as_view()),
]
