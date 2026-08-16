# Simulacra — Tester & Friend Onboarding Guide

Welcome to the **Simulacra** roleplay host test release! This document explains how multi-user profile switching, soft privacy, adult mode gating, and sessions work on your local PC.

---

## 1. First-run wizard
On a fresh install (or after this update, until you finish it once) Simulacra opens a **setup wizard** before the stage:

1. What this app is
2. Your display name, date of birth, optional PIN, and 18+ attestation
3. Recovery code if you set a PIN — write it down, it is shown once
4. Local voice model — download the small Dolphin 3 1B (~800 MB), or skip and use Mock until Settings → Roleplaying

The wizard will not appear again after **Start using Simulacra**. You can still add profiles and models later.

## 2. Creating extra profiles & switching
* **Date of Birth & Privacy:** Enter your Display Name and Date of Birth. Age is calculated locally to determine adult feature availability.
* **Optional PIN & Recovery Code:** You can set a 4-digit PIN to restrict quick profile switching. When a PIN is created, a **One-Time Recovery Code** (`REC-XXXX-XXXX-XXXX`) is automatically generated. Keep note of your recovery code in case you forget your PIN.
* **Switching Profiles:** Click the active profile badge in the top right header to lock or switch profiles.

---

## 3. Adult Mode (`/adult`) & Gating
* **Adult Formula:** Adult mode requires:
  1. Profile Age ≥ 18 (derived from DOB) **AND**
  2. First-run adult attestation (or typing `/adult on` in chat) **AND**
  3. Character `canon_adult` card status.
* **Under-18 Profiles:** Profiles under 18 have adult mode permanently locked off.
* **HEAT & Presentation Settings:** Adult profiles can configure depiction controls (`SFW`, `Fade-to-Black`, or `Explicit`) under settings.

---

## 4. Storage & Session Persistence
* **SQLite Local Database:** All profiles, active session history, turn history, and character progression are stored in an encrypted local database located at:
  ```text
  Profiles/app_data.db
  ```
* **Read-Only Preset Cards:** Character templates under `Characters/` remain read-only file assets.

---

## 5. Reporting Bugs & Exporting Sessions
* **Exporting Sessions:** You can export session transcripts to `.md` or JSON snapshots for debugging directly from the session menu.
* **Submitting Feedback:** Report any bugs, prompt leaks, or crashes with the session timestamp and exported transcript.

---
Thank you for testing Simulacra!
