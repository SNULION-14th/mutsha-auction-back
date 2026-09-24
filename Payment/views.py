import json

import requests
from django.conf import settings
from django.db import transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from UserProfile.models import UserProfile

from .models import Payment
from .serializers import PayApproveRequestSerializer

pay_key = settings.KAKAO_PAY_KEY
cid = settings.KAKAO_PAY_CID
payready_url = "https://open-api.kakaopay.com/online/v1/payment/ready"
payapprove_url = "https://open-api.kakaopay.com/online/v1/payment/approve"
payment_detail_url = "https://open-api.kakaopay.com/online/v1/payment/order"
pay_header = {
    "Content-Type": "application/json",
    "Authorization": f"SECRET_KEY {pay_key}",
}


class PayReadyView(APIView):
    def post(self, request):
        user = request.user
        if not user.is_authenticated:
            return Response(
                {"detail": "please signin."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        pay_data = request.data.copy()
        pay_data["cid"] = cid
        response = requests.post(
            payready_url,
            headers=pay_header,
            data=json.dumps(pay_data),
        )
        response_data = response.json()

        if response.status_code == status.HTTP_200_OK:
            Payment.objects.create(
                tid=response_data["tid"],
                partner_order_id=request.data["partner_order_id"],
                partner_user_id=request.data["partner_user_id"],
                point=int(request.data["item_name"]),
                price=request.data["total_amount"],
                user=user,
            )

        return Response(response_data, status=response.status_code)


class PayApproveView(APIView):
    def post(self, request):
        user = request.user
        if not user.is_authenticated:
            return Response(
                {"detail": "please signin."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        serializer = PayApproveRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pg_token = serializer.validated_data["pg_token"]
        tid = serializer.validated_data["tid"]

        try:
            payment = Payment.objects.get(tid=tid, user=user)
        except Payment.DoesNotExist:
            return Response(
                {"detail": "결제 정보를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if payment.pay_status == "approved":
            user_profile = UserProfile.objects.get(user=user)
            return Response(
                {
                    "detail": "이미 처리된 결제입니다.",
                    "point_info": {
                        "old_points": user_profile.remaining_points,
                        "added_points": 0,
                        "new_points": user_profile.remaining_points,
                    },
                },
                status=status.HTTP_200_OK,
            )

        pay_data = {
            "cid": cid,
            "tid": payment.tid,
            "partner_order_id": payment.partner_order_id,
            "partner_user_id": payment.partner_user_id,
            "pg_token": pg_token,
        }

        try:
            response = requests.post(
                payapprove_url,
                headers=pay_header,
                data=json.dumps(pay_data),
                timeout=10,
            )
            response_data = response.json()
        except requests.RequestException:
            return Response(
                {"detail": "카카오페이 승인 서버와 통신할 수 없습니다."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if response.status_code != status.HTTP_200_OK:
            return Response(response_data, status=response.status_code)

        with transaction.atomic():
            locked_payment = Payment.objects.select_for_update().get(
                pk=payment.pk,
                user=user,
            )
            user_profile = UserProfile.objects.select_for_update().get(user=user)
            old_points = user_profile.remaining_points

            if locked_payment.pay_status == "approved":
                added_points = 0
            else:
                added_points = locked_payment.point
                user_profile.remaining_points = old_points + added_points
                user_profile.save(update_fields=["remaining_points"])
                locked_payment.pay_status = "approved"
                locked_payment.save(update_fields=["pay_status"])

            new_points = user_profile.remaining_points

        response_data["point_info"] = {
            "old_points": old_points,
            "added_points": added_points,
            "new_points": new_points,
        }
        return Response(response_data, status=status.HTTP_200_OK)


class PaymentHistoryView(APIView):
    def get(self, request):
        user = request.user
        if not user.is_authenticated:
            return Response(
                {"detail": "please signin."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        approved_payments = Payment.objects.filter(
            user=user,
            pay_status="approved",
        ).order_by("-id")
        payment_history = []
        failed_count = 0

        for payment in approved_payments:
            try:
                response = requests.post(
                    payment_detail_url,
                    headers=pay_header,
                    data=json.dumps({"cid": cid, "tid": payment.tid}),
                    timeout=10,
                )
                if response.status_code != status.HTTP_200_OK:
                    failed_count += 1
                    continue

                order = response.json()
            except (requests.RequestException, ValueError):
                failed_count += 1
                continue

            if not isinstance(order, dict):
                failed_count += 1
                continue

            item_name = order.get("item_name")
            amount = order.get("amount")
            payment_method_type = order.get("payment_method_type")
            approved_at = order.get("approved_at")
            if (
                not isinstance(item_name, str)
                or not isinstance(amount, dict)
                or not isinstance(amount.get("total"), int)
                or not isinstance(payment_method_type, str)
                or not isinstance(approved_at, str)
            ):
                failed_count += 1
                continue

            payment_history.append(
                {
                    "tid": payment.tid,
                    "item_name": item_name,
                    "amount": {"total": amount["total"]},
                    "payment_method_type": payment_method_type,
                    "approved_at": approved_at,
                }
            )

        return Response(
            {
                "payments": payment_history,
                "failed_count": failed_count,
            },
            status=status.HTTP_200_OK,
        )
