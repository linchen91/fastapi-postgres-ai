output "namespace" {
  description = "Name of the application namespace."
  value       = kubernetes_namespace.app.metadata[0].name
}

output "api_service_name" {
  description = "Name of the API service."
  value       = kubernetes_service.api.metadata[0].name
}

output "api_node_port" {
  description = "NodePort assigned to the API service."
  value       = kubernetes_service.api.spec[0].port[0].node_port
}

output "postgres_service_name" {
  description = "Name of the PostgreSQL service."
  value       = kubernetes_service.postgres.metadata[0].name
}
