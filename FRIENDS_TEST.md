# Simulacra — Tester & Friend Onboarding Guide

Welcome to the **Simulacra** roleplay host test release! This document explains how multi-user profile switching, soft privacy, adult mode gating, and sessions work on your local PC.

---

## 1. Creating Your Profile & Profile Switching
* **First-Run Profile Setup:** Upon launching Simulacra, you will be prompted to select or create a profile.
* **Date of Birth & Privacy:** Enter your Display Name and Date of Birth. Age is calculated locally to determine adult feature availability.
* **Optional PIN & Recovery Code:** You can set a 4-digit PIN to restrict quick profile switching. When a PIN is created, a **One-Time Recovery Code** (`REC-XXXX-XXXX-XXXX`) is automatically generated. Keep note of your recovery code in case you forget your PIN.
* **Switching Profiles:** Click the active profile badge in the top right header to lock or switch profiles.

---

## 2. Adult Mode (`/adult`) & Gating
* **Adult Formula:** Adult mode requires:
  1. Profile Age ≥ 18 (derived from DOB) **AND**
  2. First-run adult attestation (or typing `/adult on` in chat) **AND**
  3. Character `canon_adult` card status.
* **Under-18 Profiles:** Profiles under 18 have adult mode permanently locked off.
* **HEAT & Presentation Settings:** Adult profiles can configure depiction controls (`SFW`, `Fade-to-Black`, or `Explicit`) under settings.

---

## 3. Storage & Session Persistence
* **SQLite Local Database:** All profiles, active session history, turn history, and character progression are stored in an encrypted local database located at:
  ```text
  Profiles/app_data.db
  ```
* **Read-Only Preset Cards:** Character templates under `Characters/` remain read-only file assets.

---

## 4. Reporting Bugs & Exporting Sessions
* **Exporting Sessions:** You can export session transcripts to `.md` or JSON snapshots for debugging directly from the session menu.
* **Submitting Feedback:** Report any bugs, prompt leaks, or crashes with the session timestamp and exported transcript.

---
Thank you for testing Simulacra!
