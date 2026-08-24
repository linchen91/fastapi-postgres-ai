# FastAPI + MySQL

FastAPI REST API with MySQL database using SQLAlchemy ORM, featuring JWT authentication.

## Project Structure

```
├── main.py                # App entry point
├── database.py            # DB connection & session
├── core/
│   └── security.py        # JWT auth & password hashing
├── models/
│   ├── user.py            # SQLAlchemy User model
│   ├── device.py          # SQLAlchemy Device model
│   ├── role.py            # SQLAlchemy Role model
│   └── roledevice.py      # Many-to-many relationship table
├── schemas/
│   ├── user.py            # Pydantic User schemas
│   ├── device.py          # Pydantic Device schemas
│   └── role.py            # Pydantic Role schemas
├── crud/
│   ├── user.py            # User CRUD operations
│   ├── device.py          # Device CRUD operations
│   └── role.py            # Role CRUD operations
├── routers/
│   ├── auth.py            # Auth endpoints (login, hash password)
│   ├── user.py            # User API endpoints
│   ├── device.py          # Device API endpoints
│   └── role.py            # Role API endpoints
├── frontend/              # React + Vite frontend
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

```bash
python main.py
```

## API Docs

http://127.0.0.1:8000/docs

All endpoints (except `/auth/*`) require a valid JWT token in the `Authorization: Bearer <token>` header.

## Endpoints

### Auth

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | /auth/token | Login and get JWT token | No |
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
| GET | /devices/ | List all devices |
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
| Devices | Relationship | Associated devices (many-to-many) |
| CreatedDate | DateTime | Creation timestamp |
| UpdatedDate | DateTime | Last update timestamp |

## Authentication

1. Obtain a JWT token via `POST /auth/token` with `account` and `password`
2. Use the token in the `Authorization: Bearer <token>` header for all protected endpoints
3. Tokens expire after 60 minutes

## Frontend

The `frontend/` directory contains a React + Vite application. See [frontend/README.md](frontend/README.md) for setup instructions.
