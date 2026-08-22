from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path('ws/auction/<int:auction_id>/', consumers.AuctionConsumer.as_asgi()),
    path('ws/notifications/', consumers.NotificationConsumer.as_asgi()),
]