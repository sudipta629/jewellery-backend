# Jewellery E-Commerce API

A production-ready REST API backend for a full-stack jewellery e-commerce and store management system.

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.13 |
| Framework | Flask 3 |
| CORS | Flask-Cors |
| Config | python-dotenv |
| Database | PostgreSQL + Flask-SQLAlchemy |
| Migrations | Flask-Migrate / Alembic |
| Authentication | Flask-JWT-Extended |
| Rate Limiting | Flask-Limiter |

## Project Structure

```
backend/
│
├── app/
│   ├── __init__.py           ← Application factory (create_app)
│   ├── config.py             ← Environment-based configuration
│   ├── extensions.py         ← Flask extensions registry
│   │
│   ├── models/
│   │   ├── base.py           ← TimestampMixin (created_at, updated_at)
│   │   ├── user.py           ← User model
│   │   ├── address.py        ← Address model
│   │   ├── otp_verification.py ← OTP record model
│   │   └── token_blacklist.py  ← JWT revocation model
│   │
│   ├── routes/
│   │   ├── __init__.py       ← Blueprint registration hub
│   │   ├── health.py         ← GET /api/v1/health
│   │   ├── db_health.py      ← GET /api/v1/db-health
│   │   ├── auth.py           ← Authentication endpoints (STEP 5)
│   │   ├── users.py          ← User profile endpoints (STEP 6)
│   │   └── addresses.py      ← Address CRUD endpoints (STEP 6)
│   │
│   ├── services/
│   │   ├── auth_service.py   ← OTP + JWT + token blacklist logic
│   │   ├── user_service.py   ← User profile business logic
│   │   └── address_service.py ← Address CRUD + default logic
│   │
│   └── utils/
│       └── validators.py     ← Email, phone, name, pincode validators
│
├── tests/
│   ├── conftest.py           ← Pytest fixtures (in-memory SQLite)
│   ├── test_auth.py          ← Auth endpoint tests
│   ├── test_users.py         ← User profile tests
│   └── test_addresses.py     ← Address CRUD tests
│
├── migrations/               ← Alembic migration scripts
├── .env                      ← Local secrets (NOT committed to Git)
├── .env.example              ← Public template (safe to commit)
├── requirements.txt
├── run.py                    ← Development server entry point
└── README.md
```

## Getting Started

### 1. Create a virtual environment

```bash
# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
copy .env.example .env   # Windows
cp .env.example .env     # macOS/Linux
```

Open `.env` and fill in your values (DATABASE_URL, SECRET_KEY, JWT_SECRET_KEY).

### 4. Run database migrations

```bash
flask db upgrade
```

### 5. Run the development server

```bash
python run.py
```

---

## API Endpoints

### Health Checks

| Method | URL | Auth | Description |
|--------|-----|------|-------------|
| GET | `/api/v1/health` | None | App health check |
| GET | `/api/v1/db-health` | None | Database connection check |

---

### Authentication (STEP 5)

#### POST `/api/v1/auth/request-otp`
Generate an OTP for login.

**Request:**
```json
{ "identifier": "user@example.com", "identifier_type": "email" }
```
**Response (200):**
```json
{ "status": "success", "message": "OTP generated successfully.", "otp": "123456" }
```

---

#### POST `/api/v1/auth/verify-otp`
Verify OTP and receive JWT tokens.

**Request:**
```json
{ "identifier": "user@example.com", "identifier_type": "email", "otp": "123456" }
```
**Response (200):**
```json
{
  "status": "success",
  "access_token": "...",
  "refresh_token": "...",
  "user": { "id": 1, "name": "New Customer", "email": "user@example.com", "role": "customer", "is_verified": true }
}
```

---

#### POST `/api/v1/auth/refresh`
Get a new access token using a refresh token.

**Headers:** `Authorization: Bearer <refresh_token>`

**Response (200):**
```json
{ "status": "success", "access_token": "..." }
```

---

#### GET `/api/v1/auth/me`
Get the current user's profile (auth endpoint version).

**Headers:** `Authorization: Bearer <access_token>`

---

#### POST `/api/v1/auth/logout`
Revoke the current access token (and optionally refresh token).

**Headers:** `Authorization: Bearer <access_token>`

**Request (optional):**
```json
{ "refresh_token": "..." }
```
**Response (200):**
```json
{ "status": "success", "message": "Logged out successfully." }
```

---

### User Profile (STEP 6)

All endpoints require: `Authorization: Bearer <access_token>`

#### GET `/api/v1/users/me`
View own profile. User ID always comes from JWT — not from request.

**Response (200):**
```json
{
  "status": "success",
  "user": {
    "id": 1,
    "name": "John Doe",
    "email": "john@example.com",
    "phone": null,
    "role": "customer",
    "is_verified": true,
    "created_at": "2026-09-22T16:00:00+00:00",
    "updated_at": "2026-09-22T16:00:00+00:00"
  }
}
```

**Errors:** `401` (no token), `404` (user deleted)

---

#### PUT `/api/v1/users/me`
Update own profile. Only `name` can be changed.
Email/phone require a separate OTP verification flow (future step).

**Request:**
```json
{ "name": "Jane Doe" }
```

**Response (200):**
```json
{
  "status": "success",
  "message": "Profile updated successfully.",
  "user": { ... },
  "warnings": []
}
```

