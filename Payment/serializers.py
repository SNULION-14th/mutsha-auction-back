from rest_framework.serializers import ModelSerializer
from rest_framework import serializers

class PayReadyRequestSerializer(serializers.Serializer):
  partner_order_id = serializers.CharField()
  partner_user_id = serializers.CharField()
  item_name = serializers.CharField()
  total_amount = serializers.IntegerField()

class PayApproveRequestSerializer(serializers.Serializer):
  pg_token = serializers.CharField()
  tid = serializers.CharField()

class PayReadyResponseSerializer(serializers.Serializer):
  tid = serializers.CharField()
  next_redirect_app_url = serializers.CharField()
  next_redirect_mobile_url = serializers.CharField()
  next_redirect_pc_url = serializers.CharField()
  android_app_scheme = serializers.CharField()
  ios_app_scheme = serializers.CharField()
  created_at = serializers.DateTimeField()

class PayApproveResponseSerializer(serializers.Serializer):
  aid = serializers.CharField()
  tid = serializers.CharField()
  cid = serializers.CharField()
  sid = serializers.CharField()
  status = serializers.CharField()
  partner_order_id = serializers.CharField()
  partner_user_id = serializers.CharField()
  payment_method_type = serializers.CharField()
  amount = serializers.IntegerField()
  card_info = serializers.CharField()
  item_name = serializers.CharField()
  item_code = serializers.CharField()
  quantity = serializers.IntegerField()
  created_at = serializers.DateTimeField()
  approved_at = serializers.DateTimeField()
  payload = serializers.CharField()