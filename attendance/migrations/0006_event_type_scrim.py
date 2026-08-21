# Generated manually for BangCheck event type / scrim update

from django.db import migrations, models


def set_existing_events_to_war(apps, schema_editor):
    WarEvent = apps.get_model('attendance', 'WarEvent')
    WarEvent.objects.filter(event_type='').update(event_type='war')


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0005_feedback'),
    ]

    operations = [
        migrations.AddField(
            model_name='warevent',
            name='event_type',
            field=models.CharField(
                choices=[('war', 'Bang chiến'), ('scrim', 'Scrim')],
                default='war',
                max_length=20,
                verbose_name='Loại sự kiện',
            ),
        ),
        migrations.RunPython(set_existing_events_to_war, migrations.RunPython.noop),
        migrations.AddIndex(
            model_name='warevent',
            index=models.Index(fields=['event_type', 'is_current'], name='attendance_w_event__e5b58b_idx'),
        ),
        migrations.AddIndex(
            model_name='warevent',
            index=models.Index(fields=['event_type', 'status'], name='attendance_w_event__60b7a3_idx'),
        ),
    ]
