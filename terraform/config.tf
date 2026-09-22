resource "kubernetes_config_map" "app" {
  metadata {
    name      = var.config_map_name
    namespace = kubernetes_namespace.app.metadata[0].name
  }

  data = {
    POSTGRES_HOST  = var.postgres_host
    POSTGRES_PORT  = var.postgres_port
    POSTGRES_DB    = var.postgres_db
    OPENROUTER_URL = var.openrouter_url
  }
}

resource "kubernetes_secret" "app" {
  metadata {
    name      = var.secret_name
    namespace = kubernetes_namespace.app.metadata[0].name
  }

  type = "Opaque"

  data = {
    POSTGRES_USER      = var.postgres_user
    POSTGRES_PASSWORD  = var.postgres_password
    SECRET_KEY         = var.secret_key
    OPENROUTER_API_KEY = var.openrouter_api_key
    OPENROUTER_URL     = var.openrouter_url
    OPENROUTER_MODEL   = var.openrouter_model
    TAVILY_API_KEY     = var.tavily_api_key
  }
}
