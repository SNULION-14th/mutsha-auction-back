from django.contrib.auth.models import User
from django.db import models


class Payment(models.Model):
    tid = models.CharField(max_length=100, unique=True)
    partner_order_id = models.CharField(max_length=100)
    partner_user_id = models.CharField(max_length=100)
    point = models.PositiveIntegerField(default=0)
    price = models.PositiveIntegerField(default=0)
    pay_status = models.CharField(max_length=20, default="ready")
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    created_at = models.DateTimeField(auto_now_add=True)
