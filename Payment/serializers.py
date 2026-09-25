from rest_framework import serializers
from .models import Payment


class PaymentReadySerializer(serializers.Serializer):
    item_name = serializers.CharField(max_length=100)
    quantity = serializers.IntegerField(min_value=1, max_value=1000000)
    total_amount = serializers.IntegerField(min_value=1)


class PaymentApproveSerializer(serializers.Serializer):
    tid = serializers.CharField(max_length=100)
    pg_token = serializers.CharField(max_length=500)


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["tid", "item_name", "quantity", "total_amount", "status", "approved_at", "created_at"]
