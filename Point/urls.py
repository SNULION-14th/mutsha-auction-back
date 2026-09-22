from django.urls import path
# from .views import ReadAllPostView, CreatePostView
from .views import PointListView

app_name = 'point'
urlpatterns = [
    # FBV url path
    # path("register_post/", CreatePostView),
    # path("see_post/", ReadAllPostView),

    # CBV url path
    path("", PointListView.as_view()),
]
