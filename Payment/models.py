from django.db import models

# Create your models here.
from django.contrib.auth.models import User

# Create your models here.
class Payment(models.Model):
    tid=models.CharField(max_length=100)
    partner_order_id=models.CharField(max_length=100)
    partner_user_id=models.CharField(max_length=100)
    point=models.IntegerField(default=0)
    price=models.IntegerField(default=0)
    pay_status=models.CharField(max_length=100, default='ready')
    user=models.ForeignKey(User, on_delete=models.CASCADE, related_name='pay_buyer', null=True)