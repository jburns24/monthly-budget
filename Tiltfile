load('ext://dotenv', 'dotenv')
load('ext://uibutton', 'cmd_button', 'text_input', 'location')

# Loads the repo-root .env into Tilt's own process env (a missing file is just a
# warning). Kept for host-side subprocesses — `task be:test`, the cmd_buttons —
# but note what it no longer does: the in-cluster workloads read their config
# from manifests/overlays/dev/config/*.env via the generated ConfigMap/Secret,
# so editing .env does NOT change what the pods see. Change the overlay instead.
dotenv()

# ============================================================
# Cluster guardrails
# ============================================================
# Only ever deploy to the local k3d cluster. Without this a stray kubectl
# context would make `tilt up` apply dev manifests to whatever cluster is
# currently selected. (Tilt already treats any `k3d-*` context as local and
# therefore safe, which is exactly why the name has to be pinned here.)
if k8s_context() != 'k3d-monthly-budget':
    fail(
        'Tilt is pointed at kube context %r, but this Tiltfile only deploys to ' % k8s_context() +
        '"k3d-monthly-budget". Run `task up` (which creates the cluster and ' +
        'switches context) instead of `tilt up` directly.'
    )

# ============================================================
# Image registry
# ============================================================
# The k3d-managed registry declared in k3d.yaml is reachable under two
# different names AND two different ports, and both have to be spelled out:
#   * localhost:5111               <- Tilt (on the host) pushes here
#   * monthly-budget-registry:5000 <- containerd (in-cluster) pulls here
#
# Three things bite here, all verified against this cluster:
#   1. The registry container is named exactly as in k3d.yaml. k3d does NOT
#      prefix it with "k3d-" the way it prefixes node names.
#   2. hostPort 5111 is a host-side publish only. Inside the docker network the
#      registry listens on 5000 — connecting to 5111 from a node is refused.
#   3. k3s writes /etc/rancher/k3s/registries.yaml with plain-HTTP mirrors for
#      this host, which is what lets an insecure registry work at all.
# Getting this wrong shows up as ImagePullBackOff, usually "connection refused"
# against 127.0.0.1 because the node resolves localhost to itself.
default_registry(
    'localhost:5111',
    host_from_cluster='monthly-budget-registry:5000',
)

# ============================================================
# Manifests
# ============================================================
k8s_yaml(kustomize('manifests/overlays/dev'))

# ============================================================
# Images
# ============================================================

docker_build(
    'monthly-budget-backend',
    context='backend',
    dockerfile='backend/Dockerfile',
    target='dev',
    # Anything outside this list can't trigger a rebuild, which keeps test
    # runs and cache dirs from churning the image.
    only=[
        'pyproject.toml',
        'uv.lock',
        'app',
        'alembic',
        'alembic.ini',
    ],
    live_update=[
        # A dependency change can't be patched in — rebuild the image.
        fall_back_on([
            'backend/pyproject.toml',
            'backend/uv.lock',
        ]),
        sync('backend/app', '/app/app'),
        sync('backend/alembic', '/app/alembic'),
        sync('backend/alembic.ini', '/app/alembic.ini'),
        # No restart_container() needed: the dev stage runs `uvicorn --reload`,
        # and WATCHFILES_FORCE_POLLING (set on the Deployment) makes it notice
        # files that Tilt extracted into the container's overlayfs.
    ],
)

docker_build(
    'monthly-budget-frontend',
    context='frontend',
    dockerfile='frontend/Dockerfile',
    target='dev',
    only=[
        'package.json',
        'package-lock.json',
        'index.html',
        'vite.config.ts',
        'tsconfig.json',
        'tsconfig.app.json',
        'tsconfig.node.json',
        'src',
        'public',
    ],
    live_update=[
        fall_back_on([
            'frontend/package.json',
            'frontend/package-lock.json',
        ]),
        sync('frontend/src', '/app/src'),
        sync('frontend/public', '/app/public'),
        sync('frontend/index.html', '/app/index.html'),
        # vite.config.ts is synced but Vite only reads it at boot, so a change
        # there needs a manual resource restart from the Tilt UI.
        sync('frontend/vite.config.ts', '/app/vite.config.ts'),
    ],
)

