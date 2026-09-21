from rest_framework import serializers


class PayReadyRequestSerializer(serializers.Serializer):
    partner_order_id = serializers.CharField(max_length=100)
    partner_user_id = serializers.CharField(max_length=100)
    item_name = serializers.CharField(max_length=100)
    quantity = serializers.IntegerField(min_value=1)
    total_amount = serializers.IntegerField(min_value=1)
    vat_amount = serializers.IntegerField(min_value=0, default=0)
    tax_free_amount = serializers.IntegerField(min_value=0, default=0)
    approval_url = serializers.URLField()
    cancel_url = serializers.URLField()
    fail_url = serializers.URLField()


class PayApproveRequestSerializer(serializers.Serializer):
    pg_token = serializers.CharField()
    tid = serializers.CharField(max_length=100)
