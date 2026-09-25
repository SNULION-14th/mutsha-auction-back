from django.shortcuts import render
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import Payment
from UserProfile.models import UserProfile
import requests
import json

from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

import time
from django.db import transaction
from django.db.utils import OperationalError, IntegrityError

from .serializers import PayReadyRequestSerializer, PayApproveRequestSerializer, PayReadyResponseSerializer, PayApproveResponseSerializer

### 등록된 환경변수 정보 가져오기
from django.conf import settings

### 환경변수로 등록된 값 중, KAKAO_PAY_KEY / KAKAO_PAY_CID 값 가져와 변수에 넣기
pay_key = settings.KAKAO_PAY_KEY
cid = settings.KAKAO_PAY_CID

### 결제 준비 / 결제 승인 API 요청 URL
payready_url = 'https://open-api.kakaopay.com/online/v1/payment/ready'
payapprove_url = 'https://open-api.kakaopay.com/online/v1/payment/approve'

pay_header = {
    'Content-Type': 'application/json',
    'Authorization': f'SECRET_KEY {pay_key}'
}


class PayReadyView(APIView):
    @swagger_auto_schema(
        operation_id="카카오페이 결제 준비",
        operation_description="카카오페이 단건결제 준비 요청을 보내고, 결제창 URL과 tid를 반환합니다.",
        request_body=PayReadyRequestSerializer,
        responses={200: PayReadyResponseSerializer, 401: "Unauthorized"},
    )
    def post(self, request):
        pay_data = request.data

        ### 로그인한 사용자만 결제 요청 가능
        user = request.user
        if not user.is_authenticated:
            return Response({"detail": "please signin."}, status=status.HTTP_401_UNAUTHORIZED)

        ### 요청 본문에 cid를 붙여 카카오페이에 보낼 데이터 완성
        pay_data['cid'] = cid
        pay_data = json.dumps(pay_data)

        response = requests.post(payready_url, headers=pay_header, data=pay_data)
        response_data = response.json()

        ### 결제 준비 성공 시 tid와 함께 결제 요청 이력을 DB에 저장
        if response.status_code == 200:
            item_name = request.data['item_name']
            point_amount = int(item_name)

            Payment.objects.create(
                tid=response_data['tid'],
                partner_order_id=request.data['partner_order_id'],
                partner_user_id=request.data['partner_user_id'],
                point=point_amount,
                price=request.data['total_amount'],
                user=user
            )

        return Response(response_data, status=response.status_code)


class PayApproveView(APIView):
    @swagger_auto_schema(
        operation_id="카카오페이 결제 승인",
        operation_description="pg_token과 tid로 결제를 최종 승인하고, 구매한 소주잔을 충전합니다.",
        request_body=PayApproveRequestSerializer,
        responses={200: PayApproveResponseSerializer, 401: "Unauthorized"},
    )
    def post(self, request):
        user = request.user
        if not user.is_authenticated:
            return Response({"detail": "please signin."}, status=status.HTTP_401_UNAUTHORIZED)

        pg_token = request.data['pg_token']
        tid = request.data['tid']

        ### tid로 결제 준비 때 저장해 둔 이력을 불러와 승인 요청 데이터 구성
        pay_hist = Payment.objects.get(tid=tid)
        pay_data = {
            'cid': cid,
            'tid': tid,
            'partner_order_id': pay_hist.partner_order_id,
            'partner_user_id': pay_hist.partner_user_id,
            'pg_token': pg_token
        }
        pay_data = json.dumps(pay_data)
        response = requests.post(payapprove_url, headers=pay_header, data=pay_data)

        if response.status_code == 200:
            response_data = response.json()

            # 이미 승인된 결제인지 확인
            was_already_approved = pay_hist.pay_status == 'approved'

            # 원자적 트랜잭션으로 중복 처리 방지 (재시도 로직 포함)
            max_retries = 3
            retry_delay = 0.1  # 100ms

            for attempt in range(max_retries):
                try:
                    with transaction.atomic():
                        # select_for_update로 동시성 제어
                        userprofile = UserProfile.objects.select_for_update().get(user=user)

                        point_info = {
                            'old_points': userprofile.remaining_points,
                            'added_points': 0,
                            'new_points': userprofile.remaining_points
                        }

                        # 포인트 업데이트 (이미 승인된 결제가 아닌 경우에만)
                        if not was_already_approved:
                            old_points = userprofile.remaining_points
                            added_points = int(pay_hist.point)
                            new_points = old_points + added_points
                            userprofile.remaining_points = new_points
                            userprofile.save()

                            point_info = {
                                'old_points': old_points,
                                'added_points': added_points,
                                'new_points': new_points
                            }

                        # 결제 상태 업데이트
                        pay_hist.pay_status = 'approved'
                        pay_hist.save()

                    response_data['point_info'] = point_info
                    return Response(response_data, status=response.status_code)

                except (OperationalError, IntegrityError) as e:
                    if attempt < max_retries - 1:
                        # 데이터베이스 잠금 오류 시 재시도
                        print(f"Database lock error (attempt {attempt + 1}): {e}")
                        time.sleep(retry_delay * (2 ** attempt))  # 지수 백오프
                        continue
                    else:
                        print(f"Database error after {max_retries} attempts: {e}")
                        return Response(
                            {"detail": "결제 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR
                        )
                except Exception as e:
                    print(f"Unexpected error in payment approval: {e}")
                    return Response(
                        {"detail": "결제 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )

        return Response(response.json(), status=response.status_code)
