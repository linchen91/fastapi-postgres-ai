resource "kubernetes_deployment" "api" {
  metadata {
    name      = "api"
    namespace = kubernetes_namespace.app.metadata[0].name

    labels = {
      app = "api"
    }
  }

  spec {
    replicas = var.api_replicas

    selector {
      match_labels = {
        app = "api"
      }
    }

    template {
      metadata {
        labels = {
          app = "api"
        }
      }

      spec {
        container {
          name              = "api"
          image             = var.api_image
          image_pull_policy = var.api_image_pull_policy

          port {
            container_port = 8001
          }

          env {
            name = "POSTGRES_HOST"

            value_from {
              config_map_key_ref {
                name = var.config_map_name
                key  = "POSTGRES_HOST"
              }
            }
          }

          env {
            name = "POSTGRES_PORT"

            value_from {
              config_map_key_ref {
                name = var.config_map_name
                key  = "POSTGRES_PORT"
              }
            }
          }

          env {
            name = "POSTGRES_DB"

            value_from {
              config_map_key_ref {
                name = var.config_map_name
                key  = "POSTGRES_DB"
              }
            }
          }

          env {
            name = "POSTGRES_USER"

            value_from {
              secret_key_ref {
                name = var.secret_name
                key  = "POSTGRES_USER"
              }
            }
          }

          env {
            name = "POSTGRES_PASSWORD"

            value_from {
              secret_key_ref {
                name = var.secret_name
                key  = "POSTGRES_PASSWORD"
              }
            }
          }

          env {
            name = "SECRET_KEY"

            value_from {
              secret_key_ref {
                name = var.secret_name
                key  = "SECRET_KEY"
              }
            }
          }

          env {
            name = "OPENROUTER_API_KEY"

            value_from {
              secret_key_ref {
                name = var.secret_name
                key  = "OPENROUTER_API_KEY"
              }
            }
          }

          env {
            name = "OPENROUTER_URL"

            value_from {
              secret_key_ref {
                name = var.secret_name
                key  = "OPENROUTER_URL"
              }
            }
          }

          env {
            name = "OPENROUTER_MODEL"

            value_from {
              secret_key_ref {
                name = var.secret_name
                key  = "OPENROUTER_MODEL"
              }
            }
          }

          env {
            name = "TAVILY_API_KEY"

            value_from {
              secret_key_ref {
                name = var.secret_name
                key  = "TAVILY_API_KEY"
              }
            }
          }

          readiness_probe {
            http_get {
              path = "/docs"
              port = 8001
            }

            initial_delay_seconds = 10
            period_seconds        = 10
          }

          liveness_probe {
            http_get {
              path = "/docs"
              port = 8001
            }

            initial_delay_seconds = 15
            period_seconds        = 20
          }
        }
      }
    }
  }
}

resource "kubernetes_service" "api" {
  metadata {
    name      = "api"
    namespace = kubernetes_namespace.app.metadata[0].name
  }

  spec {
    selector = {
      app = "api"
    }

    port {
      port        = 8001
      target_port = 8001
      node_port   = var.api_node_port
    }

    type = "NodePort"
  }
}
