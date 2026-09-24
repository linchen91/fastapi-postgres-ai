# Offline plan assertions: no cluster required (dummy kubeconfig supplied by scripts/test-terraform.sh).
# The stack is deployed as one Helm release; assertions decode the values
# passed to helm_release.app (secrets marked sensitive -> nonsensitive()).

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
    condition     = helm_release.app.name == "fastapi-postgres-ai"
    error_message = "helm release name must be fastapi-postgres-ai"
  }

  assert {
    condition     = helm_release.app.namespace == "fastapi-postgres"
    error_message = "helm release must target namespace fastapi-postgres"
  }

  assert {
    condition     = endswith(helm_release.app.chart, "/helm")
    error_message = "helm release must use the in-repo chart at ../helm, got: ${helm_release.app.chart}"
  }

  assert {
    condition     = helm_release.app.take_ownership == true
    error_message = "helm release must adopt pre-existing objects (take_ownership)"
  }

  assert {
    condition     = yamldecode(nonsensitive(helm_release.app.values[0])).configMap.postgresDb == "dzservice"
    error_message = "configMap.postgresDb must be dzservice"
  }

  assert {
    condition     = yamldecode(nonsensitive(helm_release.app.values[0])).configMap.postgresHost == "postgres"
    error_message = "configMap.postgresHost must be postgres"
  }

  assert {
    condition = alltrue([
      contains(keys(yamldecode(nonsensitive(helm_release.app.values[0])).secret), "postgresUser"),
      contains(keys(yamldecode(nonsensitive(helm_release.app.values[0])).secret), "postgresPassword"),
      contains(keys(yamldecode(nonsensitive(helm_release.app.values[0])).secret), "secretKey"),
      contains(keys(yamldecode(nonsensitive(helm_release.app.values[0])).secret), "openrouterApiKey"),
      contains(keys(yamldecode(nonsensitive(helm_release.app.values[0])).secret), "openrouterUrl"),
      contains(keys(yamldecode(nonsensitive(helm_release.app.values[0])).secret), "openrouterModel"),
      contains(keys(yamldecode(nonsensitive(helm_release.app.values[0])).secret), "tavilyApiKey"),
    ])
    error_message = "secret values must contain all expected keys"
  }

  assert {
    condition     = yamldecode(nonsensitive(helm_release.app.values[0])).secret.postgresPassword == "test-password"
    error_message = "secret.postgresPassword must pass through the postgres_password variable"
  }

  assert {
    condition     = yamldecode(nonsensitive(helm_release.app.values[0])).postgres.image == "postgres:16-alpine"
    error_message = "postgres image must be postgres:16-alpine"
  }

  assert {
    condition     = yamldecode(nonsensitive(helm_release.app.values[0])).postgres.persistence.size == "1Gi"
    error_message = "postgres persistence size must be 1Gi"
  }

  assert {
    condition     = yamldecode(nonsensitive(helm_release.app.values[0])).api.image == "fastapi-postgres-ai:latest"
    error_message = "api image must be fastapi-postgres-ai:latest"
  }

  assert {
    condition     = yamldecode(nonsensitive(helm_release.app.values[0])).api.imagePullPolicy == "Never"
    error_message = "api imagePullPolicy must be Never"
  }

  assert {
    condition     = yamldecode(nonsensitive(helm_release.app.values[0])).api.service.nodePort == null
    error_message = "api service nodePort must be null (Kubernetes assigns)"
  }
}
