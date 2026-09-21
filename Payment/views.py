import requests
from django.conf import settings
from django.db import transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Payment
from .serializers import PayApproveRequestSerializer, PayReadyRequestSerializer
from UserProfile.models import UserProfile


KAKAO_PAY_READY_URL = "https://open-api.kakaopay.com/online/v1/payment/ready"
KAKAO_PAY_APPROVE_URL = "https://open-api.kakaopay.com/online/v1/payment/approve"
KAKAO_PAY_ORDER_URL = "https://open-api.kakaopay.com/online/v1/payment/order"


def kakao_pay_headers():
    return {
        "Content-Type": "application/json",
        "Authorization": f"SECRET_KEY {settings.KAKAO_PAY_KEY}",
    }


class PayReadyView(APIView):
    def post(self, request):
        if not request.user.is_authenticated:
            return Response(
                {"detail": "please signin."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        serializer = PayReadyRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pay_data = {"cid": settings.KAKAO_PAY_CID, **serializer.validated_data}

        try:
            response = requests.post(
                KAKAO_PAY_READY_URL,
                headers=kakao_pay_headers(),
                json=pay_data,
                timeout=10,
            )
            response_data = response.json()
        except requests.RequestException:
            return Response(
                {"detail": "카카오페이 결제 준비 요청에 실패했습니다."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except ValueError:
            return Response(
                {"detail": "카카오페이 응답을 해석하지 못했습니다."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if response.status_code != status.HTTP_200_OK:
            return Response(response_data, status=response.status_code)

        try:
            point_amount = int(serializer.validated_data["item_name"])
        except ValueError:
            return Response(
                {"detail": "item_name은 구매할 소주잔 수여야 합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        Payment.objects.create(
            tid=response_data["tid"],
            partner_order_id=serializer.validated_data["partner_order_id"],
            partner_user_id=serializer.validated_data["partner_user_id"],
            point=point_amount,
            price=serializer.validated_data["total_amount"],
            user=request.user,
        )
        return Response(response_data, status=status.HTTP_200_OK)


class PayApproveView(APIView):
    def post(self, request):
        if not request.user.is_authenticated:
            return Response(
                {"detail": "please signin."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        serializer = PayApproveRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            payment = Payment.objects.get(
                tid=serializer.validated_data["tid"],
                user=request.user,
            )
        except Payment.DoesNotExist:
            return Response(
                {"detail": "결제 준비 이력을 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if payment.pay_status == "approved":
            return Response(
                {"detail": "이미 승인된 결제입니다."},
                status=status.HTTP_409_CONFLICT,
            )

        pay_data = {
            "cid": settings.KAKAO_PAY_CID,
            "tid": payment.tid,
            "partner_order_id": payment.partner_order_id,
            "partner_user_id": payment.partner_user_id,
            "pg_token": serializer.validated_data["pg_token"],
        }

        try:
            response = requests.post(
                KAKAO_PAY_APPROVE_URL,
                headers=kakao_pay_headers(),
                json=pay_data,
                timeout=10,
            )
            response_data = response.json()
        except requests.RequestException:
            return Response(
                {"detail": "카카오페이 결제 승인 요청에 실패했습니다."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except ValueError:
            return Response(
                {"detail": "카카오페이 응답을 해석하지 못했습니다."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if response.status_code != status.HTTP_200_OK:
            return Response(response_data, status=response.status_code)

        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(pk=payment.pk)
            if payment.pay_status == "approved":
                return Response(
                    {"detail": "이미 승인된 결제입니다."},
                    status=status.HTTP_409_CONFLICT,
                )

            user_profile = UserProfile.objects.select_for_update().get(
                user=request.user,
            )
            user_profile.remaining_points += payment.point
            user_profile.save(update_fields=["remaining_points"])

            payment.pay_status = "approved"
            payment.save(update_fields=["pay_status"])

        return Response(response_data, status=status.HTTP_200_OK)


class PaymentHistoryView(APIView):
    def get(self, request):
        if not request.user.is_authenticated:
            return Response(
                {"detail": "please signin."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        payments = Payment.objects.filter(
            user=request.user,
            pay_status="approved",
        ).order_by("-created_at")
        history = []

        for payment in payments:
            try:
                response = requests.post(
                    KAKAO_PAY_ORDER_URL,
                    headers=kakao_pay_headers(),
                    json={"cid": settings.KAKAO_PAY_CID, "tid": payment.tid},
                    timeout=10,
                )
                order_data = response.json()
            except (requests.RequestException, ValueError):
                return Response(
                    {"detail": "카카오페이 주문 조회에 실패했습니다."},
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            if response.status_code != status.HTTP_200_OK:
                return Response(order_data, status=response.status_code)

            amount = order_data.get("amount", {})
            history.append(
                {
                    "tid": payment.tid,
                    "item_name": order_data.get("item_name", f"소주잔 {payment.point}잔"),
                    "amount": amount.get("total", payment.price),
                    "payment_method_type": order_data.get("payment_method_type", "-"),
                    "approved_at": order_data.get("approved_at", "-"),
                }
            )

        return Response(history, status=status.HTTP_200_OK)
