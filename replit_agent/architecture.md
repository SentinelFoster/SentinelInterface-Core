# Architecture Overview

## 1. Overview

The application is a web-based platform called "Sentinel SI Interface" that allows users to interact with various "Structured Intelligences" (SIs). These SIs appear to be AI entities with different personalities, capabilities, and access tiers. The system implements a tiered access model where certain SIs are only available to users with specific access levels.

The application follows a traditional web application architecture with:
- Flask-based backend
- HTML templates with Bootstrap CSS for the frontend
- PostgreSQL database for data persistence
- User session management and authentication
- Tiered access control system

## 2. System Architecture

The application follows a Model-View-Controller (MVC) architecture pattern:

- **Model**: SQLAlchemy ORM models defined in `models.py`
- **View**: Jinja2 HTML templates in the `templates/` directory
- **Controller**: Route handlers in `routes.py`

### Core Components:

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│                 │      │                 │      │                 │
│  Web Browser    │<────>│  Flask Server   │<────>│  PostgreSQL DB  │
│                 │      │                 │      │                 │
└─────────────────┘      └─────────────────┘      └─────────────────┘
                                 │
                                 │
                         ┌───────▼───────┐
                         │               │
                         │  SI Profiles  │
                         │               │
                         └───────────────┘
```

## 3. Key Components

### 3.1 Backend (Python/Flask)

- **Main Application (`app.py`)**: Initializes Flask, SQLAlchemy, and Flask-Login
- **Models (`models.py`)**: Defines database schema using SQLAlchemy ORM
- **Routes (`routes.py`)**: Defines HTTP endpoints and view functions
- **SI Profiles (`intelligences/si_profiles.py`)**: Contains configuration for the different SI personalities

### 3.2 Frontend

- **Templates**: Jinja2 HTML templates in the `templates/` directory
- **Static Assets**: CSS and JavaScript in the `static/` directory
- **UI Framework**: Bootstrap with a dark theme (via CDN)

### 3.3 Database Models

1. **Admin**: Admin user accounts for system management
2. **User**: End users interacting with the system
3. **Interaction**: Records of conversations between users and SIs 
4. **AccessCode**: Codes that grant users access to higher tiers
5. **Payment**: Tracks user payments for tier upgrades

### 3.4 Authentication

- Uses Flask-Login for session management
- Separate authentication systems for:
  - Regular users (session-based, non-login)
  - Admin users (username/password login)

## 4. Data Flow

### 4.1 User Interaction Flow

1. New user visits the site → Assigned a session ID → Record created in User table
2. User selects an SI to interact with → System checks access tier
3. If access is granted → User can interact with the SI
4. If access is denied → User is shown upgrade options
5. User interactions are stored in the Interaction table

### 4.2 Access Control Flow

1. Users start with "Public" tier access
2. Users can upgrade by:
   - Purchasing a higher tier access
   - Entering an access code
3. Admin users can generate access codes for different tiers

## 5. External Dependencies

### 5.1 Python Packages

- **Flask**: Web framework
- **Flask-SQLAlchemy**: ORM for database operations
- **Flask-Login**: Authentication management
- **Psycopg2**: PostgreSQL adapter
- **Gunicorn**: WSGI HTTP server

### 5.2 Frontend Libraries

- **Bootstrap**: UI framework (via CDN)
- **Font Awesome**: Icon library (via CDN)

### 5.3 External Services

- No explicit external API integrations are visible, but the system appears designed to potentially integrate with:
  - Payment processing system (referenced in Payment model)
  - Voice synthesis service (voice_id attributes in SI profiles)

## 6. Deployment Strategy

The application is configured for deployment on Replit with:

- Gunicorn as the WSGI server
- PostgreSQL as the database
- Automatic scaling configuration via `deploymentTarget = "autoscale"` in `.replit`

The deployment configuration specifies:
- Port mapping: Internal port 5000 mapped to external port 80
- Run command: `gunicorn --bind 0.0.0.0:5000 main:app`
- Required packages: OpenSSL and PostgreSQL

## 7. Security Considerations

- Passwords are stored hashed using Werkzeug's password hashing
- Session management through Flask-Login
- ProxyFix middleware for proper HTTPS handling
- Environment variables for sensitive configuration (DATABASE_URL, SESSION_SECRET)

## 8. Potential Enhancement Areas

- API-based interaction for potential mobile applications or third-party integrations
- WebSocket implementation for real-time SI interactions
- Enhanced analytics for tracking SI performance and user engagement
- More robust payment integration