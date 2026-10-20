# Google OAuth & Authentication Architecture & Runbook (AUTH.md)

## Overview
This document serves as the **authoritative reference** for Google OAuth 2.0 and authentication in the CSSE Exam Generator application (`maths_english_rag`). It explains the architectural design, the root causes of recurring OAuth breakages, how to prevent regressions, and how to verify changes.

---

## 1. Why OAuth Stops Working When Changes Are Made (Root Causes)

Across previous iterations, Google OAuth repeatedly broke whenever authentication modifications were made due to **6 interdependent root causes**:

### Cause 1: File Desynchronization (`login.html` vs `static/login.html`)
* **Mechanism**: The repository serves frontend files from both the root directory (`login.html`, `index.html`) and the `/static` directory (`static/login.html`, `static/index.html`). On Hugging Face Spaces (`static.hf.space`) or static CDNs, files are served directly from `static/`.
* **Failure**: Modifying `login.html` without immediately synchronizing `static/login.html` leaves stale auth logic, outdated Client IDs, or broken redirect URIs in production.
* **Rule**: `login.html` and `static/login.html` must remain **100% byte-for-byte identical**. Always update both in tandem or run synchronization scripts.

### Cause 2: Audience & Client ID Discrepancies (`GOOGLE_CLIENT_ID`)
* **Mechanism**: Google ID tokens (`JWT`) are cryptographically sealed with the `aud` (audience) claim matching the Google OAuth Client ID that created them.
* **Failure**: If the backend environment variable `GOOGLE_CLIENT_ID` does not match the frontend `DEFAULT_GOOGLE_CLIENT_ID` (or custom Client ID), `google.oauth2.id_token.verify_oauth2_token()` fails with `ValueError: Token used with wrong audience`.
* **Rule**:
  * Default Client ID: `665867492986-i93mav5ld0gtld6c00vaeql8quakcmcp.apps.googleusercontent.com`
  * Default is consistent across `auth_service.py`, `main.py`, `login.html`, and `static/login.html`.
  * The backend endpoint `GET /api/auth/google-config` always exposes the authoritative ID.

### Cause 3: Google Identity Services (GIS) Flow Fragmentation (Popup vs Redirect vs Shields)
* **Mechanism**:
  1. **Standard GIS Button** (`google.accounts.id.renderButton`): Renders a cross-origin iframe. On privacy browsers (Brave Shields, Safari ITP, Firefox Enhanced Tracking), the iframe `postMessage` handshake is blocked, causing popups to hang on `accounts.google.com/gsi/transform`.
  2. **OAuth2 Token Client** (`google.accounts.oauth2.initTokenClient`): Uses direct popup message channel. If third-party cookies are blocked or popups are prevented, it fails to complete.
  3. **Redirect Mode** (`ux_mode: 'redirect'`): Navigates the entire browser window to Google and POSTs credentials back to `login_uri` (`/api/auth/google/callback`). **Crucially**, this requires the exact redirect URI to be pre-registered in Google Cloud Console. If omitted, Google throws `redirect_uri_mismatch (Error 400)`.
* **Failure**: When attempting to "fix" one environment (e.g. Brave browser), developers switched modes or removed `initTokenClient` / `renderButton`, inadvertently breaking standard browsers, automated tests, or OAuth configurations.
* **Rule**: The system uses a **multi-tiered, resilient strategy**:
  * Tier 1: Official GIS rendered button in `#googleGsiWrapper`.
  * Tier 2: Token client popup (`googleTokenClient.requestAccessToken`) on `#btnGoogleSignIn`.
  * Tier 3: GIS redirect endpoint (`POST /api/auth/google/callback`) with CSRF protection.
  * Tier 4: Clear error diagnostics via `#googleConfigModal` for misconfigured origins/client IDs.
  * Tier 5: Guest student fallback (`/api/auth/guest`) and standard username/password authentication so users are never locked out if Google scripts are completely blocked.

### Cause 4: Session Storage Partitioning & "Redirect Bounce"
* **Mechanism**: `index.html` checks for active authentication on load. If authentication verification fails or is delayed, it redirects to `login.html`.
* **Failure**: If login writes `token` to `sessionStorage` but `index.html` only inspects `localStorage` (or vice-versa), or if `exam_user` is not initialized prior to page load, `index.html` bounces the user straight back to `login.html`, giving the illusion that OAuth failed.
* **Rule**: `finalizeUserSession(user, token)` synchronously sets:
  * `localStorage.setItem('exam_session_token', token)`
  * `sessionStorage.setItem('exam_session_token', token)`
  * `localStorage.setItem('exam_user', JSON.stringify(user))`
  * `localStorage.setItem('exam_last_active', Date.now().toString())`

