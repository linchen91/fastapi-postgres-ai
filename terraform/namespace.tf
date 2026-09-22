resource "kubernetes_namespace" "app" {
  metadata {
    name = var.namespace
  }
}
