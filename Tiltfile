# Corporate Context Development Environment Tiltfile

load("ext://color", "color")
load("ext://restart_process", "docker_build_with_restart")

# Configuration
allow_k8s_contexts("docker-desktop")

# Check if GRAPEVINE_LOCAL_REMOTE_DATA is set - if so, don't start ingest-server and steward
use_remote_data = not os.getenv("GRAPEVINE_LOCAL_REMOTE_DATA") == None

# When NOT in local_remote_data mode, unset AWS credentials to avoid conflicts
if not use_remote_data:
    # Unset AWS environment variables that might interfere with local development
    os.unsetenv("AWS_PROFILE")
    os.unsetenv("AWS_CREDENTIAL_EXPIRATION")
    os.unsetenv("AWS_SESSION_TOKEN")
    print(color.yellow("📝 Cleared AWS credentials (AWS_PROFILE, AWS_CREDENTIAL_EXPIRATION, AWS_SESSION_TOKEN) for local data mode"))

# Define colors for better visibility
print(color.cyan("🚀 Starting Corporate Context Development Environment"))
print(color.cyan("=================================================="))

# Docker Compose services for backing services
# Only start OpenSearch and related services, not the api/ingest servers from docker-compose
# Use the appropriate profile based on GRAPEVINE_LOCAL_REMOTE_DATA
if use_remote_data:
    docker_compose("./docker-compose.yml", profiles=["remote-data"])
else:
    docker_compose("./docker-compose.yml", profiles=["local-data"])

# Apply labels to Docker Compose services based on mode
if use_remote_data:
    # Remote data mode: only aws-es-proxy
    dc_resource(
        "aws-es-proxy",
        labels=["10_infrastructure"],
        links=[link("http://localhost:9210/_dashboards", "AWS OpenSearch Proxy Dashboard")],
    )
else:
    # Local data mode: postgres, opensearch, opensearch-dashboards, redis, localstack
    dc_resource("postgres", labels=["10_infrastructure"])
    dc_resource("opensearch", labels=["10_infrastructure"])
    dc_resource("opensearch-dashboards", labels=["10_infrastructure"])
    dc_resource("redis", labels=["10_infrastructure"])
    dc_resource("localstack", labels=["10_infrastructure"])

# MCP Server (Python)
mcp_deps = [] if use_remote_data else ["postgres", "opensearch", "redis", "localstack-init"]
local_resource(
    "mcp-server",
    serve_cmd="uv run python -m src.mcp.server",
    serve_dir=".",
    serve_env={
        "PYTHONUNBUFFERED": "1",
        "REDIS_PRIMARY_ENDPOINT": "redis://localhost:6379",
    },
    labels=["00_python"],
    resource_deps=mcp_deps,
    readiness_probe=probe(
        http_get=http_get_action(port=8000, path="/health/ready"),
        period_secs=10,
        failure_threshold=3,
    ),
    links=[
        link("http://localhost:8000", "MCP Server"),
    ],
)

# Ingest Gatekeeper (Python) - only start if not using remote data
if not use_remote_data:
    local_resource(
        "ingest-gatekeeper",
        serve_cmd="uv run uvicorn src.ingest.gatekeeper.main:app --host 0.0.0.0 --port 8001 --reload",
        serve_dir=".",
        serve_env={"PYTHONUNBUFFERED": "1"},
        labels=["00_python"],
        resource_deps=["postgres", "opensearch", "redis", "localstack-init"],
        readiness_probe=probe(
            http_get=http_get_action(port=8001, path="/health"), period_secs=10, failure_threshold=3
        ),
        links=[
            link("http://localhost:8001", "Ingest Gatekeeper"),
        ],
    )

# Index Workers (Python) - only start if not using remote data
if not use_remote_data:
    index_workers = [
        {"name": "index-worker", "port": 8081, "display_name": "Index Worker"},
        # Uncomment / duplicate if you want to run more workers
        # {"name": "index-worker-2", "port": 8083, "display_name": "Index Worker 2"},
    ]

    for worker in index_workers:
        serve_env = {
            "PYTHONUNBUFFERED": "1",
            "INDEX_HTTP_PORT": str(worker["port"]),
        }

        local_resource(
            worker["name"],
            serve_cmd="uv run python -m src.jobs.index_job_worker",
            serve_dir=".",
            serve_env=serve_env,
            labels=["00_python"],
            resource_deps=["postgres", "opensearch", "redis", "localstack-init"],
            readiness_probe=probe(
                http_get=http_get_action(port=worker["port"], path="/health/live"),
                period_secs=10,
                failure_threshold=3,
            ),
            links=[
                link("http://localhost:{}".format(worker["port"]), worker["display_name"]),
            ],
        )

