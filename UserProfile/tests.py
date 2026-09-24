from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from .models import UserProfile
from .views import KakaoSignInCallbackView


class KakaoSignInCallbackViewTests(TestCase):
    @patch("UserProfile.views.requests.get")
    @patch("UserProfile.views.requests.post")
    def test_callback_creates_social_user_and_sets_tokens(
        self,
        mock_post,
        mock_get,
    ):
        token_response = Mock()
        token_response.json.return_value = {"access_token": "kakao-access-token"}
        mock_post.return_value = token_response
        user_response = Mock()
        user_response.json.return_value = {"id": 123456789}
        mock_get.return_value = user_response
        request = APIRequestFactory().get(
            "/api/user/kakao/callback/",
            {"code": "authorization-code"},
        )

        response = KakaoSignInCallbackView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        user = User.objects.get(username="123456789")
        self.assertTrue(
            UserProfile.objects.get(user=user).is_social_login,
        )
        self.assertIn("access_token", response.cookies)
        self.assertIn("refresh_token", response.cookies)