# ============================================================
# Workloads
# ============================================================
#
# Both roots depend on `cluster-config` (defined below). Tilt only orders
# applies along resource_deps edges, and with max_parallel_updates=5 all six
# resources would otherwise go out at once — so on a fresh cluster the
# workloads can reach the API server before the Namespace/ConfigMap/Secret/PVC
# they need. That surfaces as `namespaces "monthly-budget" not found` on the
# very first `task up` and then works on retry. Everything else inherits the
# ordering transitively (frontend -> backend -> backend-migrate -> postgres,
# backend -> redis), so these two edges are enough.

k8s_resource(
    'postgres',
    resource_deps=['cluster-config'],
    labels=['infra'],
)

k8s_resource(
    'redis',
    resource_deps=['cluster-config'],
    labels=['infra'],
)

# Alembic runs as a Job. Tilt deletes and recreates the Job on each apply,
# which is what makes an otherwise-immutable Job re-runnable here.
k8s_resource(
    'backend-migrate',
    resource_deps=['postgres'],
    labels=['backend'],
)

k8s_resource(
    'backend',
    port_forwards=['8000:8000'],
    resource_deps=['backend-migrate', 'redis'],
    labels=['backend'],
    links=[
        link('http://localhost:8080/docs', 'API Docs'),
        link('http://localhost:8080/api/health', 'Health'),
    ],
)

k8s_resource(
    'frontend',
    port_forwards=['5173:5173'],
    resource_deps=['backend'],
    labels=['frontend'],
    links=[link('http://localhost:8080', 'App')],
)

# Non-workload objects grouped so they don't each get their own row.
#
# Every entry has to name an object that kustomize actually renders, in
# `name:kind` form — Tilt hard-fails the Tiltfile on a fragment that matches
# nothing rather than warning. The ConfigMap/Secret names here are the
# *generator* names from manifests/overlays/dev/kustomization.yaml
# (`app-config` / `app-secrets`), NOT the `monthly-budget-` prefixed names an
# earlier draft used. Cross-check with:
#   kubectl kustomize manifests/overlays/dev | grep -E '^(kind|  name):'
# The Services (backend, frontend, postgres, postgres-headless, redis) are
# deliberately absent: Tilt attaches a Service to the workload its selector
# matches, so listing them here would steal them from those rows.
k8s_resource(
    new_name='cluster-config',
    objects=[
        'monthly-budget:namespace',
        'app-config:configmap',
        'app-secrets:secret',
        'monthly-budget:ingress',
        'backend-receipts:persistentvolumeclaim',
    ],
    labels=['infra'],
)

# ============================================================
# UI buttons
# ============================================================

# Deleting the Job is only half the job: nothing re-applies it on its own, so
# the row would just go empty. `tilt trigger` forces the re-apply, and it has to
# come after the delete because a completed Job's spec is immutable. Same pair
# of steps as `task db:reset`.
cmd_button('backend:migrate',
           argv=['sh', '-c',
                 'kubectl -n monthly-budget delete job backend-migrate --ignore-not-found && ' +
                 'tilt trigger backend-migrate'],
           resource='backend-migrate',
           icon_name='database',
           text='Re-run Migrations')

cmd_button('backend:test',
           argv=['task', 'be:test'],
           resource='backend',
           icon_name='bug_report',
           text='Run Backend Tests')

cmd_button('backend:shell',
           argv=['sh', '-c', 'kubectl -n monthly-budget exec -it deploy/backend -- bash'],
           resource='backend',
           icon_name='terminal',
           text='Shell')

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
