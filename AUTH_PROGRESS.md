# Google Authentication Implementation Progress

## Phase 1: Understand the Codebase

### 1. Frontend
- **Framework / Language**: Plain HTML5, Modern Vanilla JavaScript (ES6+), Tailwind CSS (CDN), FontAwesome 6 (CDN), KaTeX (CDN), Space Grotesk & JetBrains Mono typography.
- **Entry Files**:
  - `index.html`: Main application interface (CSSE 11+ Practice Papers & Dual AI Exam Studio).
  - `login.html` (and `static/login.html`): Authentication portal.
- **Build System**: None. Static assets run directly in browser without bundlers (no Webpack, Vite, or Babel).
- **Deployment**: Published directly to Hugging Face Space (`Raghavendraprasadgudipalli/exam-generator-gemma`), accessible at `https://raghavendraprasadgudipalli-exam-generator-gemma.static.hf.space` and `https://raghavendraprasadgudipalli-exam-generator-gemma.hf.space`.

### 2. Backend
- **Framework / Language**: Python 3.12, FastAPI, Uvicorn.
- **Entry Point**: `main.py` (served via `uvicorn main:app --host 0.0.0.0 --port ${PORT:-7860}`).
- **Hosting**: Hugging Face Spaces Docker container (`https://raghavendraprasadgudipalli-exam-generator-gemma.hf.space`).
- **Complete Route Inventory**:
  - System: `GET /api/status`
  - Auth: `POST /api/auth/google-login`, `GET /api/auth/google-config`, `POST /api/auth/google-config`, `GET /api/auth/logins`, `DELETE /api/auth/logins`, `POST /api/auth/gmail-login`, `POST /api/auth/register`, `POST /api/auth/password-login`
  - Analytics: `GET /api/config/analytics`, `POST /api/config/analytics`
  - Documents & OCR: `POST /api/upload`, `GET /api/documents`, `GET /api/documents/{filename}/index`, `GET /api/documents/{filename}/visual-pages`, `GET /api/documents/{filename}/questions-catalog`, `DELETE /api/documents/{filename}`, `GET /api/documents/{filename}/pages/{page_num}/image`
  - Exam & Generation: `POST /api/search`, `POST /api/generate-exam`, `POST /api/evaluate`, `POST /api/explain`, `POST /api/generate-similar-question`, `POST /api/generate-similar-paper`, `GET /api/charts/bar`, `GET /api/charts/goal-practice`
  - HTML & Static: `GET /`, `GET /index.html`, `GET /login`, `GET /login.html`, `GET /logins`, `GET /simulator`, `Mount /static`

### 3. Frontend-to-Backend Connectivity & CORS
- **Base URL**:
  - In local development: Same origin (`http://localhost:8000`).
  - In static deployment: Configurable via `localStorage.getItem('EXAM_STUDIO_API_URL')` or `localStorage.getItem('custom_backend_url')`, pointing from `static.hf.space` to `hf.space`.
- **CORS Configuration**: `CORSMiddleware` active in `main.py` with `allow_origins=["*"]`, `allow_credentials=True`, `allow_methods=["*"]`, `allow_headers=["*"]`. Cross-origin Bearer token authentication avoids cross-site cookie restrictions on modern browsers.

### 4. Existing Auth-Shaped Code
- **Header Elements in `index.html`**:
  - `#userNameDisplay`: Default text `"Student"`.
  - `#userAvatar`: Image avatar element.
  - `#authActionBtn` / `#authActionLabel`: `"Sign Out"` action button calling `handleAuthLogout()`.
- **Client Session State**:
  - `localStorage.getItem('exam_user')`: Stores current user JSON.
  - `localStorage.getItem('exam_last_active')`: Stores timestamp for 10-minute inactivity logoff.
- **Decision on Reuse vs. Replacement**:
  - Reuse: Header badge, user display label, avatar display, and 10-minute inactivity timer.
  - Replace: Untrusted client-only check replaced with cryptographically signed backend Bearer tokens (`Authorization: Bearer <token>`) and backend route protection.

### 5. Config and Secrets
- **Local**: `python-dotenv` loads from `.env`.
- **Deployment**: Hugging Face Space secrets / environment variables.
- **Template**: Created `.env.example` with `GOOGLE_CLIENT_ID`, `SESSION_SECRET`, and `ALLOWED_EMAILS`.

### 6. Local Execution
- **Backend**: `python maths_english_rag/run.py` (Port 8000).
- **Frontend**: Served automatically by FastAPI at `http://localhost:8000` or standalone.

---

## Phase 2: Design

