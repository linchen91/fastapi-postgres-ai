# FastAPI + MySQL

FastAPI REST API with MySQL database using SQLAlchemy ORM.

## Project Structure

```
├── main.py            # App entry point
├── database.py        # DB connection & session
├── models/
│   └── user.py        # SQLAlchemy User model
├── schemas/
│   └── user.py        # Pydantic request/response schemas
├── crud/
│   └── user.py        # Database CRUD operations
├── routers/
│   └── user.py        # API endpoints
├── service.py         # Test service
└── test.py            # PyMySQL test
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MYSQL_USER` | dzuser | MySQL username |
| `MYSQL_PASSWORD` | L@12345678 | MySQL password |
| `MYSQL_HOST` | localhost | MySQL host |
| `MYSQL_PORT` | 3307 | MySQL port |
| `MYSQL_DB` | dzservice | Database name |

## Run

```bash
python main.py
```

## API Docs

http://127.0.0.1:8000/docs

## Endpoints

### Users

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /users/ | List all users |
| GET | /users/{user_id} | Get user by ID |
| POST | /users/ | Create user |
| PUT | /users/{user_id} | Update user |
| DELETE | /users/{user_id} | Delete user |

## User Model

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
