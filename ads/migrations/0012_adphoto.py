from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('ads', '0011_alter_ad_category'),
    ]

    operations = [
        migrations.CreateModel(
            name='AdPhoto',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image', models.ImageField(upload_to='ads/')),
                ('thumbnail', models.ImageField(blank=True, null=True, upload_to='ads/thumbnails/')),
                ('is_cover', models.BooleanField(default=False)),
                ('sort_order', models.PositiveSmallIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('ad', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='photos', to='ads.ad')),
            ],
            options={
                'ordering': ['sort_order', 'id'],
            },
        ),
    ]
