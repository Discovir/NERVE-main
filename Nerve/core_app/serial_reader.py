"""
serial_reader.py
----------------
A singleton background thread that:
  1. Opens the serial port connected to the ESP32.
  2. Reads lines of sensor values (one EMG sample per line).
  3. Broadcasts each sample to the "emg_stream" Channels group.

Includes a Simulator fallback if no hardware is detected.
"""

import threading
import json
import time
import logging
import random
import math

# Try to import serial, but don't crash if missing (allows testing UI without pyserial)
try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False

logger = logging.getLogger(__name__)

_reader_thread: threading.Thread | None = None
_stop_event = threading.Event()

def _read_loop(port: str, baud: int) -> None:
    """Inner loop — handles hardware serial or simulation fallback."""
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    channel_layer = get_channel_layer()
    broadcast = async_to_sync(channel_layer.group_send)
    
    is_simulation = (port == "SIM") or (not HAS_SERIAL)

    # Always use the hardcoded port, ignore "AUTO" logic to prevent trying ttyS31
    if port == "AUTO":
        port = "/dev/ttyACM0"
    
    is_simulation = port == "SIM"


    print(f"DEBUG: Starting thread in {'SIMULATION' if is_simulation else 'HARDWARE'} mode on {port}")

    while not _stop_event.is_set():
        if is_simulation:
            # --- SIMULATION MODE ---
            # Generate a 50Hz sine wave + noise + random "bursts" (EMG-like)
            t_base = time.time()
            while not _stop_event.is_set():
                elapsed = time.time() - t_base
                # Base signal (noise)
                val = 2048 + random.uniform(-20, 20)
                # Add a 50Hz hum
                val += math.sin(elapsed * 2 * math.pi * 50) * 10
                # Random "Muscle Contraction" burst
                if int(elapsed * 2) % 5 == 0:
                    val += random.uniform(-400, 400)
                
                payload = {
                    "type": "emg.sample",
                    "data": {
                        "t": int(time.time() * 1000),
                        "channels": [max(0, min(4095, val))],
                        "is_sim": True
                    },
                }
                broadcast("emg_stream", payload)
                time.sleep(0.01) # 100Hz simulation for smoothness
        else:
            # --- HARDWARE MODE ---
            try:
                print(f"DEBUG: Attempting to open {port}...")
                with serial.Serial(port, baud, timeout=1) as ser:
                    ser.reset_input_buffer()
                    print(f"DEBUG: Successfully opened {port}. Reading data...")
                    
                    while not _stop_event.is_set():
                        raw = ser.readline()
                        if not raw: continue
                        
                        line = raw.decode("utf-8", errors="ignore").strip()
                        if not line: continue

                        try:
                            # Handle single value (ESP32 Serial.println)
                            parts = line.split(",")
                            if len(parts) >= 1:
                                val = float(parts[0])
                                channels = [val]
                                timestamp = int(time.time() * 1000)
                                
                                payload = {
                                    "type": "emg.sample",
                                    "data": {
                                        "t": timestamp,
                                        "channels": channels,
                                        "is_sim": False
                                    },
                                }
                                broadcast("emg_stream", payload)
                        except ValueError:
                            continue
            except Exception as exc:
                print(f"DEBUG: Serial Error: {exc}. Retrying in 2s...")
                time.sleep(2)

def start(port: str = "AUTO", baud: int = 115200) -> None:
    global _reader_thread, _stop_event

    # Stop existing thread if running
    if _reader_thread and _reader_thread.is_alive():
        stop()
        time.sleep(0.1)

    _stop_event.clear()
    _reader_thread = threading.Thread(
        target=_read_loop,
        args=(port, baud),
        daemon=True,
        name="EMGSerialReader",
    )
    _reader_thread.start()

def stop() -> None:
    _stop_event.set()