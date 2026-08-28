# FastAPI + MySQL

FastAPI REST API with MySQL database using SQLAlchemy ORM, featuring JWT authentication and a React frontend.

## Project Structure

```
├── main.py                # App entry point, CORS config, router registration
├── database.py            # DB connection & session factory
├── core/
│   └── security.py        # JWT auth, password hashing, OAuth2 scheme
├── models/
│   ├── user.py            # SQLAlchemy User model
│   ├── device.py          # SQLAlchemy Device model
│   ├── role.py            # SQLAlchemy Role model
│   └── roledevice.py      # Many-to-many relationship table (roles ↔ devices)
├── schemas/
│   ├── user.py            # Pydantic User schemas (Create, Update, Out, Login)
│   ├── device.py          # Pydantic Device schemas (Create, Update, Out)
│   └── role.py            # Pydantic Role schemas (CreateDto, UpdateDto, RoleDto, DeviceDto)
├── crud/
│   ├── user.py            # User CRUD operations
│   ├── device.py          # Device CRUD operations
│   └── role.py            # Role CRUD operations (with device associations)
├── routers/
│   ├── auth.py            # Auth endpoints (login, hash password)
│   ├── user.py            # User API endpoints
│   ├── device.py          # Device API endpoints
│   └── role.py            # Role API endpoints
├── frontend/              # React + Vite frontend application
│   ├── src/
│   │   ├── pages/         # Login, Home, Users, Devices, Roles pages
│   │   ├── components/    # Sidebar component
│   │   ├── axios.js       # Centralized Axios instance with 401 interceptor
│   │   └── configContext.jsx  # App configuration context
│   └── package.json
├── api_io_log.py          # Request/response logging middleware
├── logs/                  # Auto-created log directory (YYYY-MM-DD.log files)
├── service.py             # Test service
└── test.py                # PyMySQL test
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MYSQL_USER` | dzuser | MySQL username |
| `MYSQL_PASSWORD` | L@12345678 | MySQL password |
| `MYSQL_HOST` | localhost | MySQL host |
| `MYSQL_PORT` | 3307 | MySQL port |
| `MYSQL_DB` | dzservice | Database name |
| `SECRET_KEY` | - | JWT signing key (required) |

## Run

### Backend

```bash
python main.py
```

Starts the FastAPI server on `http://0.0.0.0:8000` with auto-reload.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Starts the Vite dev server (default: `http://localhost:5173`).

## CORS

The backend allows all origins (`*`), methods, and headers for development. Restrict `allow_origins` in [main.py](main.py#L10-L16) for production.

## Request/Response Logging

`ApiIOMiddleware` logs method, path, status code, duration, and request/response bodies for every request.

**Skipped by default:** `/docs`, `/redoc`, `/openapi.json`, `/docs/oauth2-redirect`, `/favicon.ico`, and `OPTIONS` requests.

**Logs:** Written to `logs/YYYY-MM-DD.log` (one file per day, auto-created).

**Config options** (in [main.py](main.py#L11)):

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `skip_paths` | `set[str]` | docs/openapi/favicon paths | Paths to exclude from logging |
| `skip_html` | `bool` | `True` | Skip logging HTML responses (e.g. Swagger UI) |

Binary request/response bodies are logged as `<N bytes binary>` instead of raw content.

## API Docs

http://127.0.0.1:8000/docs

All endpoints (except `/auth/*`) require a valid JWT token in the `Authorization: Bearer <token>` header.

## Endpoints

### Auth

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | /auth/token | Login and get JWT token (rejects inactive accounts) | No |
| POST | /auth/hashpwd | Hash a password with bcrypt | No |

### Users

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /users/ | List all users |
| GET | /users/{user_id} | Get user by ID |
| POST | /users/ | Create user |
| PUT | /users/{user_id} | Update user |
| DELETE | /users/{user_id} | Delete user |

### Devices

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /devices/ | List all devices (optional `?user_account=` filter by role) |
| GET | /devices/{device_id} | Get device by ID |
| POST | /devices/ | Create device |
| PUT | /devices/{device_id} | Update device |
| DELETE | /devices/{device_id} | Delete device |

### Roles

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /roles/ | List all roles (with associated devices) |
| GET | /roles/{role_id} | Get role by ID |
| POST | /roles/ | Create role with device associations |
| PUT | /roles/{role_id} | Update role and device associations |
| DELETE | /roles/{role_id} | Delete role |

## Models

### User

| Field | Type | Description |
|-------|------|-------------|
| Id | Integer | Primary key |
| Account | String(45) | Unique username |
| Name | String(45) | Display name |
| Email | String(45) | Email address |
| Pwd | String(200) | Password hash |
| IsActive | Boolean | Active status |
| RoleId | Integer | Role identifier |
| CreatedDate | DateTime | Creation timestamp |
| UpdatedDate | DateTime | Last update timestamp |

### Device

| Field | Type | Description |
|-------|------|-------------|
| Id | Integer | Primary key |
| Code | String(50) | Unique device code |
| Name | String(50) | Device name |
| DeviceType | String(20) | Device type |
| Params | String(200) | Device parameters |
| Lat | Decimal(9,6) | Latitude |
| Lng | Decimal(9,6) | Longitude |
| IsActive | Boolean | Active status |
| Status | String(20) | Device status |
| CreatedDate | DateTime | Creation timestamp |
| UpdatedDate | DateTime | Last update timestamp |

### Role

| Field | Type | Description |
|-------|------|-------------|
| Id | Integer | Primary key |
| Name | String(50) | Role name |
| Devices | Relationship | Associated devices (many-to-many via `roledevices`) |
| CreatedDate | DateTime | Creation timestamp |
| UpdatedDate | DateTime | Last update timestamp |

### RoleDevice (Association Table)

| Field | Type | Description |
|-------|------|-------------|
| Id | Integer | Primary key |
| RoleId | Integer | Foreign key → `roles.Id` |
| DeviceId | Integer | Foreign key → `devices.Id` |

## Authentication

1. Obtain a JWT token via `POST /auth/token` with `account` and `password`
2. Use the token in the `Authorization: Bearer <token>` header for all protected endpoints
3. Tokens expire after 60 minutes
4. Inactive accounts are rejected at login

### Password Security

Passwords are automatically hashed with bcrypt via `security.get_password_hash()` before being stored to the database. This applies to both user creation and updates.

## Frontend

The [frontend/](frontend/) directory contains a React 19 + Vite 8 application with:

- **React Router 7** — client-side routing
- **Bootstrap 5** — UI components
- **Axios** — HTTP client for API calls

### Axios Configuration

The app uses a centralized Axios instance ([frontend/src/axios.js](frontend/src/axios.js)) with a response interceptor that:

- Catches **401 Unauthorized** responses
- Clears stored `token` and `account` from `localStorage`
- Redirects to the login page (`/`)
- Skips the redirect for login requests (`/auth/token`)

### Pages

| Page | Description |
|------|-------------|
| Login | Authentication form, stores JWT token |
| Home | Dashboard / landing page |
| Users | User management (list, create, edit, delete) with role assignment |
| Devices | Device management (list, create, edit, delete) with live stream & map views |
| Roles | Role management with device associations (multi-select) |

### Configuration

The frontend uses a `configContext` for app-wide settings. See [frontend/src/configContext.jsx](frontend/src/configContext.jsx).

See [frontend/README.md](frontend/README.md) for Vite/React setup details.