# Ingest Workers (Python) - only start if not using remote data
if not use_remote_data:
    ingest_workers = [
        {"name": "ingest-worker", "port": 8080, "display_name": "Ingest Worker"},
        # Uncomment / duplicate if you want to run more workers
        # {"name": "ingest-worker-2", "port": 8082, "display_name": "Ingest Worker 2"},
    ]

    for worker in ingest_workers:
        serve_env = {
            "PYTHONUNBUFFERED": "1",
            "INGEST_HTTP_PORT": str(worker["port"]),
        }

        local_resource(
            worker["name"],
            serve_cmd="uv run python -m src.jobs.ingest_job_worker",
            serve_dir=".",
            serve_env=serve_env,
            labels=["00_python"],
            resource_deps=["postgres", "opensearch", "redis", "localstack-init"],
            readiness_probe=probe(
                http_get=http_get_action(port=worker["port"], path="/health/live"),
                period_secs=10,
                failure_threshold=3,
            ),
            links=[
                link("http://localhost:{}".format(worker["port"]), worker["display_name"]),
            ],
        )

# Cron Worker (Python) - only start if not using remote data
if not use_remote_data:
    local_resource(
        "cron-worker",
        serve_cmd="uv run python -m src.jobs.cron_job_worker",
        serve_dir=".",
        labels=["00_python"],
        resource_deps=["postgres", "redis", "localstack-init"],
        readiness_probe=probe(
            http_get=http_get_action(port=8090, path="/health/live"),
            period_secs=10,
            failure_threshold=3,
        ),
        links=[
            link("http://localhost:8090", "Cron Worker"),
        ],
    )


# Steward Service (Python) - Tenant Provisioner - only start if not using remote data
if not use_remote_data:
    local_resource(
        "steward",
        serve_cmd="uv run python -m src.steward.tenant_provisioner",
        serve_dir=".",
        serve_env={"PYTHONUNBUFFERED": "1"},
        labels=["00_python"],
        resource_deps=["postgres", "redis", "localstack-init"],
    )

# Admin Backend (Node.js)
admin_backend_deps = ["build:typescript"]
if not use_remote_data:
    admin_backend_deps.extend(["postgres", "redis", "localstack-init"])

local_resource(
    "admin-backend",
    serve_cmd="PORT=5002 yarn nx run admin-backend:serve:dev",
    serve_dir="js-services",
    serve_env={"PORT": "5002", "NODE_ENV": "development"},
    labels=["01_typescript"],
    resource_deps=admin_backend_deps,
    readiness_probe=probe(
        http_get=http_get_action(port=5002, path="/api/health/ready"),
        period_secs=10,
        failure_threshold=3,
    ),
    links=[
        link("http://localhost:5002", "Admin Backend API"),
    ],
)


# Admin Frontend (Vite React)
local_resource(
    "admin-frontend",
    serve_cmd="yarn nx run admin-frontend:serve:dev",
    serve_dir="js-services",
    serve_env={"NODE_ENV": "development"},
    labels=["01_typescript"],
    resource_deps=["build:typescript", "admin-backend"],
    readiness_probe=probe(
        http_get=http_get_action(port=5173, path="/"), period_secs=10, failure_threshold=3
    ),
    links=[link("http://localhost:5173", "Admin UI")],
)

# Slack bot - only start if not using remote data
if not use_remote_data:
    local_resource(
        "slack-bot",
        serve_cmd="PORT=8003 yarn nx run slack-bot:serve:dev",
        serve_dir="js-services",
        serve_env={"NODE_ENV": "development"},
        labels=["01_typescript"],
        resource_deps=["build:typescript", "postgres", "redis", "localstack-init"],
        readiness_probe=probe(
            http_get=http_get_action(port=8003, path="/health/ready"),
            period_secs=10,
            failure_threshold=3,
        ),
    )

# Rebuild shared libraries once and then on changes.
local_resource(
    "build:typescript",
    cmd="yarn nx run-many --projects=frontend-common,backend-common,shared-common,exponent-core -t build",
    dir="js-services",
    serve_cmd="yarn nx watch --projects=frontend-common,backend-common,shared-common,exponent-core -- nx run \\$NX_PROJECT_NAME:build",
    serve_dir="js-services",
    labels=["01_typescript"],
)

# Port forwards for easy access
# These are automatically handled by local_resource links above

# Additional tooling commands
local_resource(
    "mcp-inspector",
    serve_cmd="npx @modelcontextprotocol/inspector",
    auto_init=False,
    labels=["20_tools"],
    readiness_probe=probe(
        http_get=http_get_action(port=6274, path="/"), period_secs=10, failure_threshold=3
    ),
)

