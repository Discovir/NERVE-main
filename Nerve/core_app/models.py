from django.db import models


class Subject(models.Model):
    """Registered EMG user whose biometric data has been enrolled."""
    subject_id  = models.CharField(max_length=100, unique=True)
    full_name   = models.CharField(max_length=200, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.subject_id} ({self.full_name})"


class EMGSession(models.Model):
    """One recorded collection session (can span multiple reps / gestures)."""

    SESSION_TYPE_CHOICES = [
        ("enroll", "Enroll"),
        ("verify", "Verify"),
    ]

    subject      = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="sessions")
    session_type = models.CharField(max_length=10, choices=SESSION_TYPE_CHOICES)
    gesture      = models.CharField(max_length=100, default="fist_clench")
    reps_target  = models.IntegerField(default=10)
    sec_per_rep  = models.IntegerField(default=3)
    started_at   = models.DateTimeField(auto_now_add=True)
    ended_at     = models.DateTimeField(null=True, blank=True)
    notes        = models.TextField(blank=True)

    def __str__(self):
        return f"[{self.session_type}] {self.subject.subject_id} @ {self.started_at:%Y-%m-%d %H:%M}"


class EMGSample(models.Model):
    """A single 12-bit ADC reading captured from the ESP32."""
    session     = models.ForeignKey(EMGSession, on_delete=models.CASCADE, related_name="samples")
    timestamp   = models.BigIntegerField()       # unix ms from ESP32 arrival
    raw_value   = models.FloatField()            # 0-4095 from analogRead
    rep_number  = models.IntegerField(default=1)
    phase       = models.CharField(max_length=20, default="clench")  # clench | rest | ready | idle

    class Meta:
        ordering = ["timestamp"]
