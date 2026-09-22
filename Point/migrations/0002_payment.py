# Generated manually for the KakaoPay practice payment record.
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("Point", "0001_initial"),
        migrations.swappable_dependency("auth.User"),
    ]

    operations = [
        migrations.CreateModel(
            name="Payment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("partner_order_id", models.CharField(max_length=64, unique=True)),
                ("tid", models.CharField(blank=True, max_length=128)),
                ("item_name", models.CharField(max_length=256)),
                ("quantity", models.PositiveIntegerField()),
                ("total_amount", models.PositiveIntegerField()),
                ("status", models.CharField(choices=[("READY", "결제 대기"), ("APPROVED", "결제 승인"), ("FAILED", "결제 실패")], default="READY", max_length=16)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="payments", to="auth.user")),
            ],
        ),
    ]