# LocalStack UI Backend (Node.js) - only available in local mode
if not use_remote_data:
    local_resource(
        "localstack-ui-backend",
        serve_cmd="yarn nx run localstack-ui-backend:serve:dev",
        serve_dir="js-services",
        serve_env={"NODE_ENV": "development"},
        auto_init=False,
        labels=["20_tools"],
        resource_deps=["localstack-init"],
        readiness_probe=probe(
            http_get=http_get_action(port=3001, path="/health"), period_secs=10, failure_threshold=3
        ),
        links=[
            link("http://localhost:3001", "LocalStack UI Backend API"),
        ],
    )

# LocalStack UI Frontend (Vite React) - only available in local mode
if not use_remote_data:
    local_resource(
        "localstack-ui-frontend",
        serve_cmd="yarn nx run localstack-ui-frontend:serve:dev",
        serve_dir="js-services",
        serve_env={"NODE_ENV": "development"},
        auto_init=False,
        labels=["20_tools"],
        resource_deps=["localstack-ui-backend"],
        readiness_probe=probe(
            http_get=http_get_action(port=5174, path="/"), period_secs=10, failure_threshold=3
        ),
        links=[link("http://localhost:5174", "LocalStack UI")],
    )

# Credentials Check - runs in both local and local_remote_data modes
local_resource(
    "check-credentials",
    cmd="uv run python scripts/check_credentials.py",
    dir=".",
    labels=["10_infrastructure"],
    auto_init=True,
    trigger_mode=TRIGGER_MODE_MANUAL,
)

# LocalStack initialization - runs after LocalStack is healthy (only in local mode)
if not use_remote_data:
    local_resource(
        "localstack-init",
        cmd="uv run python scripts/localstack_init.py",
        dir=".",
        labels=["10_infrastructure"],
        resource_deps=["localstack"],
        auto_init=True,
        trigger_mode=TRIGGER_MODE_AUTO,
    )

# Status dashboard links
print("")
print(color.green("✅ Services Starting:"))
print("  🚀 MCP Server: " + color.blue("http://localhost:8000"))
if not use_remote_data:
    print("  🌐 Ingest Gatekeeper: " + color.blue("http://localhost:8001"))
    # Index Workers
    index_workers = [
        {"port": 8081, "display_name": "Index Worker"},
        {"port": 8082, "display_name": "Index Worker 2"},
    ]
    for worker in index_workers:
        print(
            "  ⚙️  {}: ".format(worker["display_name"])
            + color.blue("http://localhost:{}".format(worker["port"]))
        )

    # Ingest Workers
    ingest_workers = [
        {"port": 8080, "display_name": "Ingest Worker"},
        {"port": 8083, "display_name": "Ingest Worker 2"},
    ]
    for worker in ingest_workers:
        print(
            "  🔄 {}: ".format(worker["display_name"])
            + color.blue("http://localhost:{}".format(worker["port"]))
        )
    print("  🐘 PostgreSQL: " + color.blue("localhost:5422"))
    print("  🔍 OpenSearch: " + color.blue("http://localhost:9200"))
    print("  📊 OpenSearch Dashboards: " + color.blue("http://localhost:5601"))
    print("  🗄️  Redis: " + color.blue("localhost:6379"))
else:
    print("  🌐 Ingest Gatekeeper: " + color.yellow("(disabled - using remote data)"))
    print("  ⚙️  Index Worker: " + color.yellow("(disabled - using remote data)"))
    print("  🔄 Ingest Worker: " + color.yellow("(disabled - using remote data)"))
    print("  🐘 PostgreSQL: " + color.yellow("(disabled - using remote data)"))
    print("  🔍 OpenSearch: " + color.yellow("(disabled - using remote data)"))
    print("  📊 OpenSearch Dashboards: " + color.yellow("(disabled - using remote data)"))
    print("  🗄️  Redis: " + color.yellow("(disabled - using remote data)"))
    print("  🔌 AWS OpenSearch Proxy: " + color.blue("http://localhost:9210/_dashboards"))

print("  🎨 Admin UI Frontend: " + color.blue("http://localhost:5173"))
print("  🔧 Admin UI Backend: " + color.blue("http://localhost:5002"))
if not use_remote_data:
    print("  ☁️  LocalStack (AWS): " + color.blue("http://localhost:4566"))
print("")
print(color.yellow("Developer Tools:"))
if not use_remote_data:
    print("  📖 Gatekeeper API Docs: " + color.blue("http://localhost:8001/docs"))
    print(
        '  🛠️  LocalStack UI: Run "localstack-ui-backend" and "localstack-ui-frontend" resources in Tilt UI'
    )
print('  🔍 MCP Inspector: Run "mcp-inspector" resource in Tilt UI')
print("")
print(color.cyan("=================================================="))
print(color.green("Access Tilt UI at: ") + color.blue("http://localhost:10350"))
