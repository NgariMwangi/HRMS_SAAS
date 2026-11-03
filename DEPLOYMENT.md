# Simple Docker setup

Install Docker Engine and the Docker Compose plugin on your server using the [official Docker guide](https://docs.docker.com/engine/install/). Upload this project, then run all commands below from its root directory.

## 1. Set your database URL

```sh
cp .env.example .env
nano .env
```

For the PostgreSQL database included in Docker Compose:

```dotenv
POSTGRES_USER=hrms
POSTGRES_PASSWORD=your_database_password
POSTGRES_DB=hrms
DATABASE_URL=postgresql+asyncpg://hrms:your_database_password@postgres:5432/hrms
```

Use a URL-safe database password, or URL-encode special characters in the URL. `postgres` is the Docker service name; `localhost` inside the backend container means the backend container itself.

If using a database that already exists elsewhere, set `DATABASE_URL` to that database instead. The included PostgreSQL service can remain unused. Choose a database intended for this app: startup automatically applies migrations and seeds reference data and the initial platform administrator.

Also set these values in `.env`:

```dotenv
HRMS_CENTRAL_HOSTS=localhost,127.0.0.1,::1,test,backend,YOUR_SERVER_IP
JWT_SECRET=your_long_random_secret
PLATFORM_ADMIN_EMAIL=you@example.com
PLATFORM_ADMIN_PASSWORD=your_admin_password
```

Replace `YOUR_SERVER_IP` with the address or hostname you will use in your browser. Keep `.env` for future restarts. Changing `POSTGRES_PASSWORD` later does not change the password of an already initialized database; changing the admin environment password does not reset an existing admin account.

## 2. Start everything

```sh
docker compose up -d --build
docker compose ps
```

The frontend, backend, database, cache and reminder worker start together. The backend automatically runs database migrations. PostgreSQL data persists in its Docker volume.

Allow TCP port **5173** in the server firewall, then open:

- App: `http://YOUR_SERVER_IP:5173`
- Platform admin: `http://YOUR_SERVER_IP:5173/admin`
- Health check: `http://YOUR_SERVER_IP:5173/health`

The frontend forwards API requests to the backend automatically. Database/cache ports are bound to localhost. This is the simple HTTP testing setup; the existing `docker-compose.domains.yml` remains available later for HTTPS/domain hosting.

## Useful commands

```sh
docker compose logs --tail 100 backend frontend
docker compose up -d --build    # Apply source updates
docker compose stop            # Stop without deleting data
docker compose start           # Start again
```

Do not add `-v` to `docker compose down` unless you intend to delete the database volume. The initial platform-admin login uses the credentials from `.env`; register a separate tenant workspace from the app's home page to test HR features.