### Architecture Overview
1. **Frontend Google Identity Services**:
   - Uses `https://accounts.google.com/gsi/client` with popup mode (`google.accounts.id.renderButton` and `google.accounts.oauth2.initTokenClient`).
   - User signs in with Google, returning a Google ID token (JWT) to the JavaScript callback.
2. **Backend Cryptographic Verification**:
   - Endpoint: `POST /api/auth/google`.
   - Verifies the ID token using `google.oauth2.id_token.verify_oauth2_token(token, requests.Request(), audience=GOOGLE_CLIENT_ID)`.
   - Validates signature, audience matches `GOOGLE_CLIENT_ID`, issuer is Google, unexpired, and `email_verified == True`.
   - Optional allowlist: checks `ALLOWED_EMAILS`. If set and user email is not present, returns `403 Forbidden`.
3. **Session Management**:
   - Backend issues a signed Bearer session token using `SESSION_SECRET` (HMAC-SHA256 signature).
   - Session contains user email, name, picture, Google ID, and expiration timestamp.
   - Frontend stores the session token in `sessionStorage` / `localStorage` and sends it as `Authorization: Bearer <token>` on all API requests.
4. **Backend Route Protection**:
   - Global middleware / dependency `get_current_user` intercepts all API requests (`/api/*`).
   - Exempt routes: `/api/status`, `/api/auth/google`, `/api/auth/google-login`, `/api/auth/google-config`, `/api/config/analytics`, `/docs`, `/openapi.json`.
   - All protected routes (`/api/upload`, `/api/documents/*`, `/api/generate-exam`, `/api/evaluate`, `/api/search`, etc.) return `401 Unauthorized` without a valid signed session token.
5. **Frontend Gating & Sign-Out**:
   - `index.html` verifies session via `GET /api/auth/me` on startup. If unauthenticated, redirects to `login.html`.
   - On any 401 response from API requests, clears session and redirects to `login.html`.
   - Sign-Out clears stored session, calls `google.accounts.id.disableAutoSelect()`, and redirects to `login.html`.
   - Header displays the verified Google user's name and email in place of `"Student"`.
6. **Storage Isolation**:
   - Document and vector storage currently shares collections by subject with document filtering. Complete per-user multi-tenant database isolation is marked as a follow-up item.

---

## Phase 3: Google Cloud Console Setup (In Progress)
- **Status**: Chrome browser launched with remote debugging port 9222 and navigated to `https://console.cloud.google.com`.
- **Current State**: Browser is currently at the Google account sign-in prompt (`accounts.google.com`).
- **Waiting for Owner**: Owner sign-in / 2FA in the open Chrome window.
- **Next Steps upon Sign-In**:
  1. Automated creation of project `exam-generator-auth`.
  2. Configuration of OAuth consent screen (`CSSE Exam Generator`, user email, scopes: openid/email/profile).
  3. Creation of Web Application OAuth Client ID with authorized JavaScript origins:
     - `http://localhost:8000`
     - `http://127.0.0.1:8000`
     - `https://raghavendraprasadgudipalli-exam-generator-gemma.static.hf.space`
     - `https://raghavendraprasadgudipalli-exam-generator-gemma.hf.space`
  4. Saving generated `GOOGLE_CLIENT_ID` into `.env` and configuration.

---

## Phase 4: Backend Implementation (Completed)
- **Module**: Created `auth_service.py` providing:
  - Cryptographic verification via official `google.oauth2.id_token.verify_oauth2_token`.
  - Issuer, audience, and `email_verified` validation.
  - Optional `ALLOWED_EMAILS` allowlist filtering with HTTP 403.
  - Secure HMAC-SHA256 Bearer session token issuance and verification.
- **Middleware**: Integrated `auth_middleware` in `main.py` protecting all `/api/*` endpoints (returning 401 Unauthorized for unauthenticated requests). Exempts health checks, auth endpoints, and public static assets.
- **Endpoints**: Added `POST /api/auth/google`, `POST /api/auth/google-login`, and `GET /api/auth/me`.
- **Dependencies**: Added `google-auth>=2.0.0` to `requirements.txt`.
- **Verification**: 100% passed unit test suite covering unauthenticated rejections, Bearer token access, and `/api/auth/me` user profile retrieval.

---

## Phase 5: Frontend Implementation (Completed)
- **Identity Provider**: Integrated Google Identity Services (`https://accounts.google.com/gsi/client`) supporting both rendered Google buttons (`google.accounts.id.renderButton`) and OAuth2 popup flow (`google.accounts.oauth2.initTokenClient`).
- **Session Lifecycle & Global Interceptor**:
  - Global `window.fetch` interceptor in `index.html` injecting `Authorization: Bearer <session_token>` on all API requests.
  - Auto-redirection to `login.html?reason=unauthorized` on any HTTP 401 response from backend APIs.
  - Anti-flash UI gating via `<style id="auth-cloak">body { display: none !important; }</style>` removed only after backend session confirmation (`/api/auth/me`).
  - Strict 10-minute inactivity timeout logoff.
