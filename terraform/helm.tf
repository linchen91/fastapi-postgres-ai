# The application stack (ConfigMap, Secret, PostgreSQL, API) is a single Helm
# release rendered from the in-repo chart at ../helm. The namespace stays a
# plain kubernetes_namespace resource (namespace.tf).
resource "helm_release" "app" {
  name      = "fastapi-postgres-ai"
  chart     = abspath("${path.module}/../helm")
  namespace = kubernetes_namespace.app.metadata[0].name

  # Adopt the objects created by the pre-Helm kubernetes_* resources (see
  # migration.tf). Harmless afterwards; can be set to false once the migration
  # apply has succeeded.
  take_ownership = true

  wait    = true
  timeout = 600

  values = [yamlencode({
    configMap = {
      name          = var.config_map_name
      postgresHost  = var.postgres_host
      postgresPort  = var.postgres_port
      postgresDb    = var.postgres_db
      openrouterUrl = var.openrouter_url
    }

    secret = {
      name             = var.secret_name
      postgresUser     = var.postgres_user
      postgresPassword = var.postgres_password
      secretKey        = var.secret_key
      openrouterApiKey = var.openrouter_api_key
      openrouterModel  = var.openrouter_model
      openrouterUrl    = var.openrouter_url
      tavilyApiKey     = var.tavily_api_key
    }

    postgres = {
      image       = var.postgres_image
      replicas    = var.postgres_replicas
      persistence = { size = "1Gi" }
    }

    api = {
      image           = var.api_image
      imagePullPolicy = var.api_image_pull_policy
      replicas        = var.api_replicas

      service = {
        type     = "NodePort"
        nodePort = var.api_node_port
      }
    }
  })]
}
