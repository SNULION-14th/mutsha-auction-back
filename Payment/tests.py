import json
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from UserProfile.models import UserProfile

from .models import Payment
from .views import (
    PaymentHistoryView,
    PayApproveView,
    PayReadyView,
    cid,
    payapprove_url,
    pay_header,
    payment_detail_url,
)


class PayReadyViewTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(username="payer", password="password")
        self.profile = UserProfile.objects.create(
            user=self.user,
            remaining_points=20,
        )

    @patch("Payment.views.requests.post")
    def test_ready_request_saves_payment(self, mock_post):
        kakao_response = Mock(status_code=200)
        kakao_response.json.return_value = {
            "tid": "T123",
            "next_redirect_pc_url": "https://example.com/pay",
        }
        mock_post.return_value = kakao_response
        request = self.factory.post(
            "/api/payment/ready/",
            {
                "partner_order_id": "order-1",
                "partner_user_id": "user-1",
                "item_name": "10",
                "quantity": 1,
                "total_amount": 10000,
                "tax_free_amount": 0,
                "approval_url": "http://localhost/payment/approve",
                "cancel_url": "http://localhost/payment/cancel",
                "fail_url": "http://localhost/payment/fail",
            },
            format="json",
        )
        force_authenticate(request, user=self.user)

        response = PayReadyView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        payment = Payment.objects.get(tid="T123")
        self.assertEqual(payment.point, 10)
        self.assertEqual(payment.price, 10000)
        self.assertEqual(payment.user, self.user)

    def test_ready_request_requires_authentication(self):
        request = self.factory.post("/api/payment/ready/", {}, format="json")

        response = PayReadyView.as_view()(request)

        self.assertEqual(response.status_code, 401)


class PayApproveViewTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(username="payer", password="password")
        self.profile = UserProfile.objects.create(
            user=self.user,
            remaining_points=20,
        )
        self.payment = Payment.objects.create(
            tid="T123",
            partner_order_id="order-1",
            partner_user_id="user-1",
            point=30,
            price=30000,
            user=self.user,
        )

    @patch("Payment.views.requests.post")
    def test_approve_updates_status_and_adds_points_once(self, mock_post):
        kakao_response = Mock(status_code=200)
        kakao_response.json.return_value = {
            "aid": "A123",
            "tid": self.payment.tid,
        }
        mock_post.return_value = kakao_response
        request = self.factory.post(
            "/api/payment/approve/",
            {"pg_token": "pg-token", "tid": self.payment.tid},
            format="json",
        )
        force_authenticate(request, user=self.user)

        response = PayApproveView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertEqual(self.payment.pay_status, "approved")
        self.assertEqual(self.profile.remaining_points, 50)
        self.assertEqual(
            response.data["point_info"],
            {"old_points": 20, "added_points": 30, "new_points": 50},
        )
        mock_post.assert_called_once_with(
            payapprove_url,
            headers=pay_header,
            data=json.dumps(
                {
                    "cid": cid,
                    "tid": self.payment.tid,
                    "partner_order_id": self.payment.partner_order_id,
                    "partner_user_id": self.payment.partner_user_id,
                    "pg_token": "pg-token",
                }
            ),
            timeout=10,
        )

    @patch("Payment.views.requests.post")
    def test_already_approved_payment_does_not_add_points_again(self, mock_post):
        self.payment.pay_status = "approved"
        self.payment.save(update_fields=["pay_status"])
        request = self.factory.post(
            "/api/payment/approve/",
            {"pg_token": "pg-token", "tid": self.payment.tid},
            format="json",
        )
        force_authenticate(request, user=self.user)

        response = PayApproveView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.remaining_points, 20)
        self.assertEqual(response.data["point_info"]["added_points"], 0)
        mock_post.assert_not_called()

    def test_approve_cannot_use_another_users_payment(self):
        other_user = User.objects.create_user(username="other", password="password")
        UserProfile.objects.create(user=other_user)
        request = self.factory.post(
            "/api/payment/approve/",
            {"pg_token": "pg-token", "tid": self.payment.tid},
            format="json",
        )
        force_authenticate(request, user=other_user)

        response = PayApproveView.as_view()(request)

        self.assertEqual(response.status_code, 404)

    def test_approve_requires_authentication(self):
        request = self.factory.post(
            "/api/payment/approve/",
            {"pg_token": "pg-token", "tid": self.payment.tid},
            format="json",
        )

        response = PayApproveView.as_view()(request)

        self.assertEqual(response.status_code, 401)


class PaymentHistoryViewTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(username="payer", password="password")
        UserProfile.objects.create(user=self.user)
        self.other_user = User.objects.create_user(
            username="other",
            password="password",
        )
        UserProfile.objects.create(user=self.other_user)

    @patch("Payment.views.requests.post")
    def test_history_only_queries_current_users_approved_payments(self, mock_post):
        own_approved = Payment.objects.create(
            tid="OWN-APPROVED",
            partner_order_id="order-1",
            partner_user_id="user-1",
            point=10,
            price=10000,
            pay_status="approved",
            user=self.user,
        )
        Payment.objects.create(
            tid="OWN-READY",
            partner_order_id="order-2",
            partner_user_id="user-1",
            point=30,
            price=30000,
            pay_status="ready",
            user=self.user,
        )
        Payment.objects.create(
            tid="OTHER-APPROVED",
            partner_order_id="order-3",
            partner_user_id="user-2",
            point=50,
            price=50000,
            pay_status="approved",
            user=self.other_user,
        )
        kakao_response = Mock(status_code=200)
        kakao_response.json.return_value = {
            "item_name": "10",
            "amount": {"total": 10000},
            "payment_method_type": "MONEY",
            "approved_at": "2026-09-25T12:00:00",
        }
        mock_post.return_value = kakao_response
        request = self.factory.get("/api/payment/history/")
        force_authenticate(request, user=self.user)

        response = PaymentHistoryView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["payments"]), 1)
        self.assertEqual(response.data["payments"][0]["tid"], own_approved.tid)
        self.assertEqual(response.data["payments"][0]["amount"]["total"], 10000)
        self.assertEqual(response.data["failed_count"], 0)
        mock_post.assert_called_once_with(
            payment_detail_url,
            headers=pay_header,
            data=json.dumps({"cid": cid, "tid": own_approved.tid}),
            timeout=10,
        )

    @patch("Payment.views.requests.post")
    def test_history_keeps_successful_items_when_one_lookup_fails(self, mock_post):
        Payment.objects.create(
            tid="SUCCESS",
            partner_order_id="order-1",
            partner_user_id="user-1",
            point=10,
            price=10000,
            pay_status="approved",
            user=self.user,
        )
        Payment.objects.create(
            tid="FAILURE",
            partner_order_id="order-2",
            partner_user_id="user-1",
            point=30,
            price=30000,
            pay_status="approved",
            user=self.user,
        )
        failed_response = Mock(status_code=500)
        success_response = Mock(status_code=200)
        success_response.json.return_value = {
            "item_name": "10",
            "amount": {"total": 10000},
            "payment_method_type": "CARD",
            "approved_at": "2026-09-25T12:00:00",
        }
        mock_post.side_effect = [failed_response, success_response]
        request = self.factory.get("/api/payment/history/")
        force_authenticate(request, user=self.user)

        response = PaymentHistoryView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["payments"]), 1)
        self.assertEqual(response.data["payments"][0]["tid"], "SUCCESS")
        self.assertEqual(response.data["failed_count"], 1)

    def test_history_requires_authentication(self):
        request = self.factory.get("/api/payment/history/")

        response = PaymentHistoryView.as_view()(request)

        self.assertEqual(response.status_code, 401)
