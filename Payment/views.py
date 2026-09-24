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

from .Serializers import PayReadyRequestSerializer, PayApproveRequestSerializer, PayApproveResponseSerializer, PayReadyResponseSerializer

from django.conf import settings

pay_key = settings.KAKAO_PAY_KEY
cid = settings.KAKAO_PAY_CID

payready_url = 'https://open-api.kakaopay.com/online/v1/payment/ready'
payapprove_url = 'https://open-api.kakaopay.com/online/v1/payment/approve'

pay_header = {
    'Content-Type': 'application/json',
    'Authorization': f'SECRET_KEY {pay_key}'
}
class PayReadyView(APIView):
    def post(self, request):
        ## request는 프론트엔드에서 전송한 요청. 그 본문을  pay_data에 담는다.
        pay_data = request.data

        ## access token으로 사용자를 확인
        user = request.user
        if not user.is_authenticated:
            return Response({"detail": "please signin."}, status=status.HTTP_401_UNAUTHORIZED)

        ## request에서 받아온 요청 본문에 cid를 붙이고 json 형태로 바꿔서 카카오페이에 보낼 요청 본문 완성
        pay_data['cid'] = cid
        pay_data = json.dumps(pay_data)

        ## payready_url에 헤더와 본문(data)를 실제 요청
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
    def post(self, request):
    
        #### 1
        user = request.user
        if not user.is_authenticated:
            return Response({"detail": "please signin."}, status=status.HTTP_401_UNAUTHORIZED)

        #### 2
        pg_token = request.data['pg_token']
        tid = request.data['tid']
        
        #### 3
        pay_hist = Payment.objects.get(tid=tid)
        pay_data = {
            'cid': cid,
            'tid': tid,
            'partner_order_id': pay_hist.partner_order_id,
            'partner_user_id': pay_hist.partner_user_id,
            'pg_token': pg_token
        }
        
        #### 4
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
                        
                        # 포인트 업데이트 (이미 승인된 결제가 아닌 경우에만)
                        point_info = {
                            'old_points': userprofile.remaining_points,
                            'added_points': 0,
                            'new_points': userprofile.remaining_points
                        }
                        
                        if not was_already_approved:
                            # 포인트 업데이트 전후 로깅
                            old_points = userprofile.remaining_points
                            added_points = int(pay_hist.point)
                            
                            # 직접 계산하여 업데이트 (F() 표현식 대신)
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
                        # 최대 재시도 횟수 초과
                        print(f"Database error after {max_retries} attempts: {e}")
                        return Response(
                            {"detail": "결제 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."}, 
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR
                        )
                except Exception as e:
                    # 기타 예상치 못한 오류
                    print(f"Unexpected error in payment approval: {e}")
                    return Response(
                        {"detail": "결제 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."}, 
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )

        return Response(response.json(), status=response.status_code)

payorder_url = 'https://open-api.kakaopay.com/online/v1/payment/order'  # 기존 payready_url, payapprove_url 옆에 추가

class PaymentOrderListView(APIView):
    def get(self, request):
        user = request.user
        if not user.is_authenticated:
            return Response({"detail": "please signin."}, status=status.HTTP_401_UNAUTHORIZED)

        # 1. 우리 DB에서 이 유저의 결제완료(approved) 내역만 먼저 꺼냄
        payments = Payment.objects.filter(user=user, pay_status='approved')

        # 2. 각 tid로 카카오페이 주문조회 API를 한 건씩 호출
        order_list = []
        for payment in payments:
            order_data = json.dumps({'cid': cid, 'tid': payment.tid})
            response = requests.post(payorder_url, headers=pay_header, data=order_data)

            if response.status_code == 200:
                order_info = response.json()
                order_list.append({
                    'tid': payment.tid,
                    'item_name': order_info.get('item_name'),
                    'payment_method_type': order_info.get('payment_method_type'),
                    'approved_at': order_info.get('approved_at'),
                    'amount': order_info.get('amount', {}).get('total'),  # amount는 객체라서 .get('total')
                })

        return Response(order_list, status=status.HTTP_200_OK)
