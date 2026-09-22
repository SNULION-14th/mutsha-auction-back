from django.db import models
from django.contrib.auth.models import User

# Create your models here.
class Point(models.Model):
    price = models.CharField(max_length=256)
    point = models.IntegerField()


class Payment(models.Model):
    class Status(models.TextChoices):
        READY = "READY", "결제 대기"
        APPROVED = "APPROVED", "결제 승인"
        FAILED = "FAILED", "결제 실패"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="payments")
    partner_order_id = models.CharField(max_length=64, unique=True)
    tid = models.CharField(max_length=128, blank=True)
    item_name = models.CharField(max_length=256)
    quantity = models.PositiveIntegerField()
    total_amount = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.READY)
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
