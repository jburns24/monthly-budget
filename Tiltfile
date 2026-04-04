load('ext://dotenv', 'dotenv')
load('ext://uibutton', 'cmd_button', 'text_input', 'location')

dotenv()

# Cleanup stale containers on tilt down
if config.tilt_subcommand == 'down':
    local('docker rm -f monthly-budget-db 2>/dev/null || true')
    local('docker rm -f monthly-budget-redis 2>/dev/null || true')
    local('docker rm -f monthly-budget-api 2>/dev/null || true')
    local('docker rm -f monthly-budget-frontend 2>/dev/null || true')

# Ensure shared dev network exists
local('docker network create monthly-budget-net 2>/dev/null || true')

# --- Read env vars ---
pg_user = os.getenv('POSTGRES_USER', 'monthly_budget')
pg_pass = os.getenv('POSTGRES_PASSWORD', 'changeme_postgres_password')
pg_db   = os.getenv('POSTGRES_DB', 'monthly_budget')
redis_pass = os.getenv('REDIS_PASSWORD', 'changeme_redis_password')

# Host-accessible URLs (for db:migrate running on host)
database_url = 'postgresql+asyncpg://%s:%s@localhost:5432/%s' % (pg_user, pg_pass, pg_db)  # pragma: allowlist secret
redis_url    = 'redis://:%s@localhost:6379/0' % redis_pass

# Container-to-container URLs (for api container on monthly-budget-net)
container_database_url = 'postgresql+asyncpg://%s:%s@monthly-budget-db:5432/%s' % (pg_user, pg_pass, pg_db)  # pragma: allowlist secret
container_redis_url    = 'redis://:%s@monthly-budget-redis:6379/0' % redis_pass

# ============================================================
# Infrastructure (Docker containers via local_resource)
# ============================================================

local_resource(
    'db',
    cmd='docker rm -f monthly-budget-db 2>/dev/null || true',
    serve_cmd=' '.join([
        'docker run --rm',
        '--name monthly-budget-db',
        '--network monthly-budget-net',
        '-p 5432:5432',
        '-e POSTGRES_USER=%s' % pg_user,
        '-e POSTGRES_PASSWORD=%s' % pg_pass,
        '-e POSTGRES_DB=%s' % pg_db,
        '-v mb_pg_data:/var/lib/postgresql/data',
        'postgres:16-alpine',
    ]),
    readiness_probe=probe(
        exec=exec_action(['docker', 'exec', 'monthly-budget-db', 'pg_isready', '-U', pg_user, '-d', pg_db]),
        period_secs=5,
        timeout_secs=5,
        failure_threshold=10,
    ),
    labels=['infra'],
)

local_resource(
    'redis',
    cmd='docker rm -f monthly-budget-redis 2>/dev/null || true',
    serve_cmd=' '.join([
        'docker run --rm',
        '--name monthly-budget-redis',
        '--network monthly-budget-net',
        '-p 6379:6379',
        'redis:7-alpine',
        'redis-server',
        '--requirepass %s' % redis_pass,
        '--maxmemory 128mb',
        '--maxmemory-policy allkeys-lru',
    ]),
    readiness_probe=probe(
        tcp_socket=tcp_socket_action(6379),
        period_secs=5,
        timeout_secs=5,
        failure_threshold=10,
    ),
    labels=['infra'],
)

# ============================================================
# Database migrations (runs once after db is ready)
# ============================================================

local_resource(
    'db:migrate',
    cmd='cd backend && uv run alembic upgrade head',
    env={
        'DATABASE_URL': database_url,
    },
    resource_deps=['db'],
    trigger_mode=TRIGGER_MODE_MANUAL,
    auto_init=True,
    labels=['backend'],
)

# ============================================================
# Application services (Docker containers with bind-mounted source)
# ============================================================