**Errors:** `400` (empty name / name too long), `401`

> **Note:** Sending `email`, `phone`, `role`, or `is_verified` returns 200 but those fields are NOT changed — a `warnings` array explains why.

---

### Addresses (STEP 6)

All endpoints require: `Authorization: Bearer <access_token>`

#### GET `/api/v1/addresses/`
List all addresses belonging to the authenticated user.

**Response (200):**
```json
{
  "status": "success",
  "addresses": [
    {
      "id": 1,
      "full_name": "John Doe",
      "phone": "9876543210",
      "address_line": "123 Main Road",
      "city": "Kolkata",
      "state": "West Bengal",
      "pincode": "700001",
      "is_default": true,
      "created_at": "...",
      "updated_at": "..."
    }
  ]
}
```

---

#### POST `/api/v1/addresses/`
Create a new address. `user_id` is always taken from JWT — never from the body.

**Request:**
```json
{
  "full_name": "John Doe",
  "phone": "9876543210",
  "address_line": "123 Main Road",
  "city": "Kolkata",
  "state": "West Bengal",
  "pincode": "700001",
  "is_default": false
}
```

**Response (201):**
```json
{ "status": "success", "message": "Address created successfully.", "address": { ... } }
```

**Rules:**
- First address is **always** made default automatically.
- `is_default: true` clears all other defaults atomically.

**Errors:** `400` (missing/invalid fields), `401`

---

#### PUT `/api/v1/addresses/<address_id>`
Update an address. Only updates fields present in the body. Only own addresses.

**Request (all optional):**
```json
{ "city": "Mumbai", "is_default": true }
```

**Response (200):**
```json
{ "status": "success", "message": "Address updated successfully.", "address": { ... } }
```

**Errors:** `400` (validation), `401`, `404` (not found or not owned)

---

#### DELETE `/api/v1/addresses/<address_id>`
Delete an address. Only own addresses. If the deleted address was default, the oldest remaining address becomes default.

**Response (200):**
```json
{ "status": "success", "message": "Address deleted successfully." }
```

**Errors:** `401`, `404` (not found or not owned)

---

## Running Tests

```bash
# All tests
python -m pytest tests/ -v

# Only auth tests
python -m pytest tests/test_auth.py -v

# Only profile tests
python -m pytest tests/test_users.py -v

# Only address tests
python -m pytest tests/test_addresses.py -v
```

---

## Environment Variables

| Variable | Description | Required |
|---|---|---|
| `FLASK_ENV` | `development`, `testing`, or `production` | Yes |
| `SECRET_KEY` | Flask session signing key | Yes |
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `JWT_SECRET_KEY` | JWT token signing key | Yes |
| `JWT_ACCESS_TOKEN_EXPIRES` | Access token lifetime (e.g. `15m`) | No |
| `JWT_REFRESH_TOKEN_EXPIRES` | Refresh token lifetime (e.g. `30d`) | No |
| `OTP_EXPIRY_MINUTES` | OTP validity window (default: `5`) | No |
| `OTP_MAX_ATTEMPTS` | Max wrong OTP attempts (default: `5`) | No |
| `RATELIMIT_STORAGE_URI` | `memory://` or Redis URL | No |
| `FRONTEND_URL` | React app URL for CORS | Yes |

---

## Development Steps

- [x] **Step 1** — Flask foundation, health-check endpoint, CORS, configuration
- [x] **Step 2** — PostgreSQL + SQLAlchemy + Alembic migrations
- [x] **Step 3** — Database model architecture (User, Address, OTPVerification)
- [x] **Step 4** — User + Address models + migration
- [x] **Step 5** — Passwordless OTP authentication + JWT (request-otp, verify-otp, refresh, me, logout) + rate limiting + token blacklisting
- [x] **Step 6** — User Profile + Address API (GET/PUT /users/me, full address CRUD)
- [ ] **Step 7** — Product catalogue
- [ ] **Step 8** — Order management

## Production Deployment

This project is configured for deployment using Gunicorn and Docker. It can be easily deployed to platforms like AWS ECS, DigitalOcean App Platform, Render, or Heroku.

### 1. Required Environment Variables
Ensure the following are set in your production environment:
- `FLASK_ENV=production`
- `SECRET_KEY=your_secure_random_string`
- `JWT_SECRET_KEY=your_secure_random_string`
- `DATABASE_URL=postgresql+psycopg://user:password@host/db`
- `FRONTEND_URL=https://your-production-frontend-domain.com`

### 2. Database Migration
Run the following command on the production server (or let the deployment script run it) before starting the application:
```bash
flask db upgrade
```

### 3. Build & Run (Docker)
```bash
docker build -t jewellery-backend .
docker run -p 5000:5000 --env-file .env jewellery-backend
```

### 4. Start Command (Without Docker)
If running directly on a Linux server:
```bash
gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 3 --access-logfile - --error-logfile - "app:create_app()"
```

### 5. Health Check
Most deployment platforms require a health check URL. Use:
- **Endpoint:** `GET /api/v1/health`
- **Expected Status:** `200 OK`

### 6. CORS Configuration
Ensure `FRONTEND_URL` is set correctly. The backend will strictly reject requests from any origin other than the one specified. Wildcards (`*`) should not be used in production.

---

## License

Private — all rights reserved.
