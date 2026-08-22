from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.utils import timezone
from django.db.models import Q
from django.db import transaction
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import random

from .models import Auction, Bid
from .serializers import (
    AuctionSerializer, AuctionListSerializer, AuctionCreateSerializer, 
    BidSerializer, MyAuctionHistorySerializer, MyBidHistorySerializer
)
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi


class RecommendedAuctionsView(APIView):
    """오늘의 추천 경매 API"""
    permission_classes = [AllowAny]
    
    @swagger_auto_schema(
        operation_id="오늘의 추천 경매",
        operation_description="진행중인 경매 중에서 랜덤으로 2개의 경매를 추천합니다.",
        responses={200: AuctionListSerializer(many=True)},
    )
    def get(self, request):
        # 현재 진행중인 경매만 필터링
        active_auctions = Auction.objects.filter(
            status='active',
            end_time__gt=timezone.now()
        ).order_by('?')[:2]  # 랜덤으로 2개 선택

        serializer = AuctionListSerializer(active_auctions, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class AuctionListView(APIView):
    """경매 목록 API"""
    permission_classes = [AllowAny]
    
    @swagger_auto_schema(
        operation_id="경매 목록 조회",
        operation_description="진행중인 경매 목록을 조회합니다.",
        manual_parameters=[
            openapi.Parameter('status', openapi.IN_QUERY, description="경매 상태 (active, ended, cancelled)", type=openapi.TYPE_STRING),
            openapi.Parameter('search', openapi.IN_QUERY, description="검색어", type=openapi.TYPE_STRING),
        ],
        responses={200: AuctionListSerializer(many=True)},
    )
    def get(self, request):
        # 종료된 경매 처리
        ended_auctions = Auction.objects.filter(status='active', end_time__lt=timezone.now())
        for auction in ended_auctions:
            auction.status = 'ended'
            # 최고 입찰자를 winner로 설정
            highest_bid = auction.bids.order_by('-amount').first()
            if highest_bid:
                auction.winner = highest_bid.bidder
            auction.save()
        
        auctions = Auction.objects.all()
        
        # 상태 필터링
        status_filter = request.query_params.get('status')
        if status_filter:
            auctions = auctions.filter(status=status_filter)
        
        # 검색 필터링
        search = request.query_params.get('search')
        if search:
            auctions = auctions.filter(
                Q(title__icontains=search) | Q(description__icontains=search)
            )
        
        # 최신순 정렬
        auctions = auctions.order_by('-created_at')
        
        serializer = AuctionListSerializer(auctions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class AuctionDetailView(APIView):
    """경매 상세 조회 API"""
    permission_classes = [AllowAny]
    
    @swagger_auto_schema(
        operation_id="경매 상세 조회",
        operation_description="특정 경매의 상세 정보를 조회합니다.",
        responses={200: AuctionSerializer, 404: "경매를 찾을 수 없습니다."},
    )
    def get(self, request, auction_id):
        try:
            auction = Auction.objects.get(id=auction_id)
            
            # 경매가 종료되었는지 확인하고 winner 설정
            if auction.status == 'active' and auction.end_time < timezone.now():
                auction.status = 'ended'
                highest_bid = auction.bids.order_by('-amount').first()
                if highest_bid:
                    auction.winner = highest_bid.bidder
                auction.save()
            
            serializer = AuctionSerializer(auction, context={'request': request})
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Auction.DoesNotExist:
            return Response(
                {"detail": "경매를 찾을 수 없습니다."}, 
                status=status.HTTP_404_NOT_FOUND
            )


class AuctionCreateView(APIView):
    """경매 생성 API"""
    
    @swagger_auto_schema(
        operation_id="경매 생성",
        operation_description="새로운 경매를 생성합니다.",
        request_body=AuctionCreateSerializer,
        responses={201: AuctionSerializer, 400: "Bad Request", 401: "please signin"},
        manual_parameters=[openapi.Parameter("Authorization", openapi.IN_HEADER, description="access token", type=openapi.TYPE_STRING)]
    )
    def post(self, request):
        user = request.user
        if not user.is_authenticated:
            return Response({"detail": "please signin"}, status=status.HTTP_401_UNAUTHORIZED)
        
        serializer = AuctionCreateSerializer(data=request.data)
        if serializer.is_valid():
            # 현재 로그인한 사용자를 판매자로 설정
            auction = serializer.save(seller=user)
            response_serializer = AuctionSerializer(auction)

            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "global_notifications",
                {
                    "type": "auction_created",
                    "data" : f"새 경매 [{auction.title}]가 등록되었습니다!"
                },
            )

            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class BidCreateView(APIView):
    """입찰 생성 API"""

    @swagger_auto_schema(
        operation_id="입찰하기",
        operation_description="경매에 입찰합니다.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'amount': openapi.Schema(
                    type=openapi.TYPE_INTEGER,
                    description="입찰가",
                )
            },
        ),
        responses={201: BidSerializer, 400: "Bad Request", 401: "please signin", 404: "경매를 찾을 수 없습니다."},
        manual_parameters=[openapi.Parameter("Authorization", openapi.IN_HEADER, description="access token", type=openapi.TYPE_STRING)]
    )
    def post(self, request, auction_id):
        user = request.user
        if not user.is_authenticated:
            return Response({"detail": "please signin"}, status=status.HTTP_401_UNAUTHORIZED)

        amount = request.data.get('amount')

        if not amount:
            return Response(
                {"detail": "입찰가를 입력해주세요."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 입찰은 atomic하게... 여러 명이 한번에 하면 문제 발생!!
        try:
            with transaction.atomic():
                auction = Auction.objects.select_for_update().get(id=auction_id)

                if not auction.is_active:
                    return Response(
                        {"detail": "진행중인 경매가 아닙니다."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                if amount <= auction.current_price:
                    return Response(
                        {"detail": "현재가보다 높은 금액을 입찰해야 합니다."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                bid = Bid.objects.create(
                    auction=auction,
                    bidder=user,
                    amount=amount
                )

                auction.current_price = amount
                auction.save()

            # 실시간 입찰 정보 broadcast하기 ~ ^_^
            # 새롭게 업데이트 된 auction 정보 전체를 시리얼라이저로 보냅니다

            serializer = AuctionSerializer(auction, context={'request': request})

            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"auction_{auction_id}",
                {
                    "type": "auction_update",
                    "data": serializer.data,
                },
            )

            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Auction.DoesNotExist:
            return Response(
                {"detail": "경매를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND
            )

class MyAuctionHistoryView(APIView):
    """내가 등록한 경매 히스토리 API"""
    
    @swagger_auto_schema(
        operation_id="내가 등록한 경매 히스토리",
        operation_description="로그인한 사용자가 판매자로 등록한 경매 목록을 조회합니다.",
        responses={200: MyAuctionHistorySerializer(many=True), 401: "please signin"},
        manual_parameters=[openapi.Parameter("Authorization", openapi.IN_HEADER, description="access token", type=openapi.TYPE_STRING)]
    )
    def get(self, request):
        user = request.user
        if not user.is_authenticated:
            return Response({"detail": "please signin"}, status=status.HTTP_401_UNAUTHORIZED)
        
        # 로그인한 사용자가 판매자인 경매들
        my_auctions = Auction.objects.filter(seller=user).order_by('-created_at')
        serializer = MyAuctionHistorySerializer(my_auctions, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class MyBidHistoryView(APIView):
    """내가 입찰한 경매 히스토리 API"""
    
    @swagger_auto_schema(
        operation_id="내가 입찰한 경매 히스토리",
        operation_description="로그인한 사용자가 입찰한 경매 목록을 조회합니다.",
        responses={200: MyBidHistorySerializer(many=True), 401: "please signin"},
        manual_parameters=[openapi.Parameter("Authorization", openapi.IN_HEADER, description="access token", type=openapi.TYPE_STRING)]
    )
    def get(self, request):
        user = request.user
        if not user.is_authenticated:
            return Response({"detail": "please signin"}, status=status.HTTP_401_UNAUTHORIZED)
        
        # 로그인한 사용자가 입찰한 경매들
        # Bid를 통해 사용자가 입찰한 경매의 ID를 가져옴
        auction_ids = Bid.objects.filter(bidder=user).values_list('auction_id', flat=True).distinct()
        my_bid_auctions = Auction.objects.filter(id__in=auction_ids).order_by('-updated_at')
        
        serializer = MyBidHistorySerializer(my_bid_auctions, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)