api_env = {
    'DATABASE_URL': container_database_url,
    'REDIS_URL': container_redis_url,
    'SECRET_KEY': os.getenv('SECRET_KEY', ''),
    'JWT_SECRET': os.getenv('JWT_SECRET', ''),
    'GOOGLE_CLIENT_ID': os.getenv('GOOGLE_CLIENT_ID', ''),
    'GOOGLE_CLIENT_SECRET': os.getenv('GOOGLE_CLIENT_SECRET', ''),
    'ANTHROPIC_API_KEY': os.getenv('ANTHROPIC_API_KEY', ''),
    'ENVIRONMENT': os.getenv('ENVIRONMENT', 'development'),
    'LOG_LEVEL': os.getenv('LOG_LEVEL', 'INFO'),
}

local_resource(
    'api',
    cmd=' && '.join([
        'docker rm -f monthly-budget-api 2>/dev/null || true',
        'docker build --target dev -t monthly-budget-api backend',
    ]),
    serve_cmd=' '.join([
        'docker run --rm',
        '--name monthly-budget-api',
        '--network monthly-budget-net',
        '-p 8000:8000',
        '-v $(pwd)/backend/app:/app/app',
        '-v $(pwd)/backend/alembic:/app/alembic',
        '-v $(pwd)/backend/alembic.ini:/app/alembic.ini',
    ] + ['-e %s="%s"' % (k, v) for k, v in api_env.items()] + [
        'monthly-budget-api',
    ]),
    deps=['backend/pyproject.toml', 'backend/uv.lock', 'backend/Dockerfile'],
    resource_deps=['db:migrate'],
    readiness_probe=probe(
        http_get=http_get_action(8000, path='/api/health'),
        period_secs=5,
        timeout_secs=5,
        failure_threshold=12,
    ),
    labels=['backend'],
    links=[link('http://localhost:8000/docs', 'API Docs')],
)

local_resource(
    'frontend',
    cmd=' && '.join([
        'docker rm -f monthly-budget-frontend 2>/dev/null || true',
        'docker build --target dev -t monthly-budget-frontend frontend',
    ]),
    serve_cmd=' '.join([
        'docker run --rm',
        '--name monthly-budget-frontend',
        '--network monthly-budget-net',
        '-p 5173:5173',
        '-v $(pwd)/frontend/src:/app/src',
        '-v $(pwd)/frontend/public:/app/public',
        '-v $(pwd)/frontend/index.html:/app/index.html',
        '-v $(pwd)/frontend/vite.config.ts:/app/vite.config.ts',
        '-e VITE_API_BASE_URL=%s' % os.getenv('VITE_API_BASE_URL', 'http://localhost:8000'),
        '-e VITE_GOOGLE_CLIENT_ID=%s' % os.getenv('GOOGLE_CLIENT_ID', ''),
        '-e VITE_DEV_PROXY_TARGET=http://monthly-budget-api:8000',
        'monthly-budget-frontend',
    ]),
    deps=['frontend/package.json', 'frontend/Dockerfile'],
    readiness_probe=probe(
        http_get=http_get_action(5173, path='/'),
        period_secs=5,
        timeout_secs=5,
        failure_threshold=12,
    ),
    labels=['frontend'],
    links=[link('http://localhost:5173', 'App')],
)

# ============================================================
# UI buttons
# ============================================================

cmd_button('api:migrate',
           argv=['task', 'be:db:migrate'],
           resource='api',
           icon_name='database',
           text='Run Migrations')

cmd_button('api:test',
           argv=['task', 'be:test'],
           resource='api',
           icon_name='bug_report',
           text='Run Backend Tests')

cmd_button('frontend:test',
           argv=['task', 'fe:test'],
           resource='frontend',
           icon_name='bug_report',
           text='Run Frontend Tests')

cmd_button('nav:lint',
           argv=['task', 'lint'],
           location=location.NAV,
           icon_name='check_circle',
           text='Lint All')

# ============================================================
# Settings
# ============================================================

update_settings(max_parallel_updates=5)
