load('ext://dotenv', 'dotenv')
load('ext://uibutton', 'cmd_button', 'text_input', 'location')

dotenv()
docker_compose('./docker-compose.yml')

# --- Backend ---
docker_build(
    'monthly-budget-api',
    context='./backend',
    only=['app/', 'alembic/', 'pyproject.toml', 'uv.lock', 'alembic.ini', 'entrypoint.sh'],
    live_update=[
        fall_back_on(['./backend/pyproject.toml', './backend/uv.lock']),
        sync('./backend/app', '/app/app'),
        sync('./backend/alembic', '/app/alembic'),
        restart_container(),
    ],
)

# --- Frontend ---
docker_build(
    'monthly-budget-frontend',
    context='./frontend',
    only=['src/', 'public/', 'index.html', 'package.json', 'package-lock.json',
          'vite.config.ts', 'tsconfig.json', 'tsconfig.app.json', 'tsconfig.node.json',
          'eslint.config.js'],
    live_update=[
        fall_back_on(['./frontend/package.json', './frontend/package-lock.json']),
        sync('./frontend/src', '/app/src'),
        sync('./frontend/public', '/app/public'),
        sync('./frontend/index.html', '/app/index.html'),
    ],
)

# --- Resource configuration ---
dc_resource('db',       labels=['infra'])
dc_resource('redis',    labels=['infra'])
dc_resource('api',      labels=['backend'],  resource_deps=['db', 'redis'],
            links=[link('http://localhost:8000/docs', 'API Docs')])
dc_resource('frontend', labels=['frontend'],
            links=[link('http://localhost:5173', 'App')])

# --- UI buttons ---
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

# --- Settings ---
update_settings(max_parallel_updates=5)
