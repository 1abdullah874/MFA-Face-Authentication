"""
Multi-Factor Authentication System
===================================
Requires: pip install face_recognition PyQt5 opencv-python bcrypt
100% offline — no API key or internet needed.

⚠️  EDUCATIONAL / DEMO PROJECT
    Not recommended for production use without additional security hardening.

    Marked severities with Claude AI
"""

import sys
import os
import cv2
import json
import bcrypt
import re
import threading
import numpy as np
from datetime import datetime
from pathlib import Path

import face_recognition

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QStackedWidget, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QSizePolicy, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QImage, QPixmap, QFont, QColor

# ── Storage ───────────────────────────────────────────────────────────────────
DATA_DIR   = Path.home() / ".mfa_app"
USERS_FILE = DATA_DIR / "users.json"
LOG_FILE   = DATA_DIR / "log.json"
DATA_DIR.mkdir(exist_ok=True)

# [HIGH SEVERITY SECTION REDACTED]
# Additional storage hardening (file permissions, encryption) removed.
# See security notes in README before deploying.

def load_users():
    if USERS_FILE.exists():
        with open(USERS_FILE) as f:
            return json.load(f)
    return {}

def save_users(users):
    tmp = USERS_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(users, f)
    tmp.replace(USERS_FILE)

def load_log():
    if LOG_FILE.exists():
        with open(LOG_FILE) as f:
            return json.load(f)
    return []

def save_log(log):
    tmp = LOG_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(log, f)
    tmp.replace(LOG_FILE)

