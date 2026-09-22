# Offline plan assertions: no cluster required (dummy kubeconfig supplied by scripts/test-terraform.sh).

run "plan_offline" {
  command = plan

  variables {
    config_path           = "/tmp/fastapi-postgres-ai-dummy-kubeconfig"
    namespace             = "fastapi-postgres"
    config_map_name       = "app-config"
    secret_name           = "app-secrets"
    postgres_user         = "postgres"
    postgres_password     = "test-password"
    postgres_db           = "dzservice"
    postgres_host         = "postgres"
    postgres_port         = "5432"
    postgres_image        = "postgres:16-alpine"
    secret_key            = "test-secret-key"
    openrouter_api_key    = "test-openrouter-key"
    openrouter_model      = "openrouter/free"
    openrouter_url        = "https://openrouter.ai/api/v1"
    tavily_api_key        = "test-tavily-key"
    api_image             = "fastapi-postgres-ai:latest"
    api_image_pull_policy = "Never"
    api_node_port         = null
  }

  assert {
    condition     = kubernetes_namespace.app.metadata[0].name == "fastapi-postgres"
    error_message = "namespace must be fastapi-postgres"
  }

  assert {
    condition     = kubernetes_config_map.app.data["POSTGRES_DB"] == "dzservice"
    error_message = "configmap POSTGRES_DB must be dzservice"
  }

  assert {
    condition     = kubernetes_config_map.app.data["POSTGRES_HOST"] == "postgres"
    error_message = "configmap POSTGRES_HOST must be postgres"
  }

  assert {
    condition = alltrue([
      contains(keys(kubernetes_secret.app.data), "POSTGRES_USER"),
      contains(keys(kubernetes_secret.app.data), "POSTGRES_PASSWORD"),
      contains(keys(kubernetes_secret.app.data), "SECRET_KEY"),
      contains(keys(kubernetes_secret.app.data), "OPENROUTER_API_KEY"),
      contains(keys(kubernetes_secret.app.data), "OPENROUTER_URL"),
      contains(keys(kubernetes_secret.app.data), "OPENROUTER_MODEL"),
      contains(keys(kubernetes_secret.app.data), "TAVILY_API_KEY"),
    ])
    error_message = "secret must contain all expected keys"
  }

  assert {
    condition     = kubernetes_deployment.postgres.spec[0].template[0].spec[0].container[0].image == "postgres:16-alpine"
    error_message = "postgres image must be postgres:16-alpine"
  }

  assert {
    condition     = join(" ", kubernetes_deployment.postgres.spec[0].template[0].spec[0].container[0].readiness_probe[0].exec[0].command) == "pg_isready -U postgres"
    error_message = "postgres readiness probe must exec pg_isready, got: ${join(" ", kubernetes_deployment.postgres.spec[0].template[0].spec[0].container[0].readiness_probe[0].exec[0].command)}"
  }

  assert {
    condition     = join(" ", kubernetes_deployment.postgres.spec[0].template[0].spec[0].container[0].liveness_probe[0].exec[0].command) == "pg_isready -U postgres"
    error_message = "postgres liveness probe must exec pg_isready, got: ${join(" ", kubernetes_deployment.postgres.spec[0].template[0].spec[0].container[0].liveness_probe[0].exec[0].command)}"
  }

  assert {
    condition     = kubernetes_service.postgres.spec[0].type == "ClusterIP"
    error_message = "postgres service must be ClusterIP"
  }

  assert {
    condition     = kubernetes_deployment.api.spec[0].template[0].spec[0].container[0].image == "fastapi-postgres-ai:latest"
    error_message = "api image must be fastapi-postgres-ai:latest"
  }

  assert {
    condition     = kubernetes_deployment.api.spec[0].template[0].spec[0].container[0].image_pull_policy == "Never"
    error_message = "api imagePullPolicy must be Never"
  }

  assert {
    condition     = kubernetes_deployment.api.spec[0].template[0].spec[0].container[0].readiness_probe[0].http_get[0].path == "/docs"
    error_message = "api readiness probe must hit /docs"
  }

  assert {
    condition     = kubernetes_deployment.api.spec[0].template[0].spec[0].container[0].liveness_probe[0].http_get[0].path == "/docs"
    error_message = "api liveness probe must hit /docs"
  }

  assert {
    condition = alltrue([
      for env in kubernetes_deployment.api.spec[0].template[0].spec[0].container[0].env : true
      if contains(["POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "SECRET_KEY", "OPENROUTER_API_KEY", "OPENROUTER_URL", "OPENROUTER_MODEL", "TAVILY_API_KEY"], env.name)
    ]) && length(kubernetes_deployment.api.spec[0].template[0].spec[0].container[0].env) == 10
    error_message = "api must declare exactly the 10 expected env vars"
  }

  assert {
    condition     = kubernetes_service.api.spec[0].type == "NodePort"
    error_message = "api service must be NodePort"
  }

  assert {
    condition     = kubernetes_service.api.spec[0].port[0].port == 8001 && tostring(kubernetes_service.api.spec[0].port[0].target_port) == "8001"
    error_message = "api service port and targetPort must be 8001"
  }
}
