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

### 아래 3줄은 결제 승인 단계(Step 5)에서 쓰이니 같이 넣어 두세요 ###
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
### 이건 나중에 결제 승인 API 요청시 사용될 URL !
payapprove_url = 'https://open-api.kakaopay.com/online/v1/payment/approve'

pay_header = {
    'Content-Type': 'application/json',
    'Authorization': f'SECRET_KEY {pay_key}'
}

class PayReadyView(APIView):
    def post(self, request):
        #### 1
        pay_data = request.data

        #### 2
        user = request.user
        if not user.is_authenticated:
            return Response({"detail": "please signin."}, status=status.HTTP_401_UNAUTHORIZED)
        
        #### 3
        pay_data['cid'] = cid
        pay_data = json.dumps(pay_data)

        #### 4
        response = requests.post(payready_url, headers=pay_header, data=pay_data)
        response_data = response.json()

         ### 🔻 이 부분 추가 ###
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