"""
Management command: python manage.py run_serial_reader

Useful during development — run this in a separate terminal so the
serial reader stays active without relying on AppConfig.ready().
"""

import signal
import time
from django.core.management.base import BaseCommand
from django.conf import settings
from core_app import serial_reader


class Command(BaseCommand):
    help = "Start the ESP32 serial reader and stream data to connected WebSocket clients"

    def add_arguments(self, parser):
        parser.add_argument(
            "--port",
            default=settings.SERIAL_PORT,
            help="Serial port (default: %(default)s)",
        )
        parser.add_argument(
            "--baud",
            type=int,
            default=settings.SERIAL_BAUD,
            help="Baud rate (default: %(default)s)",
        )

    def handle(self, *args, **options):
        port = "/dev/ttyACM0"
        baud = options["baud"]

        self.stdout.write(self.style.SUCCESS(f"Starting serial reader on {port} @ {baud}"))
        serial_reader.start(port, baud)

        # Block until Ctrl+C
        def _shutdown(sig, frame):
            self.stdout.write("\nStopping serial reader...")
            serial_reader.stop()

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

        while serial_reader._reader_thread and serial_reader._reader_thread.is_alive():
            time.sleep(0.5)

        self.stdout.write(self.style.SUCCESS("Serial reader stopped."))
