from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):
    dependencies = [
        ("Payment", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, default=timezone.now),
            preserve_default=False,
        ),
    ]
