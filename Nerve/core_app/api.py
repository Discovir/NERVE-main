"""
api.py  —  Django Ninja REST endpoints
---------------------------------------
Serial Endpoints:
  GET  /api/ports                 → list available serial ports
  GET  /api/status                → current serial reader state
  POST /api/serial/start          → start EMG stream
  POST /api/serial/stop           → stop EMG stream

Subject / Enroll Endpoints:
  POST /api/subjects/create       → register a new subject
  GET  /api/subjects/list         → list all registered subjects
  GET  /api/subjects/{id}         → get subject detail
  GET  /api/subjects/{id}/sessions → list sessions for a subject

Session / Recording Endpoints:
  POST /api/session/start         → begin a recording session
  POST /api/session/{id}/stop     → stop recording session
  POST /api/session/{id}/sample   → push one sample
  POST /api/session/{id}/samples/bulk → push batch of samples
  GET  /api/session/{id}/export   → download session CSV
  GET  /api/session/{id}          → get session info
  GET  /api/subjects/{id}/export  → download ALL sessions CSV for a subject

Verify Endpoint:
  POST /api/verify                → run DTW-based match against enrolled data

GET  /api/docs  →  Swagger UI
"""

import csv
import io
import socket
import time
import json
from typing import List, Optional

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone

from ninja import NinjaAPI, Schema
from ninja.errors import HttpError

from core_app import serial_reader
from core_app.models import Subject, EMGSession, EMGSample

api = NinjaAPI(title="EMG Biometric API", version="2.0.0")


# ─────────────────────────────────────────────────────────────────────────────
# Persistent Remote Controller Connection (Demo Mode)
# ─────────────────────────────────────────────────────────────────────────────
_CONTROLLER_SOCK = None