def append_log(username, status, reason=""):
    log = load_log()
    log.insert(0, {
        "username": username,
        "status":   status,
        "reason":   reason,
        "time":     datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    log = log[:200]  # keep last 200
    save_log(log)

# ── Signals ───────────────────────────────────────────────────────────────────
class Signals(QObject):
    frame_ready    = pyqtSignal(QPixmap)
    face_enrolled  = pyqtSignal(list)       # encoding list
    face_matched   = pyqtSignal(bool)
    status_update  = pyqtSignal(str, str)   # text, color

# ── Camera Worker ─────────────────────────────────────────────────────────────
class CameraWorker:
    def __init__(self, signals: Signals):
        self.signals   = signals
        self.cap       = None
        self.running   = False
        self.mode      = "preview"   # "preview" | "enroll" | "verify"
        self.target_encoding = None
        self._thread   = None
        self._lock     = threading.Lock()

    def start(self, mode="preview", target_encoding=None):
        self.mode = mode
        self.target_encoding = target_encoding
        if self.cap is None or not self.cap.isOpened():
            self.cap = cv2.VideoCapture(0)
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        if self.cap:
            self.cap.release()
            self.cap = None

    def _loop(self):
        while self.running:
            if not self.cap or not self.cap.isOpened():
                break
            ret, frame = self.cap.read()
            if not ret:
                continue

            frame = cv2.flip(frame, 1)
            rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Detect face locations for overlay
            small  = cv2.resize(rgb, (0, 0), fx=0.5, fy=0.5)
            locs   = face_recognition.face_locations(small)
            locs   = [(t*2, r*2, b*2, l*2) for t,r,b,l in locs]

            color = (80, 200, 120)   # green default

            if self.mode == "enroll" and locs:
                encs = face_recognition.face_encodings(rgb, locs)
                if encs:
                    self.running = False
                    self.signals.face_enrolled.emit(encs[0].tolist())
                    color = (52, 211, 153)

            elif self.mode == "verify" and self.target_encoding is not None and locs:
                encs = face_recognition.face_encodings(rgb, locs)
                if encs:
                    target = np.array(self.target_encoding)
                    # Tolerance set to 0.4 (stricter than default 0.5)
                    match  = face_recognition.compare_faces([target], encs[0], tolerance=0.4)[0]
                    if match:
                        self.running = False
                        self.signals.face_matched.emit(True)
                        color = (52, 211, 153)
                    else:
                        color = (248, 113, 113)
                        self.signals.face_matched.emit(False)

            # Draw bounding boxes
            display = frame.copy()
            for (top, right, bottom, left) in locs:
                cv2.rectangle(display, (left, top), (right, bottom), color, 2)
                # Corner accents
                l = 18
                cv2.line(display, (left, top),    (left+l, top),    color, 3)
                cv2.line(display, (left, top),    (left, top+l),    color, 3)
                cv2.line(display, (right, top),   (right-l, top),   color, 3)
                cv2.line(display, (right, top),   (right, top+l),   color, 3)
                cv2.line(display, (left, bottom), (left+l, bottom), color, 3)
                cv2.line(display, (left, bottom), (left, bottom-l), color, 3)
                cv2.line(display, (right,bottom), (right-l,bottom), color, 3)
                cv2.line(display, (right,bottom), (right, bottom-l),color, 3)

            rgb2 = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb2.shape
            qimg = QImage(rgb2.data, w, h, ch*w, QImage.Format_RGB888)
            pix  = QPixmap.fromImage(qimg)
            self.signals.frame_ready.emit(pix)

# ── Shared style helpers ───────────────────────────────────────────────────────
STYLE = """
    QMainWindow, QWidget { background: #080810; }
    QLabel { color: #e8e4ff; background: transparent; }
    QLineEdit {
        background: #13131f; color: #e8e4ff;
        border: 1px solid #2a2a40; border-radius: 8px;
        padding: 10px 14px; font-size: 13px;
    }
    QLineEdit:focus { border-color: #6c63ff; }
    QPushButton {
        border-radius: 8px; padding: 11px 24px;
        font-size: 13px; font-weight: bold; border: none;
    }
    QTableWidget {
        background: #0d0d1a; color: #e8e4ff;
        border: 1px solid #1a1a2e; border-radius: 8px;
        gridline-color: #1a1a2e; font-size: 12px;
    }
    QTableWidget::item { padding: 6px 10px; }
    QHeaderView::section {
        background: #13131f; color: #7c78a8;
        border: none; border-bottom: 1px solid #1a1a2e;
        padding: 6px 10px; font-family: 'Courier New'; font-size: 11px;
    }
    QScrollBar:vertical { background: #0d0d1a; width: 6px; }
    QScrollBar::handle:vertical { background: #2a2a40; border-radius: 3px; }
"""

def btn_primary(text, color="#6c63ff", hover="#5a52e0"):
    b = QPushButton(text)
    b.setStyleSheet(f"""
        QPushButton {{ background:{color}; color:white; }}
        QPushButton:hover {{ background:{hover}; }}
        QPushButton:disabled {{ background:#1a1a2e; color:#3a3a5c; }}
    """)
    return b

def btn_secondary(text):
    b = QPushButton(text)
    b.setStyleSheet("""
        QPushButton { background:#13131f; color:#7c78a8;
                      border:1px solid #2a2a40; }
        QPushButton:hover { color:#e8e4ff; border-color:#4a4a6a; }
    """)
    return b

def card(parent=None):
    w = QWidget(parent)
    w.setStyleSheet("background:#0d0d1a; border:1px solid #1a1a2e; border-radius:12px;")
    return w

def label_tag(text, color="#6c63ff"):
    l = QLabel(text)
    l.setStyleSheet(f"color:{color}; font-family:'Courier New'; font-size:9px; letter-spacing:1px;")
    return l

def cam_widget():
    l = QLabel("Camera not started")
    l.setAlignment(Qt.AlignCenter)
    l.setMinimumSize(400, 300)
    l.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    l.setStyleSheet("background:#000; color:#3a3a5c; border:1px solid #1a1a2e; border-radius:10px; font-size:12px;")
    return l

# ── Register Screen ───────────────────────────────────────────────────────────
class RegisterScreen(QWidget):
    go_login   = pyqtSignal()
    registered = pyqtSignal(str)

    def __init__(self, signals: Signals, worker: CameraWorker):
        super().__init__()
        self.signals  = signals
        self.worker   = worker
        self.encoding = None
        self._build()
        self.signals.frame_ready.connect(self._on_frame)
        self.signals.face_enrolled.connect(self._on_enrolled)

    def _build(self):
        outer = QHBoxLayout(self); outer.setContentsMargins(40,40,40,40); outer.setSpacing(30)

        # Left — form
        left = QVBoxLayout(); left.setSpacing(16)

        logo = QLabel("🔐")
        logo.setStyleSheet("font-size:36px; background:transparent;")
        title = QLabel("Create Account")
        title.setStyleSheet("color:#e8e4ff; font-size:24px; font-weight:bold; background:transparent;")
        sub = QLabel("Password + Face = Secure Access")
        sub.setStyleSheet("color:#5c5880; font-size:12px; background:transparent;")

        left.addStretch()
        left.addWidget(logo)
        left.addWidget(title)
        left.addWidget(sub)
        left.addSpacing(10)

        self.username_in = QLineEdit(); self.username_in.setPlaceholderText("Username")
        self.password_in = QLineEdit(); self.password_in.setPlaceholderText("Password (min 10 characters)")
        self.password_in.setEchoMode(QLineEdit.Password)
        self.confirm_in  = QLineEdit(); self.confirm_in.setPlaceholderText("Confirm Password")
        self.confirm_in.setEchoMode(QLineEdit.Password)

        left.addWidget(self.username_in)
        left.addWidget(self.password_in)
        left.addWidget(self.confirm_in)

        self.err_lbl = QLabel("")
        self.err_lbl.setStyleSheet("color:#f87171; font-size:11px; background:transparent;")
        self.err_lbl.hide()
        left.addWidget(self.err_lbl)

        self.register_btn = btn_primary("Create Account", "#6c63ff")
        self.register_btn.clicked.connect(self._on_register)
        left.addWidget(self.register_btn)

        login_row = QHBoxLayout()
        login_row.addWidget(QLabel("Already have an account?"))
        login_btn = QPushButton("Sign In")
        login_btn.setStyleSheet("QPushButton{background:transparent;color:#6c63ff;border:none;font-size:13px;}"
                                "QPushButton:hover{color:#a89cff;}")
        login_btn.clicked.connect(self.go_login)
        login_row.addWidget(login_btn); login_row.addStretch()
        left.addLayout(login_row)
        left.addStretch()

        form_wrap = QWidget()
        form_wrap.setLayout(left)
        form_wrap.setMaximumWidth(360)
        outer.addWidget(form_wrap)

        # Right — camera
        right = QVBoxLayout(); right.setSpacing(12)

        self.cam_lbl = cam_widget()
        right.addWidget(self.cam_lbl)

        self.face_status = QLabel("Step 2: After filling the form, scan your face")
        self.face_status.setStyleSheet("color:#5c5880; font-size:12px; text-align:center; background:transparent;")
        self.face_status.setAlignment(Qt.AlignCenter)
        right.addWidget(self.face_status)

        self.scan_btn = btn_primary("📷  Scan My Face", "#13131f")
        self.scan_btn.setStyleSheet("""
            QPushButton{background:#13131f;color:#7c78a8;border:1px solid #2a2a40;}
            QPushButton:hover{color:#e8e4ff;border-color:#6c63ff;}
            QPushButton:disabled{background:#0a0a14;color:#2a2a40;border-color:#1a1a2e;}
        """)
        self.scan_btn.clicked.connect(self._start_scan)
        right.addWidget(self.scan_btn)

        self.face_tick = QLabel("")
        self.face_tick.setAlignment(Qt.AlignCenter)
        self.face_tick.setStyleSheet("font-size:28px; background:transparent;")
        right.addWidget(self.face_tick)

        outer.addLayout(right, 1)

    def showEvent(self, e):
        super().showEvent(e)
        self.worker.start("preview")

    def hideEvent(self, e):
        super().hideEvent(e)
        self.worker.stop()

    def _on_frame(self, pix):
        scaled = pix.scaled(self.cam_lbl.width(), self.cam_lbl.height(),
                            Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.cam_lbl.setPixmap(scaled)

    def _start_scan(self):
        self.encoding = None
        self.face_tick.setText("")
        self.face_status.setText("🔍 Look at the camera…")
        self.face_status.setStyleSheet("color:#a78bfa; font-size:12px; background:transparent;")
        self.scan_btn.setEnabled(False)
        self.worker.stop()
        self.worker.start("enroll")

    def _on_enrolled(self, enc):
        self.encoding = enc
        self.face_tick.setText("✅")
        self.face_status.setText("Face captured! Now click Create Account.")
        self.face_status.setStyleSheet("color:#34d399; font-size:12px; background:transparent;")
        self.scan_btn.setEnabled(True)
        self.worker.start("preview")

    def _on_register(self):
        username = self.username_in.text().strip()
        password = self.password_in.text()
        confirm  = self.confirm_in.text()

        # Username validation — alphanumeric + _ and - only
        if not re.match(r'^[a-zA-Z0-9_\-]{3,32}$', username):
            return self._err("Username: 3–32 chars, letters/numbers/_ only.")
        if len(password) < 10:
            return self._err("Password must be at least 10 characters.")
        if password != confirm:
            return self._err("Passwords do not match.")
        if self.encoding is None:
            return self._err("Please scan your face first.")

        users = load_users()
        if username in users:
            return self._err("Username already exists.")

        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        users[username] = {"password": hashed, "face": self.encoding}
        save_users(users)
        append_log(username, "REGISTERED")

        self.err_lbl.hide()
        self.registered.emit(username)

    def _err(self, msg):
        self.err_lbl.setText(msg); self.err_lbl.show()


# ── Login Screen ──────────────────────────────────────────────────────────────
class LoginScreen(QWidget):
    go_register   = pyqtSignal()
    login_success = pyqtSignal(str)

    STEP_PASSWORD = "password"
    STEP_FACE     = "face"

    # [HIGH SEVERITY SECTION REDACTED]
    # Brute-force / rate limiting logic removed from this file.
    # See security notes in README before deploying.

    def __init__(self, signals: Signals, worker: CameraWorker):
        super().__init__()
        self.signals  = signals
        self.worker   = worker
        self.step     = self.STEP_PASSWORD
        self.username = ""
        self._build()
        self.signals.frame_ready.connect(self._on_frame)
        self.signals.face_matched.connect(self._on_face_result)

    def _build(self):
        outer = QHBoxLayout(self); outer.setContentsMargins(40,40,40,40); outer.setSpacing(30)

        # Left
        left = QVBoxLayout(); left.setSpacing(16)

        logo = QLabel("🔐")
        logo.setStyleSheet("font-size:36px; background:transparent;")
        self.title_lbl = QLabel("Welcome Back")
        self.title_lbl.setStyleSheet("color:#e8e4ff; font-size:24px; font-weight:bold; background:transparent;")
        sub = QLabel("Sign in with password + face")
        sub.setStyleSheet("color:#5c5880; font-size:12px; background:transparent;")

        left.addStretch()
        left.addWidget(logo); left.addWidget(self.title_lbl); left.addWidget(sub)
        left.addSpacing(10)

        # Step indicator
        steps_row = QHBoxLayout()
        self.step1_lbl = self._step_pill("1  Password", active=True)
        self.step2_lbl = self._step_pill("2  Face Scan", active=False)
        steps_row.addWidget(self.step1_lbl); steps_row.addWidget(self.step2_lbl)
        steps_row.addStretch()
        left.addLayout(steps_row)

        self.username_in = QLineEdit(); self.username_in.setPlaceholderText("Username")
        self.password_in = QLineEdit(); self.password_in.setPlaceholderText("Password")
        self.password_in.setEchoMode(QLineEdit.Password)
        self.password_in.returnPressed.connect(self._check_password)

        left.addWidget(self.username_in); left.addWidget(self.password_in)

        self.err_lbl = QLabel("")
        self.err_lbl.setStyleSheet("color:#f87171; font-size:11px; background:transparent;")
        self.err_lbl.hide()
        left.addWidget(self.err_lbl)

        self.next_btn = btn_primary("Next: Face Scan →", "#6c63ff")
        self.next_btn.clicked.connect(self._check_password)
        left.addWidget(self.next_btn)

        reg_row = QHBoxLayout()
        reg_row.addWidget(QLabel("No account?"))
        reg_btn = QPushButton("Register")
        reg_btn.setStyleSheet("QPushButton{background:transparent;color:#6c63ff;border:none;font-size:13px;}"
                              "QPushButton:hover{color:#a89cff;}")
        reg_btn.clicked.connect(self.go_register)
        reg_row.addWidget(reg_btn); reg_row.addStretch()
        left.addLayout(reg_row)
        left.addStretch()

        wrap = QWidget(); wrap.setLayout(left); wrap.setMaximumWidth(360)
        outer.addWidget(wrap)

        # Right — camera
        right = QVBoxLayout(); right.setSpacing(12)
        self.cam_lbl = cam_widget()
        right.addWidget(self.cam_lbl)

        self.face_status = QLabel("Complete Step 1 first")
        self.face_status.setAlignment(Qt.AlignCenter)
        self.face_status.setStyleSheet("color:#5c5880; font-size:12px; background:transparent;")
        right.addWidget(self.face_status)

        outer.addLayout(right, 1)

    def _step_pill(self, text, active=False):
        l = QLabel(text)
        if active:
            l.setStyleSheet("background:#6c63ff; color:white; font-size:11px; font-weight:bold; padding:4px 12px; border-radius:20px;")
        else:
            l.setStyleSheet("background:#13131f; color:#5c5880; font-size:11px; padding:4px 12px; border-radius:20px; border:1px solid #2a2a40;")
        return l

    def showEvent(self, e):
        super().showEvent(e)
        self._reset()
        self.worker.start("preview")

    def hideEvent(self, e):
        super().hideEvent(e)
        self.worker.stop()

    def _reset(self):
        self.step = self.STEP_PASSWORD
        self.username_in.setEnabled(True)
        self.password_in.setEnabled(True)
        self.next_btn.setEnabled(True)
        self.err_lbl.hide()
        self.step1_lbl.setStyleSheet("background:#6c63ff; color:white; font-size:11px; font-weight:bold; padding:4px 12px; border-radius:20px;")
        self.step2_lbl.setStyleSheet("background:#13131f; color:#5c5880; font-size:11px; padding:4px 12px; border-radius:20px; border:1px solid #2a2a40;")
        self.face_status.setText("Complete Step 1 first")
        self.face_status.setStyleSheet("color:#5c5880; font-size:12px; background:transparent;")

    def _on_frame(self, pix):
        scaled = pix.scaled(self.cam_lbl.width(), self.cam_lbl.height(),
                            Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.cam_lbl.setPixmap(scaled)

    def _check_password(self):
        username = self.username_in.text().strip()
        password = self.password_in.text()

        users = load_users()
        if username not in users:
            append_log("*", "FAILED", "Unknown username")   # don't log the attempted name
            return self._err("Invalid username or password.")

        hashed = users[username]["password"].encode()
        if not bcrypt.checkpw(password.encode(), hashed):
            append_log(username, "FAILED", "Wrong password")
            return self._err("Invalid username or password.")

        # Password OK — move to face step
        self.username   = username
        self.step       = self.STEP_FACE
        self.err_lbl.hide()
        self.username_in.setEnabled(False)
        self.password_in.setEnabled(False)
        self.next_btn.setEnabled(False)

        self.step1_lbl.setStyleSheet("background:#34d399; color:#000; font-size:11px; font-weight:bold; padding:4px 12px; border-radius:20px;")
        self.step2_lbl.setStyleSheet("background:#6c63ff; color:white; font-size:11px; font-weight:bold; padding:4px 12px; border-radius:20px;")

        self.face_status.setText("✅ Password OK  →  Now look at the camera…")
        self.face_status.setStyleSheet("color:#a78bfa; font-size:12px; background:transparent;")

        enc = users[username]["face"]
        self.worker.stop()
        self.worker.start("verify", target_encoding=enc)

    def _on_face_result(self, matched):
        if self.step != self.STEP_FACE:
            return
        if matched:
            append_log(self.username, "SUCCESS")
            self.face_status.setText("✅ Face matched! Logging in…")
            self.face_status.setStyleSheet("color:#34d399; font-size:12px; background:transparent;")
            QTimer.singleShot(800, lambda: self.login_success.emit(self.username))
        else:
            append_log(self.username, "FAILED", "Face mismatch")
            self._err("Face not recognised. Try again.")
            self.worker.stop()
            enc = load_users()[self.username]["face"]
            self.worker.start("verify", target_encoding=enc)

    def _err(self, msg):
        self.err_lbl.setText(msg); self.err_lbl.show()


# ── Dashboard Screen ──────────────────────────────────────────────────────────
class DashboardScreen(QWidget):
    logout = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.username = ""
        self._build()

    def _build(self):
        outer = QVBoxLayout(self); outer.setContentsMargins(40,30,40,30); outer.setSpacing(20)

        # Top bar
        top = QHBoxLayout()
        greet_col = QVBoxLayout()
        self.greet_lbl = QLabel("Welcome back!")
        self.greet_lbl.setStyleSheet("color:#e8e4ff; font-size:22px; font-weight:bold; background:transparent;")
        self.time_lbl = QLabel("")
        self.time_lbl.setStyleSheet("color:#5c5880; font-size:12px; background:transparent;")
        greet_col.addWidget(self.greet_lbl); greet_col.addWidget(self.time_lbl)
        top.addLayout(greet_col); top.addStretch()

        logout_btn = btn_secondary("⬅  Logout")
        logout_btn.clicked.connect(self.logout)
        top.addWidget(logout_btn)
        outer.addLayout(top)

        # Stats row
        stats = QHBoxLayout(); stats.setSpacing(16)

        self.stat_total  = self._stat_card("Total Logins",   "0", "#6c63ff")
        self.stat_failed = self._stat_card("Failed Attempts","0", "#f87171")
        self.stat_users  = self._stat_card("Registered Users","0","#34d399")
        stats.addWidget(self.stat_total)
        stats.addWidget(self.stat_failed)
        stats.addWidget(self.stat_users)
        outer.addLayout(stats)

        # Log table
        log_hdr = QLabel("ACCESS LOG")
        log_hdr.setStyleSheet("color:#3a3a5c; font-family:'Courier New'; font-size:10px; letter-spacing:1px; background:transparent;")
        outer.addWidget(log_hdr)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["TIME", "USER", "STATUS", "REASON"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        outer.addWidget(self.table)

        # Refresh timer
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._refresh)
        self.refresh_timer.start(3000)

    def _stat_card(self, label, value, color):
        w = QWidget()
        w.setStyleSheet(f"background:#0d0d1a; border:1px solid #1a1a2e; border-radius:10px;")
        v = QVBoxLayout(w); v.setContentsMargins(16,14,16,14)
        lbl = QLabel(label)
        lbl.setStyleSheet(f"color:{color}; font-family:'Courier New'; font-size:10px; background:transparent; border:none;")
        val = QLabel(value)
        val.setStyleSheet("color:#e8e4ff; font-size:28px; font-weight:bold; background:transparent; border:none;")
        v.addWidget(lbl); v.addWidget(val)
        w._val = val
        return w

    def set_user(self, username):
        self.username = username
        self.greet_lbl.setText(f"Welcome, {username} 👋")
        self._refresh()

    def showEvent(self, e):
        super().showEvent(e)
        self._refresh()

    def _refresh(self):
        self.time_lbl.setText(datetime.now().strftime("Last login: %Y-%m-%d %H:%M:%S"))
        log   = load_log()
        users = load_users()

        total   = sum(1 for e in log if e["status"] == "SUCCESS")
        failed  = sum(1 for e in log if e["status"] == "FAILED")
        n_users = len(users)

        self.stat_total._val.setText(str(total))
        self.stat_failed._val.setText(str(failed))
        self.stat_users._val.setText(str(n_users))

        self.table.setRowCount(0)
        for entry in log[:50]:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(entry.get("time","")))
            self.table.setItem(r, 1, QTableWidgetItem(entry.get("username","")))

            status = entry.get("status","")
            s_item = QTableWidgetItem(status)
            if status == "SUCCESS":
                s_item.setForeground(QColor("#34d399"))
            elif status == "FAILED":
                s_item.setForeground(QColor("#f87171"))
            else:
                s_item.setForeground(QColor("#a78bfa"))
            self.table.setItem(r, 2, s_item)
            self.table.setItem(r, 3, QTableWidgetItem(entry.get("reason","")))


# ── Main App ──────────────────────────────────────────────────────────────────
class MFAApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MFA System  •  Face + Password")
        self.resize(960, 640)
        self.setStyleSheet(STYLE)

        self.signals = Signals()
        self.worker  = CameraWorker(self.signals)

        self.stack     = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.register  = RegisterScreen(self.signals, self.worker)
        self.login     = LoginScreen(self.signals, self.worker)
        self.dashboard = DashboardScreen()

        self.stack.addWidget(self.login)      # 0
        self.stack.addWidget(self.register)   # 1
        self.stack.addWidget(self.dashboard)  # 2

        self.login.go_register.connect(lambda: self.stack.setCurrentIndex(1))
        self.login.login_success.connect(self._on_login)
        self.register.go_login.connect(lambda: self.stack.setCurrentIndex(0))
        self.register.registered.connect(self._on_registered)
        self.dashboard.logout.connect(self._on_logout)

        self.stack.setCurrentIndex(0)

    def _on_login(self, username):
        self.dashboard.set_user(username)
        self.stack.setCurrentIndex(2)

    def _on_registered(self, username):
        QMessageBox.information(self, "Account Created",
            f"Account '{username}' created successfully!\nYou can now sign in.")
        self.stack.setCurrentIndex(0)

    def _on_logout(self):
        self.stack.setCurrentIndex(0)

    def closeEvent(self, e):
        self.worker.stop()
        e.accept()


# ── Entry ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MFAApp()
    win.show()
    sys.exit(app.exec_())
