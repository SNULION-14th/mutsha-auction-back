import json
import time

import requests
from django.conf import settings
from django.db import transaction
from django.db.utils import IntegrityError, OperationalError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from UserProfile.models import UserProfile
from .models import Payment
from .serializers import (
    PayApproveRequestSerializer,
    PayApproveResponseSerializer,
    PayReadyRequestSerializer,
    PayReadyResponseSerializer,
)

pay_key = settings.KAKAO_PAY_KEY
cid = settings.KAKAO_PAY_CID
payready_url = "https://open-api.kakaopay.com/online/v1/payment/ready"
payapprove_url = "https://open-api.kakaopay.com/online/v1/payment/approve"
pay_header = {
    "Content-Type": "application/json",
    "Authorization": f"SECRET_KEY {pay_key}",
}


class PayReadyView(APIView):
    def post(self, request):
        pay_data = request.data.copy()

        user = request.user
        if not user.is_authenticated:
            return Response({"detail": "please signin."}, status=status.HTTP_401_UNAUTHORIZED)

        pay_data["cid"] = cid
        response = requests.post(payready_url, headers=pay_header, data=json.dumps(pay_data))
        response_data = response.json()

        if response.status_code == 200:
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
            return Response({"detail": "please signin."}, status=status.HTTP_401_UNAUTHORIZED)

        pg_token = request.data["pg_token"]
        tid = request.data["tid"]

        pay_hist = Payment.objects.get(tid=tid)
        pay_data = {
            "cid": cid,
            "tid": tid,
            "partner_order_id": pay_hist.partner_order_id,
            "partner_user_id": pay_hist.partner_user_id,
            "pg_token": pg_token,
        }
        response = requests.post(
            payapprove_url,
            headers=pay_header,
            data=json.dumps(pay_data),
        )

        if response.status_code == 200:
            response_data = response.json()
            was_already_approved = pay_hist.pay_status == "approved"
            max_retries = 3
            retry_delay = 0.1

            for attempt in range(max_retries):
                try:
                    with transaction.atomic():
                        userprofile = UserProfile.objects.select_for_update().get(user=user)
                        point_info = {
                            "old_points": userprofile.remaining_points,
                            "added_points": 0,
                            "new_points": userprofile.remaining_points,
                        }

                        if not was_already_approved:
                            old_points = userprofile.remaining_points
                            added_points = int(pay_hist.point)
                            new_points = old_points + added_points
                            userprofile.remaining_points = new_points
                            userprofile.save()
                            point_info = {
                                "old_points": old_points,
                                "added_points": added_points,
                                "new_points": new_points,
                            }

                        pay_hist.pay_status = "approved"
                        pay_hist.save()

                    response_data["point_info"] = point_info
                    return Response(response_data, status=response.status_code)
                except (OperationalError, IntegrityError) as error:
                    if attempt < max_retries - 1:
                        print(f"Database lock error (attempt {attempt + 1}): {error}")
                        time.sleep(retry_delay * (2**attempt))
                        continue
                    return Response(
                        {"detail": "결제 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )
                except Exception as error:
                    print(f"Unexpected error in payment approval: {error}")
                    return Response(
                        {"detail": "결제 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )

        return Response(response.json(), status=response.status_code)
