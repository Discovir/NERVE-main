from django.apps import AppConfig


class SerialAppConfig(AppConfig):
    name = "core_app"
    verbose_name = "EMG Serial App"

    def ready(self):
        """
        Auto-start the serial reader when the Django process is ready.
        Guarded by RUN_MAIN to avoid double-start with the dev reloader.
        """
        import os
        from django.conf import settings
        from core_app import serial_reader

        # DEPRECATED: WebSerial is now used for direct browser-to-hardware communication.
        # This prevents the backend from locking the serial port.
        pass
