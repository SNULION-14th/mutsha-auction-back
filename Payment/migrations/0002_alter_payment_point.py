from django.db import migrations, models


class Migration(migrations.Migration):
    """Historical migration already applied to the supplied SQLite database."""

    dependencies = [("Payment", "0001_initial")]
    operations = [
        migrations.AlterField(
            model_name="payment",
            name="point",
            field=models.IntegerField(default=0),
        ),
    ]
