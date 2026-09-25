from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):
    """Bring the historical payment table to the current API model schema."""

    dependencies = [("Payment", "0002_alter_payment_point")]
    operations = [
        migrations.RenameField(model_name="payment", old_name="price", new_name="total_amount"),
        migrations.RenameField(model_name="payment", old_name="pay_status", new_name="status"),
        migrations.RemoveField(model_name="payment", name="partner_user_id"),
        migrations.RemoveField(model_name="payment", name="point"),
        migrations.AddField(
            model_name="payment",
            name="quantity",
            field=models.PositiveIntegerField(default=0),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="payment",
            name="item_name",
            field=models.CharField(default="기존 결제", max_length=100),
            preserve_default=False,
        ),
        migrations.AddField(model_name="payment", name="approved_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="payment", name="created_at", field=models.DateTimeField(default=timezone.now, auto_now_add=True), preserve_default=False),
        migrations.AddField(model_name="payment", name="updated_at", field=models.DateTimeField(default=timezone.now, auto_now=True), preserve_default=False),
        migrations.AlterField(
            model_name="payment",
            name="status",
            field=models.CharField(choices=[("ready", "Ready"), ("approved", "Approved"), ("failed", "Failed"), ("cancelled", "Cancelled")], default="ready", max_length=20),
        ),
    ]
