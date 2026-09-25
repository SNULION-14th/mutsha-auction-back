import uuid
import logging

import requests
from django.conf import settings
from django.db import transaction
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from UserProfile.models import UserProfile
from .models import Payment
from .serializers import PaymentApproveSerializer, PaymentReadySerializer

KAKAO_PAY_BASE_URL = "https://open-api.kakaopay.com/online/v1/payment"
KAKAO_PAY_TEST_CID = "TC0ONETIME"
logger = logging.getLogger(__name__)


def kakao_headers():
    key_type = "DEV_SECRET_KEY" if settings.KAKAO_PAY_KEY.startswith("DEV") else "SECRET_KEY"
    return {"Authorization": f"{key_type} {settings.KAKAO_PAY_KEY}", "Content-Type": "application/json"}


def kakao_error_response(operation, exc):
    """Log an upstream error without exposing the configured secret key."""
    response = exc.response
    if response is None:
        logger.error("KakaoPay %s request error: %s", operation, str(exc))
        return Response({"detail": f"KakaoPay {operation} request failed"}, status=status.HTTP_502_BAD_GATEWAY)

    response_text = response.text
    if settings.KAKAO_PAY_KEY:
        response_text = response_text.replace(settings.KAKAO_PAY_KEY, "[REDACTED]")
    response_text = response_text[:2000]
    logger.error("KakaoPay %s failed: status=%s body=%s", operation, response.status_code, response_text)
    try:
        upstream = response.json()
    except ValueError:
        upstream = {}
    error = {
        "code": upstream.get("error_code", response.status_code),
        "message": upstream.get("error_message", response_text),
    }
    return Response(
        {"detail": f"KakaoPay {operation} request failed", "kakao_error": error},
        status=response.status_code if 400 <= response.status_code < 600 else status.HTTP_502_BAD_GATEWAY,
    )


def authenticated_user_or_response(request):
    if not request.user.is_authenticated:
        return None, Response({"detail": "authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
    if not settings.KAKAO_PAY_KEY:
        logger.warning("KakaoPay request rejected because KAKAO_PAY_KEY is not configured")
        return None, Response({"detail": "KAKAO_PAY_KEY is not configured"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return request.user, None


class PaymentReadyView(APIView):
    def post(self, request):
        user, error = authenticated_user_or_response(request)
        if error:
            return error
        serializer = PaymentReadySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order_id = f"order_{uuid.uuid4().hex}"
        payload = {"cid": KAKAO_PAY_TEST_CID, "partner_order_id": order_id, "partner_user_id": str(user.pk), **serializer.validated_data,
                   "tax_free_amount": 0,
                   "approval_url": f"{settings.KAKAO_REDIRECT_URI.rsplit('/auth', 1)[0]}/payment/approve",
                   "cancel_url": f"{settings.KAKAO_REDIRECT_URI.rsplit('/auth', 1)[0]}/payment/cancel",
                   "fail_url": f"{settings.KAKAO_REDIRECT_URI.rsplit('/auth', 1)[0]}/payment/fail"}
        try:
            kakao_response = requests.post(f"{KAKAO_PAY_BASE_URL}/ready", headers=kakao_headers(), json=payload, timeout=10)
            kakao_response.raise_for_status()
            data = kakao_response.json()
            tid = data.get("tid")
        except requests.HTTPError as exc:
            return kakao_error_response("ready", exc)
        except requests.RequestException as exc:
            return kakao_error_response("ready", exc)
        except ValueError:
            logger.error("KakaoPay ready returned invalid JSON")
            return Response({"detail": "KakaoPay ready returned invalid JSON"}, status=status.HTTP_502_BAD_GATEWAY)
        if not tid or not data.get("next_redirect_pc_url"):
            return Response({"detail": "Invalid KakaoPay ready response"}, status=status.HTTP_502_BAD_GATEWAY)
        Payment.objects.create(user=user, tid=tid, partner_order_id=order_id, **serializer.validated_data)
        return Response({"tid": tid, "next_redirect_pc_url": data["next_redirect_pc_url"]}, status=status.HTTP_201_CREATED)


class PaymentApprovalView(APIView):
    def post(self, request):
        user, error = authenticated_user_or_response(request)
        if error:
            return error
        serializer = PaymentApproveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payment = Payment.objects.get(tid=serializer.validated_data["tid"], user=user)
        except Payment.DoesNotExist:
            return Response({"detail": "payment not found"}, status=status.HTTP_404_NOT_FOUND)
        if payment.status == Payment.Status.APPROVED:
            return Response({"detail": "payment already approved"}, status=status.HTTP_409_CONFLICT)
        if payment.status != Payment.Status.READY:
            return Response({"detail": "payment cannot be approved"}, status=status.HTTP_400_BAD_REQUEST)
        payload = {"cid": KAKAO_PAY_TEST_CID, "tid": payment.tid, "partner_order_id": payment.partner_order_id,
                   "partner_user_id": str(user.pk), "pg_token": serializer.validated_data["pg_token"]}
        try:
            kakao_response = requests.post(f"{KAKAO_PAY_BASE_URL}/approve", headers=kakao_headers(), json=payload, timeout=10)
            kakao_response.raise_for_status()
            data = kakao_response.json()
        except requests.HTTPError as exc:
            return kakao_error_response("approve", exc)
        except requests.RequestException as exc:
            return kakao_error_response("approve", exc)
        except ValueError:
            logger.error("KakaoPay approve returned invalid JSON")
            return Response({"detail": "KakaoPay approve returned invalid JSON"}, status=status.HTTP_502_BAD_GATEWAY)
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(pk=payment.pk)
            if payment.status == Payment.Status.APPROVED:
                return Response({"detail": "payment already approved"}, status=status.HTTP_409_CONFLICT)
            payment.status = Payment.Status.APPROVED
            payment.approved_at = parse_datetime(data["approved_at"]) if data.get("approved_at") else None
            payment.save(update_fields=["status", "approved_at", "updated_at"])
            profile, _ = UserProfile.objects.select_for_update().get_or_create(user=user)
            profile.remaining_points += payment.quantity
            profile.save(update_fields=["remaining_points"])
        return Response({"tid": payment.tid, "status": payment.status, "remaining_points": profile.remaining_points})


class PaymentHistoryView(APIView):
    def get(self, request):
        user, error = authenticated_user_or_response(request)
        if error:
            return error
        payments = Payment.objects.filter(user=user, status=Payment.Status.APPROVED)
        history = []
        for payment in payments:
            try:
                response = requests.get(f"{KAKAO_PAY_BASE_URL}/order", headers=kakao_headers(), params={"cid": KAKAO_PAY_TEST_CID, "tid": payment.tid}, timeout=10)
                response.raise_for_status()
                order = response.json()
            except (requests.RequestException, ValueError):
                # Preserve an approved local record even if the provider is temporarily unavailable.
                order = {}
            amount = order.get("amount", {"total": payment.total_amount})
            history.append({"tid": payment.tid, "item_name": order.get("item_name", payment.item_name), "amount": amount,
                            "payment_method_type": order.get("payment_method_type", ""),
                            "approved_at": order.get("approved_at") or (payment.approved_at.isoformat() if payment.approved_at else None)})
        return Response(history)