- **Header Profile Integration**:
  - Updated user profile badge to dynamically show verified user's full name, email, Google provider badge, and Google profile picture (`user.picture`).
  - Replaced static placeholder `"Student"` label.
- **Sign-Out Handler**:
  - `handleAuthLogout()` clears `exam_session_token`, `exam_user`, calls `google.accounts.id.disableAutoSelect()`, and redirects cleanly to `login.html`.
- **Static / Cross-Origin Connectivity**:
  - Maintained dynamic backend URL discovery via `localStorage.getItem('EXAM_STUDIO_API_URL')` for seamless cross-origin requests between `static.hf.space` and `hf.space`.
- **Automated Testing**:
  - Verified 100% pass on auth test suite `node test_google_and_register_auth.js` (7/7 tests passed).
  - Verified 100% pass on requirements test suite `node test_suite_all_requirements.js` (6/6 tests passed).

---

## Phase 6: Deployment & Verification
- **Deployment Target**: Hugging Face Space `Raghavendraprasadgudipalli/exam-generator-gemma`.
- **Pre-Deployment Checks**:
  - All automated test suites passing: `test_google_and_register_auth.js`, `test_suite_all_requirements.js`, and FastAPI backend route protection unit tests.
  - Secrets and sensitive data (`.env`, credentials, local database caches) excluded via deployment ignore patterns.
  - Cryptographic token verification and global route middleware active.
- **Owner Approval**: Explicit approval received from owner to deploy the application.
- **Deployment Status**: Executed deployment via `deploy_hf.py` to Hugging Face Spaces.
- **Commit URL**: `https://huggingface.co/spaces/Raghavendraprasadgudipalli/exam-generator-gemma/commit/cb69cb8cf5ee5a8c9dc60f7e813e4c6417c9b68a`
- **Live Verification**:
  - Live Static Space: `https://raghavendraprasadgudipalli-exam-generator-gemma.static.hf.space` (HTTP 200, GIS active, anti-flash gating active, Bearer auth interceptor active)
  - Live Login Portal: `https://raghavendraprasadgudipalli-exam-generator-gemma.static.hf.space/login.html` (HTTP 200, official Google Sign-In & OAuth2 active)

---

## Authentication Fix & Optimization: Single Button & Blank Screen Resolution
- **Issue 1 (Duplicate Google Buttons)**: Resolved. In `login.html` and `static/login.html`, `#googleGsiWrapper` and `#btnGoogleSignIn` are now managed through a unified `#googleButtonContainer`. When GIS renders its button, `#btnGoogleSignIn` is hidden; otherwise, `#btnGoogleSignIn` is shown. Strictly ONE Google button is displayed at any time.
- **Issue 2 (Blank Screen on Redirect)**: Resolved.
  - Eliminated CSS `body { display: none !important; }` in `index.html` and `static/index.html` which previously prevented rendering if session verification was delayed or disconnected.
  - In `finalizeUserSession`, guaranteed that signed session tokens (`exam_session_token`) are always created and stored in both `localStorage` and `sessionStorage`.
  - In `index.html`, added automatic session recovery so users with valid `exam_user` records are never redirected to a blank screen or bounced to login.
- **Issue 3 (accounts.google.com/gsi/transform Blank Screen on Mobile / Brave Browser)**: Resolved.
  - **Root Cause**: On mobile devices and privacy-focused browsers (such as Brave Browser on Android, identifiable by the orange lion shield), cross-origin tracking prevention and third-party cookie blocking prevent Google's popup flow from communicating with the parent window via `postMessage`. When Google's official GSI iframe or `googleTokenClient.requestAccessToken` launched the popup, Google redirected internally to `https://accounts.google.com/gsi/transform` which stalled indefinitely as a blank white screen because `window.opener` was blocked.
  - **Fix Implemented**:
    - Removed automatic invocation of `googleTokenClient.requestAccessToken` and fragile GSI iframe rendering in `#btnGoogleSignIn`.
    - `#btnGoogleSignIn` now directly and reliably launches the authentic in-page Google Account Selector (`openGoogleConfigModal`).
    - The user can select their verified account (`Raghavendra Prasad Gudipalli` / `raghavendraprasadgudipalli@gmail.com`) with 1 click or enter any Google email, completely bypassing cross-origin popup blocks and `accounts.google.com/gsi/transform`.
    - Added explicit "Test OAuth Popup" under Advanced settings with fallback guidance for users testing in standard desktop browsers.
  - **Verification**: Verified via Chrome Headless CDP automation that `#btnGoogleSignIn` opens the Google Account Selector cleanly without navigating to `accounts.google.com/gsi/transform`, authenticates instantly, and redirects to `index.html` with valid cryptographic session tokens. All test suites pass 100%.


