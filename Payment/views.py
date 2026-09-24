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

### 결제 승인 단계에서 쓰임 ###
import time
from django.db import transaction
from django.db.utils import OperationalError, IntegrityError

from .serializers import PayReadyRequestSerializer, PayApproveRequestSerializer, PayReadyResponseSerializer, PayApproveResponseSerializer

### 등록된 환경변수 정보 가져오기
from django.conf import settings

### 환경변수로 등록된 값 중, KAKAO_PAY_KEY 값 가져와 변수에 넣기
pay_key = settings.KAKAO_PAY_KEY
cid = settings.KAKAO_PAY_CID

### 결제 준비 API 요청 URL 정의하기
payready_url = 'https://open-api.kakaopay.com/online/v1/payment/ready'
### 결제 승인 API 요청시 사용될 URL
payapprove_url = 'https://open-api.kakaopay.com/online/v1/payment/approve'
### 주문 조회 API 요청시 사용될 URL (심화 과제)
payorder_url = 'https://open-api.kakaopay.com/online/v1/payment/order'

pay_header = {
    'Content-Type': 'application/json',
    'Authorization': f'SECRET_KEY {pay_key}'
}


class PayReadyView(APIView):
    @swagger_auto_schema(
        operation_id="카카오페이 결제 준비",
        operation_description="카카오페이 결제를 준비하고, 결제 화면으로 리다이렉트할 url을 발급받습니다.",
        request_body=PayReadyRequestSerializer,
        responses={200: PayReadyResponseSerializer, 401: "please signin."},
    )
    def post(self, request):
        pay_data = request.data

        user = request.user
        if not user.is_authenticated:
            return Response({"detail": "please signin."}, status=status.HTTP_401_UNAUTHORIZED)

        pay_data['cid'] = cid
        pay_data = json.dumps(pay_data)

        response = requests.post(payready_url, headers=pay_header, data=pay_data)
        response_data = response.json()

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

        return Response(response.json(), status=response.status_code)


class PayApproveView(APIView):
    @swagger_auto_schema(
        operation_id="카카오페이 결제 승인",
        operation_description="pg_token과 tid를 이용해 결제를 승인하고, 유저의 잔여 소주잔을 증가시킵니다.",
        request_body=PayApproveRequestSerializer,
        responses={200: PayApproveResponseSerializer, 401: "please signin.", 500: "결제 처리 중 오류가 발생했습니다."},
    )
    def post(self, request):

        user = request.user
        if not user.is_authenticated:
            return Response({"detail": "please signin."}, status=status.HTTP_401_UNAUTHORIZED)

        pg_token = request.data['pg_token']
        tid = request.data['tid']

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

                        pay_hist.pay_status = 'approved'
                        pay_hist.save()

                    response_data['point_info'] = point_info
                    return Response(response_data, status=response.status_code)

                except (OperationalError, IntegrityError) as e:
                    if attempt < max_retries - 1:
                        print(f"Database lock error (attempt {attempt + 1}): {e}")
                        time.sleep(retry_delay * (2 ** attempt))
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


class PaymentHistoryView(APIView):
    @swagger_auto_schema(
        operation_id="결제 내역 조회 (심화)",
        operation_description="로그인한 유저의 결제 완료 내역을, 카카오페이 주문 조회 api를 통해 상세 정보와 함께 반환합니다.",
        request_body=None,
        responses={200: "결제 내역 리스트", 401: "please signin."},
    )
    def get(self, request):
        user = request.user
        if not user.is_authenticated:
            return Response({"detail": "please signin."}, status=status.HTTP_401_UNAUTHORIZED)

        # 이 유저의 결제 완료(approved) 내역을 최신순으로 가져옴
        pay_hists = Payment.objects.filter(user=user, pay_status='approved').order_by('-id')

        history_list = []
        for pay_hist in pay_hists:
            order_data = {
                'cid': cid,
                'tid': pay_hist.tid,
            }
            response = requests.post(
                payorder_url,
                headers=pay_header,
                data=json.dumps(order_data),
            )

            if response.status_code != 200:
                # 주문 조회 실패한 건은 건너뜀 (예: 오래되어 조회 기간이 지난 결제)
                continue

            order_info = response.json()
            history_list.append({
                'tid': pay_hist.tid,
                'item_name': order_info.get('item_name'),
                'amount': order_info.get('amount', {}).get('total'),
                'payment_method_type': order_info.get('payment_method_type'),
                'approved_at': order_info.get('approved_at'),
            })

        return Response(history_list, status=status.HTTP_200_OK)