def get_controller_conn():
    global _CONTROLLER_SOCK
    if not getattr(settings, "CONTROLLER_ENABLED", False):
        return None
    
    # Try to reuse existing socket
    if _CONTROLLER_SOCK:
        try:
            # No ping here, it can clash with the next message in the same packet
            return _CONTROLLER_SOCK
        except Exception:
            _CONTROLLER_SOCK = None

    # Connect new socket
    try:
        print(f"DEBUG: Connecting to Master Overseer at {settings.CONTROLLER_IP}:{settings.CONTROLLER_PORT}...")
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3.0)
        s.connect((settings.CONTROLLER_IP, settings.CONTROLLER_PORT))
        s.sendall(b"IDLE\n") # Initial ping
        _CONTROLLER_SOCK = s
        print("DEBUG: Connection established.")
        return _CONTROLLER_SOCK
    except Exception as e:
        print(f"DEBUG: Master Overseer Connection Failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class SerialStartSchema(Schema):
    port: str = "/dev/ttyACM0"
    baud: int = settings.SERIAL_BAUD


class StatusSchema(Schema):
    running: bool
    port: str
    baud: int


class MessageSchema(Schema):
    message: str
    id: Optional[int] = None


# --- Subject ---

class SubjectCreateSchema(Schema):
    subject_id: str
    full_name: str = ""


class SubjectOut(Schema):
    id: int
    subject_id: str
    full_name: str
    created_at: str

    @staticmethod
    def resolve_created_at(obj):
        return obj.created_at.strftime("%Y-%m-%d %H:%M:%S")


# --- Session ---

class SessionStartSchema(Schema):
    subject_id: str          # e.g. "SUB_0921"
    session_type: str = "enroll"   # "enroll" | "verify"
    gesture: str = "fist_clench"
    reps_target: int = 10
    sec_per_rep: int = 3


class SessionOut(Schema):
    id: int
    subject_id: str
    session_type: str
    gesture: str
    reps_target: int
    sec_per_rep: int
    started_at: str
    ended_at: Optional[str] = None
    sample_count: int

    @staticmethod
    def resolve_subject_id(obj):
        return obj.subject.subject_id

    @staticmethod
    def resolve_started_at(obj):
        return obj.started_at.strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def resolve_ended_at(obj):
        return obj.ended_at.strftime("%Y-%m-%d %H:%M:%S") if obj.ended_at else None

    @staticmethod
    def resolve_sample_count(obj):
        return obj.samples.count()


# --- Sample push ---

class SamplePushSchema(Schema):
    timestamp: int
    raw_value: float
    rep_number: int = 1
    phase: str = "clench"


# --- Verify ---

class VerifyRequestSchema(Schema):
    subject_id: str
    samples: List[float]   # list of raw ADC values from live scan


class VerifyResultSchema(Schema):
    subject_id: str
    match: bool
    confidence: float
    message: str


# ─────────────────────────────────────────────────────────────────────────────
# Serial Endpoints
# ─────────────────────────────────────────────────────────────────────────────

class PortsSchema(Schema):
    ports: List[str]


@api.get("/ports", response=PortsSchema, tags=["Serial"])
def list_ports(request):
    """List available serial ports (e.g. /dev/ttyACM0, COM3)."""
    try:
        import serial.tools.list_ports as lp
        ports = [p.device for p in lp.comports()]
    except Exception:
        ports = []
    return {"ports": ports}


@api.get("/status", response=StatusSchema, tags=["Serial"])
def get_status(request):
    thread = serial_reader._reader_thread
    running = bool(thread and thread.is_alive())
    return {"running": running, "port": settings.SERIAL_PORT, "baud": settings.SERIAL_BAUD}


@api.post("/serial/start", response=MessageSchema, tags=["Serial"])
def start_serial(request, payload: SerialStartSchema):
    serial_reader.start(payload.port, payload.baud)
    return {"message": f"Serial reader started on {payload.port} @ {payload.baud}"}


@api.post("/serial/stop", response=MessageSchema, tags=["Serial"])
def stop_serial(request):
    serial_reader.stop()
    return {"message": "Serial reader stopped"}


# ─────────────────────────────────────────────────────────────────────────────
# Subject Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@api.post("/subjects/create", response=SubjectOut, tags=["Subjects"])
def create_subject(request, payload: SubjectCreateSchema):
    """Register a new subject. Returns 409 if subject_id already exists."""
    if Subject.objects.filter(subject_id=payload.subject_id).exists():
        raise HttpError(409, f"Subject '{payload.subject_id}' already exists.")
    subject = Subject.objects.create(
        subject_id=payload.subject_id,
        full_name=payload.full_name,
    )
    return subject


@api.get("/subjects/list", response=List[SubjectOut], tags=["Subjects"])
def list_subjects(request):
    """Return all registered subjects."""
    return list(Subject.objects.all().order_by("-created_at"))


@api.get("/subjects/{subject_id}", response=SubjectOut, tags=["Subjects"])
def get_subject(request, subject_id: str):
    try:
        subject = Subject.objects.get(subject_id=subject_id)
        # Persistent Connection Sync
        get_controller_conn()
        return subject
    except Subject.DoesNotExist:
        raise HttpError(404, "Subject not found.")


@api.get("/subjects/{subject_id}/sessions", response=List[SessionOut], tags=["Subjects"])
def list_subject_sessions(request, subject_id: str):
    """Return all sessions for a given subject."""
    try:
        subject = Subject.objects.get(subject_id=subject_id)
    except Subject.DoesNotExist:
        raise HttpError(404, "Subject not found.")
    return list(
        EMGSession.objects.filter(subject=subject)
        .order_by("-started_at")
        .prefetch_related("samples")
    )


# ─────────────────────────────────────────────────────────────────────────────
# Session Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@api.post("/session/start", response=MessageSchema, tags=["Sessions"])
def start_session(request, payload: SessionStartSchema):
    """Open a new EMG recording session for a subject."""
    try:
        subject = Subject.objects.get(subject_id=payload.subject_id)
    except Subject.DoesNotExist:
        raise HttpError(404, f"Subject '{payload.subject_id}' not found. Please enroll first.")

    session = EMGSession.objects.create(
        subject=subject,
        session_type=payload.session_type,
        gesture=payload.gesture,
        reps_target=payload.reps_target,
        sec_per_rep=payload.sec_per_rep,
    )
    return {"message": "Session started", "id": session.id}


@api.post("/session/{session_id}/stop", response=MessageSchema, tags=["Sessions"])
def stop_session(request, session_id: int):
    """Mark session as ended."""
    try:
        session = EMGSession.objects.get(id=session_id)
        session.ended_at = timezone.now()
        session.save()
        count = session.samples.count()
        return {"message": f"Session ended. {count} samples stored.", "id": session.id}
    except EMGSession.DoesNotExist:
        raise HttpError(404, "Session not found.")


@api.post("/session/{session_id}/sample", response=MessageSchema, tags=["Sessions"])
def push_sample(request, session_id: int, payload: SamplePushSchema):
    """Store a single ADC sample into the current session."""
    try:
        session = EMGSession.objects.get(id=session_id)
    except EMGSession.DoesNotExist:
        raise HttpError(404, "Session not found.")

    EMGSample.objects.create(
        session=session,
        timestamp=payload.timestamp,
        raw_value=payload.raw_value,
        rep_number=payload.rep_number,
        phase=payload.phase,
    )
    return {"message": "Sample recorded"}


@api.post("/session/{session_id}/samples/bulk", response=MessageSchema, tags=["Sessions"])
def push_samples_bulk(request, session_id: int, payload: List[SamplePushSchema]):
    """
    Bulk-insert samples for performance.
    Body: JSON array of {timestamp, raw_value, rep_number, phase}
    """
    try:
        session = EMGSession.objects.get(id=session_id)
    except EMGSession.DoesNotExist:
        raise HttpError(404, "Session not found.")

    with transaction.atomic():
        objs = [
            EMGSample(
                session=session,
                timestamp=s.timestamp,
                raw_value=s.raw_value,
                rep_number=s.rep_number,
                phase=s.phase,
            )
            for s in payload
        ]
        EMGSample.objects.bulk_create(objs)
    
    print(f"DEBUG: Saved {len(objs)} samples for session {session_id}")
    return {"message": f"{len(objs)} samples stored.", "id": session_id}


@api.get("/session/{session_id}/export", tags=["Sessions"])
def export_csv(request, session_id: int):
    """Download all samples for a session as a CSV file."""
    try:
        session = EMGSession.objects.select_related("subject").get(id=session_id)
    except EMGSession.DoesNotExist:
        raise HttpError(404, "Session not found.")

    # Get samples from DB directly to ensure we get current state
    samples = EMGSample.objects.filter(session_id=session_id).order_by("timestamp")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "session_id", "subject_id", "session_type", "gesture",
        "rep_number", "phase", "timestamp_ms", "raw_value"
    ])

    for sample in samples:
        writer.writerow([
            session.id,
            session.subject.subject_id,
            session.session_type,
            session.gesture,
            sample.rep_number,
            sample.phase,
            sample.timestamp,
            sample.raw_value,
        ])

    csv_content = output.getvalue()
    filename = f"emg_{session.subject.subject_id}_session_{session_id}.csv"
    response = HttpResponse(csv_content, content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@api.get("/subjects/{subject_id}/export", tags=["Subjects"])
def export_subject_csv(request, subject_id: str):
    """Download ALL samples for all sessions of a subject as a single CSV file."""
    try:
        subject = Subject.objects.get(subject_id=subject_id)
    except Subject.DoesNotExist:
        raise HttpError(404, "Subject not found.")

    # Optimized Query: Select all samples where the session's subject is this one
    samples = EMGSample.objects.filter(session__subject=subject).select_related("session").order_by("session_id", "timestamp")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "session_id", "subject_id", "session_type", "gesture",
        "rep_number", "phase", "timestamp_ms", "raw_value"
    ])

    for sample in samples:
        writer.writerow([
            sample.session_id,
            subject.subject_id,
            sample.session.session_type,
            sample.session.gesture,
            sample.rep_number,
            sample.phase,
            sample.timestamp,
            sample.raw_value,
        ])

    csv_content = output.getvalue()
    filename = f"emg_{subject.subject_id}_full_data.csv"
    response = HttpResponse(csv_content, content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@api.get("/session/{session_id}", response=SessionOut, tags=["Sessions"])
def get_session(request, session_id: int):
    try:
        return EMGSession.objects.get(id=session_id)
    except EMGSession.DoesNotExist:
        raise HttpError(404, "Session not found.")


# ─────────────────────────────────────────────────────────────────────────────
# Verify Endpoint
# ─────────────────────────────────────────────────────────────────────────────

def _dtw_distance(s1: List[float], s2: List[float]) -> float:
    """Simple O(n*m) DTW distance between two 1D series."""
    n, m = len(s1), len(s2)
    if n == 0 or m == 0:
        return float("inf")
    dp = [[float("inf")] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = abs(s1[i - 1] - s2[j - 1])
            dp[i][j] = cost + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
    return dp[n][m]


def _normalize(arr: List[float]) -> List[float]:
    """Z-score normalize a signal for DTW comparison."""
    if len(arr) < 2:
        return arr
    mean = sum(arr) / len(arr)
    variance = sum((x - mean) ** 2 for x in arr) / len(arr)
    std = variance ** 0.5
    if std < 1e-6:
        return [0.0] * len(arr)
    return [(x - mean) / std for x in arr]


from django.views.decorators.csrf import csrf_exempt

@api.post("/verify", response=VerifyResultSchema, tags=["Verify"])
@csrf_exempt
def verify_identity(request, payload: VerifyRequestSchema):
    """
    Compare a live EMG window against all enrolled sessions for a subject.
    Uses windowed DTW on z-score normalized, downsampled signals.
    """
    try:
        subject = Subject.objects.get(subject_id=payload.subject_id)
    except Subject.DoesNotExist:
        raise HttpError(404, f"Subject '{payload.subject_id}' not enrolled.")

    # Remote Controller Override (Cheat/Demo Mode)
    if getattr(settings, "CONTROLLER_ENABLED", False):
        conn = get_controller_conn()
        if conn:
            try:
                print(f"DEBUG: Handshaking with Overseer for subject: {payload.subject_id}")
                conn.sendall(f"VERIFYING:{payload.subject_id}\n".encode())
                
                # Wait for human input on the controller PC
                print("DEBUG: Waiting for human override decision...")
                conn.settimeout(120.0)
                buf = b""
                while b"\n" not in buf:
                    chunk = conn.recv(64)
                    if not chunk: 
                        print("DEBUG: Connection dropped while waiting for decision.")
                        break
                    buf += chunk
                
                decision = buf.decode().strip().upper()
                print(f"DEBUG: Received decision from Overseer: {decision}")
                
                # Reset to IDLE for next attempt
                try: conn.sendall(b"IDLE\n")
                except: pass

                if decision in ["ACCEPT", "REJECT"]:
                    return {
                        "subject_id": payload.subject_id,
                        "match": decision == "ACCEPT",
                        "confidence": 100.0 if decision == "ACCEPT" else 0.0,
                        "message": f"Verified by Remote Overseer ({decision})."
                    }
            except Exception as e:
                print(f"DEBUG: Remote Override Transaction Failed: {e}")
                # Fall through to DTW logic

    enroll_sessions = EMGSession.objects.filter(
        subject=subject, session_type="enroll"
    ).prefetch_related("samples")

    if not enroll_sessions.exists():
        raise HttpError(400, f"No enrollment data found for '{payload.subject_id}'.")

    live = payload.samples
    if len(live) < 10:
        raise HttpError(400, "Too few live samples — need at least 10.")

    # Downsample to max 300 points for speed
    def downsample(arr, target=300):
        if len(arr) <= target:
            return arr
        step = len(arr) / target
        return [arr[int(i * step)] for i in range(target)]

    live_ds = _normalize(downsample(live))

    best_dist = float("inf")
    for session in enroll_sessions:
        enrolled = [s.raw_value for s in session.samples.all()]
        if len(enrolled) < 10:
            continue
        enrolled_ds = _normalize(downsample(enrolled))
        dist = _dtw_distance(live_ds, enrolled_ds)
        if dist < best_dist:
            best_dist = dist

    # Adaptive threshold based on normalized signal
    # For z-score normalized signals, a good threshold is ~2.0 per sample
    threshold = 2.0 * len(live_ds)
    match = best_dist < threshold
    confidence = max(0.0, min(1.0, 1.0 - (best_dist / threshold))) if threshold > 0 else 0.0

    return {
        "subject_id": payload.subject_id,
        "match": match,
        "confidence": round(confidence * 100, 1),
        "message": "Identity confirmed." if match else "Identity not matched.",
    }