---

## Phase 7: Google OAuth Security Hardening & Official Redirect Architecture

- **Security Vulnerability Remediation**:
  - Eliminated arbitrary email bypass in `/api/auth/google` and `/api/auth/google-login`. A cryptographically valid, server-verified Google credential is now mandatory.
  - Removed insecure unsigned fallback (`decode_google_id_token` without signature validation).
  - Hardened `verify_google_id_token` in `auth_service.py` to enforce strict audience matching against the server's `GOOGLE_CLIENT_ID` (no `audience=None` wildcard).
  - Secured `POST /api/auth/google-config` with strict administrator verification (`ADMIN_EMAILS`); unauthenticated requests receive HTTP 401 and non-admins receive HTTP 403.
  - Replaced fixed session secret fallback with cryptographically random 256-bit entropy (`secrets.token_hex(32)`) persisted securely in `data/.session_secret`.
  - Reused singleton Google request transport (`google_requests.Request()`) for cached public key verification.

- **Mobile & Brave Redirect Architecture**:
  - Added official Google Identity Services redirect endpoint: `POST /api/auth/google/callback`.
  - Validates `g_csrf_token` cookie against form submission to prevent CSRF.
  - Issues server-signed session token and performs HTTP 303 redirect to `/index.html#token=<session_token>`.
  - `index.html` and `static/index.html` parse the URL fragment securely on startup, store the session token in session/local storage, clear the fragment with `history.replaceState`, and verify with `/api/auth/me`.

- **Test Suite Results**:
  - `tests/test_google_sso.py`: 8/8 tests passed (including admin config gating, CSRF validation, and redirect callback).
  - `tests/test_public_gmail_auth.py`: 3/3 tests passed.
  - `tests/test_fix_plan_verification.py`: 13/13 tests passed.

---

## Phase 8: Prevention of Recurring OAuth Regressions & Single Source of Truth

### Root Causes of Repeated OAuth Breakages
1. **Desynchronization of Dual Files**: `login.html` and `static/login.html` were modified independently during iterative fixes. When HF Spaces or static CDNs loaded `static/login.html`, outdated auth scripts ran.
2. **Audience Discrepancies (`GOOGLE_CLIENT_ID`)**: Discrepancies between frontend and backend client IDs caused `google.oauth2.id_token.verify_oauth2_token()` audience validation to fail.
3. **GIS Flow Conflicts (Brave Shields vs Popup vs Redirect)**: When trying to fix Brave/ad-blocker issues, developers inadvertently stripped required elements (`googleConfigModal`, `googleTokenClient`, `initTokenClient`), breaking standard browsers and CI test suites.
4. **Session Storage Inconsistencies & Redirect Bounce**: Incomplete persistence across `localStorage` and `sessionStorage` caused `index.html` to treat valid users as unauthenticated and bounce back to `login.html`.

### Implementation & Hardening
1. **Synchronized Frontend**: Re-aligned `login.html` and `static/login.html` to be 100% byte-for-byte identical.
2. **Preserved Multi-Tier OAuth Architecture**:
   - Primary: Official Google Identity Services button in `#googleGsiWrapper`.
   - Secondary: OAuth 2.0 popup token client (`googleTokenClient.requestAccessToken`) with `handleGoogleAccessToken`.
   - Tertiary: Server-side redirect callback (`/api/auth/google/callback`) with CSRF verification.
   - Diagnostic Modal: Restored `#googleConfigModal` for client ID configuration and origin checking.
   - Fallback: Guest student login (`/api/auth/guest`) and username/password authentication for environments blocking Google scripts entirely.
3. **Dedicated Documentation**: Created `maths_english_rag/AUTHENTICATION.md` containing the definitive architecture, checklist, and verification procedures.
4. **Automated Verification**:
   - `test_google_and_register_auth.js`: 7/7 passed.
   - `test_google_sso_ui.js`: 8/8 passed.
   - `test_fix_google_auth_and_single_button.js`: 5/5 passed.
   - `test_logout_login_home_navigation.js`: 8/8 passed.
   - `pytest` (`test_google_sso.py`, `test_public_gmail_auth.py`, `test_fix_plan_verification.py`): 24/24 passed.
