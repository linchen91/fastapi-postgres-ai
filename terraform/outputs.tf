output "namespace" {
  description = "Name of the application namespace."
  value       = kubernetes_namespace.app.metadata[0].name
}

output "helm_release_name" {
  description = "Name of the Helm release deploying the application stack."
  value       = helm_release.app.name
}

output "api_service_name" {
  description = "Name of the API service (created by the Helm release)."
  value       = "api"
}

output "api_node_port" {
  description = "Configured NodePort for the API service (null = assigned by Kubernetes; fetch with: kubectl get svc api -n fastapi-postgres -o jsonpath='{.spec.ports[0].nodePort}')."
  value       = var.api_node_port
}

output "postgres_service_name" {
  description = "Name of the PostgreSQL service (created by the Helm release)."
  value       = "postgres"
}
