import uuid
import requests

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response

from .models import Point
from .models import Payment
from .serializers import PointSerializer
from UserProfile.models import UserProfile
from django.conf import settings
from django.utils.dateparse import parse_datetime

from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from .request_serializers import PointRequestSerializer

# Create your views here.
class PointListView(APIView):
    @swagger_auto_schema(
        operation_id="포인트 조회",
        operation_description="DB에 저장된 모든 포인트 정보를 조회합니다.",  
        request_body=None,
        responses={200: PointSerializer(many=True)}
    )
    def get(self, request):
        points = Point.objects.all()
        serializer = PointSerializer(points, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_id="포인트 생성",
        operation_description="""
        DB에 새로운 포인트 정보를 생성합니다.
        price: 포인트의 가격
        point: 포인트의 양
        참고: price는 문자열로 저장됩니다. (ex. "1000원")
        """,
        request_body=PointRequestSerializer,
        responses={400: "fields missing.", 201: PointSerializer}
    )
    def post(self, request):
        price = request.data.get('price')
        point = request.data.get('point')
        if not price or not point:
            return Response({"detail": "fields missing."}, status=status.HTTP_400_BAD_REQUEST)
        point = Point.objects.create(price=price, point=point)
        serializer = PointSerializer(point)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class PaymentReadyView(APIView):
    def post(self, request):
        if not request.user.is_authenticated:
            return Response({"detail": "please signin"}, status=status.HTTP_401_UNAUTHORIZED)

        quantity = request.data.get("quantity")
        total_amount = request.data.get("total_amount")
        item_name = request.data.get("item_name", "소주잔 충전")
        if not isinstance(quantity, int) or not isinstance(total_amount, int) or quantity <= 0 or total_amount <= 0:
            return Response({"detail": "quantity와 total_amount는 0보다 큰 정수여야 합니다."}, status=status.HTTP_400_BAD_REQUEST)

        partner_order_id = f"order_{uuid.uuid4().hex}"
        payment = Payment.objects.create(
            user=request.user,
            partner_order_id=partner_order_id,
            item_name=item_name,
            quantity=quantity,
            total_amount=total_amount,
        )
        try:
            kakao_response = requests.post(
                "https://open-api.kakaopay.com/online/v1/payment/ready",
                headers={
                    "Authorization": f"SECRET_KEY {settings.KAKAO_PAY_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "cid": settings.KAKAO_PAY_CID,
                    "partner_order_id": partner_order_id,
                    "partner_user_id": str(request.user.id),
                    "item_name": item_name,
                    "quantity": quantity,
                    "total_amount": total_amount,
                    "tax_free_amount": 0,
                    "approval_url": f"{settings.FRONTEND_URL}/payment/approve",
                    "cancel_url": f"{settings.FRONTEND_URL}/payment/cancel",
                    "fail_url": f"{settings.FRONTEND_URL}/payment/fail",
                },
                timeout=10,
            )
            kakao_response.raise_for_status()
            data = kakao_response.json()
        except requests.RequestException:
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status", "updated_at"])
            return Response({"detail": "결제 준비 요청에 실패했습니다."}, status=status.HTTP_502_BAD_GATEWAY)

        payment.tid = data["tid"]
        payment.save(update_fields=["tid", "updated_at"])
        return Response({
            "partner_order_id": partner_order_id,
            "tid": payment.tid,
            "next_redirect_pc_url": data["next_redirect_pc_url"],
        }, status=status.HTTP_200_OK)


class PaymentApproveView(APIView):
    def post(self, request):
        if not request.user.is_authenticated:
            return Response({"detail": "please signin"}, status=status.HTTP_401_UNAUTHORIZED)

        partner_order_id = request.data.get("partner_order_id")
        pg_token = request.data.get("pg_token")
        if not partner_order_id or not pg_token:
            return Response({"detail": "partner_order_id와 pg_token이 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payment = Payment.objects.get(partner_order_id=partner_order_id, user=request.user)
        except Payment.DoesNotExist:
            return Response({"detail": "결제 정보를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)
        if payment.status == Payment.Status.APPROVED:
            return Response({"detail": "이미 승인된 결제입니다."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            kakao_response = requests.post(
                "https://open-api.kakaopay.com/online/v1/payment/approve",
                headers={
                    "Authorization": f"SECRET_KEY {settings.KAKAO_PAY_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "cid": settings.KAKAO_PAY_CID,
                    "tid": payment.tid,
                    "partner_order_id": payment.partner_order_id,
                    "partner_user_id": str(request.user.id),
                    "pg_token": pg_token,
                },
                timeout=10,
            )
            kakao_response.raise_for_status()
            data = kakao_response.json()
        except requests.RequestException:
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status", "updated_at"])
            return Response({"detail": "결제 승인 요청에 실패했습니다."}, status=status.HTTP_502_BAD_GATEWAY)

        payment.status = Payment.Status.APPROVED
        payment.approved_at = parse_datetime(data.get("approved_at", ""))
        payment.save(update_fields=["status", "approved_at", "updated_at"])
        profile = UserProfile.objects.get(user=request.user)
        profile.remaining_points += payment.quantity
        profile.save(update_fields=["remaining_points"])

        return Response({"payment": serialize_payment(payment), "user_profile": {"remaining_points": profile.remaining_points}})


class PaymentHistoryView(APIView):
    def get(self, request):
        if not request.user.is_authenticated:
            return Response({"detail": "please signin"}, status=status.HTTP_401_UNAUTHORIZED)

        payments = Payment.objects.filter(user=request.user).order_by("-created_at")
        # 카카오페이 주문 조회 API를 호출해 최신 결제 상태를 확인한다.
        result = []
        for payment in payments:
            item = serialize_payment(payment)
            if payment.tid:
                try:
                    kakao_response = requests.post(
                        "https://open-api.kakaopay.com/online/v1/payment/order",
                        headers={"Authorization": f"SECRET_KEY {settings.KAKAO_PAY_KEY}", "Content-Type": "application/json"},
                        json={"cid": settings.KAKAO_PAY_CID, "tid": payment.tid},
                        timeout=5,
                    )
                    if kakao_response.ok:
                        kakao_data = kakao_response.json()
                        item["kakao_status"] = kakao_data.get("status")
                except requests.RequestException:
                    item["kakao_status"] = None
            result.append(item)
        return Response(result)


def serialize_payment(payment):
    return {
        "id": payment.id,
        "partner_order_id": payment.partner_order_id,
        "item_name": payment.item_name,
        "quantity": payment.quantity,
        "total_amount": payment.total_amount,
        "status": payment.status,
        "approved_at": payment.approved_at,
        "created_at": payment.created_at,
    }
