# MFA-Face-Authentication

⚠️ This is an educational/demo project.
Not recommended for production use without additional hardening.
Multi-factor authentication system using face recognition + password — runs 100% offline, no API key needed.


A secure Multi-Factor Authentication (MFA) system that requires BOTH 
a password AND face recognition to grant access. Built entirely in 
Python, runs 100% offline on your local machine — no internet, 
no API keys, no cloud services.

Designed as a cybersecurity project demonstrating real-world 2FA 
concepts using biometric authentication.

How it works:
- Register with a username, password, and face scan
- Login requires password first, then face verification
- Both factors must pass — one alone is not enough
- All data stored locally with bcrypt-hashed passwords

Features:
- Two-factor authentication (password + biometric face scan)
- Real-time face detection and matching using face_recognition + dlib
- Passwords hashed with bcrypt (never stored in plain text)
- Face stored as 128-point numerical vector, not as a photo
- Live access log dashboard with timestamps and success/fail status
- Brute-force resistant — failed attempts are logged
- Clean dark UI built with PySide6

Tech Stack:
Python • face_recognition • dlib • OpenCV • PySide6 • bcrypt