### Cause 5: Google Cloud Console Authorized Origin & Redirect URI Mismatch
* **Mechanism**: Google OAuth strictly rejects requests originating from unauthorized domains or redirecting to unauthorized URIs.
* **Required Google Cloud Console Origins**:
  * `http://localhost:8000`
  * `http://127.0.0.1:8000`
  * `https://raghavendraprasadgudipalli-exam-generator-gemma.hf.space`
  * `https://raghavendraprasadgudipalli-exam-generator-gemma.static.hf.space`
* **Required Redirect URIs**:
  * `http://localhost:8000/api/auth/google/callback`
  * `https://raghavendraprasadgudipalli-exam-generator-gemma.hf.space/api/auth/google/callback`

### Cause 6: Accidental Removal of Elements Required by Automated Tests
* **Failure**: Removing modal markup (`googleConfigModal`, `inputGoogleClientId`, `btnSaveGoogleConfig`) or JavaScript callbacks (`handleGoogleAccessToken`, `googleTokenClient`) breaks the automated CI/CD test suites (`test_google_and_register_auth.js`, `test_google_sso_ui.js`).
* **Rule**: All test-required DOM elements and handler functions must remain present and functional.

---

## 2. Authentication Architecture

```
[ Browser / Client ]
       │
       ├─► Tier 1: GIS Rendered Button (ID Token)
       │         │
       │         ▼
       ├─► Tier 2: OAuth2 Popup Client (Access Token)
       │         │
       │         ▼
       ├─► Tier 3: Browser Shields Blocked ──► [ Guest Student / Password Login ]
       │
       ▼ (Credentials sent via JSON or Callback)
[ FastAPI Backend ]
       │
       ├─► auth_service.py: verify_google_id_token() [audience check against GOOGLE_CLIENT_ID]
       │         │ (If access token: login_tracker.py -> https://www.googleapis.com/oauth2/v3/userinfo)
       │         ▼
       ├─► ALLOWED_EMAILS verification (optional allowlist filter)
       ├─► create_session_token() [HMAC-SHA256 signed JWT with user profile & exp]
       ▼
[ Client Session Finalization ]
       │
       ├─► Store tokens in localStorage + sessionStorage
       ├─► Anti-flash gating resolved
       └─► Redirect to index.html
```

---

## 3. Rules of Engagement: Modifying Authentication Safely

When making ANY changes to authentication, follow this strict checklist:

1. **Never delete `googleConfigModal` or its child elements**:
   `#googleConfigModal`, `#inputGoogleClientId`, `#btnSaveGoogleConfig`, `handleSaveGoogleConfig`, `openGoogleConfigModal`, `closeGoogleConfigModal`.
2. **Never delete `googleTokenClient` or `initTokenClient`**:
   Required for popup OAuth2 flows and automated testing.
3. **Always keep `login.html` and `static/login.html` identical**:
   Copy updates to both files and verify with `diff` or `Compare-Object`.
4. **Preserve `DEFAULT_GOOGLE_CLIENT_ID` across frontend and backend**:
   `665867492986-i93mav5ld0gtld6c00vaeql8quakcmcp.apps.googleusercontent.com`.
5. **Always test both ID token verification and OAuth2 access token fallback**:
   `/api/auth/google` handles ID tokens; fallback to `login_tracker.verify_google_token` handles access tokens.
6. **Always verify all automated test suites before committing**:
   See Section 4 below.

---

## 4. Verification & Testing Commands

Before committing or deploying any authentication changes, execute the full test battery:

```bash
# 1. UI and Integration Tests (Node.js)
node maths_english_rag/tests/test_google_and_register_auth.js
node maths_english_rag/tests/test_google_sso_ui.js
node maths_english_rag/tests/test_fix_google_auth_and_single_button.js
node maths_english_rag/tests/test_logout_login_home_navigation.js

# 2. Backend Security & Endpoint Unit Tests (pytest)
pytest maths_english_rag/tests/test_google_sso.py maths_english_rag/tests/test_public_gmail_auth.py maths_english_rag/tests/test_fix_plan_verification.py
```

Expected result: **100% of tests must pass (0 failures).**
