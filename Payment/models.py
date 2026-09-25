from django.conf import settings
from django.db import models


class Payment(models.Model):
    class Status(models.TextChoices):
        READY = "ready", "Ready"
        APPROVED = "approved", "Approved"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="pay_buyer", null=True)
    tid = models.CharField(max_length=100)
    partner_order_id = models.CharField(max_length=100)
    item_name = models.CharField(max_length=100)
    quantity = models.PositiveIntegerField()
    total_amount = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.READY)
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
