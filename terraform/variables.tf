variable "config_path" {
  description = "Path to the kubeconfig file used by the Kubernetes provider."
  type        = string
  default     = "~/.kube/config"
}

variable "namespace" {
  description = "Kubernetes namespace for all application resources."
  type        = string
  default     = "fastapi-postgres"
}

variable "config_map_name" {
  description = "Name of the ConfigMap holding non-sensitive configuration."
  type        = string
  default     = "app-config"
}

variable "secret_name" {
  description = "Name of the Secret holding sensitive configuration."
  type        = string
  default     = "app-secrets"
}

variable "postgres_user" {
  description = "PostgreSQL username."
  type        = string
  default     = "postgres"
  sensitive   = true
}

variable "postgres_password" {
  description = "PostgreSQL password."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.postgres_password) > 0
    error_message = "postgres_password must not be empty."
  }
}

variable "postgres_db" {
  description = "PostgreSQL database name."
  type        = string
  default     = "dzservice"
}

variable "postgres_host" {
  description = "PostgreSQL host as seen by the API pods."
  type        = string
  default     = "postgres"
}

variable "postgres_port" {
  description = "PostgreSQL port as seen by the API pods."
  type        = string
  default     = "5432"
}

variable "postgres_image" {
  description = "PostgreSQL container image."
  type        = string
  default     = "postgres:16-alpine"
}

variable "postgres_replicas" {
  description = "Number of PostgreSQL replicas."
  type        = number
  default     = 1
}

variable "secret_key" {
  description = "JWT signing key for the API."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.secret_key) > 0
    error_message = "secret_key must not be empty."
  }
}

variable "openrouter_api_key" {
  description = "OpenRouter API key."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.openrouter_api_key) > 0
    error_message = "openrouter_api_key must not be empty."
  }
}

variable "openrouter_model" {
  description = "OpenRouter model identifier."
  type        = string
  default     = "openrouter/free"
}

variable "openrouter_url" {
  description = "OpenRouter API base URL."
  type        = string
  default     = "https://openrouter.ai/api/v1"
}

variable "tavily_api_key" {
  description = "Tavily API key."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.tavily_api_key) > 0
    error_message = "tavily_api_key must not be empty."
  }
}

variable "api_image" {
  description = "API container image."
  type        = string
  default     = "fastapi-postgres-ai:latest"
}

variable "api_image_pull_policy" {
  description = "Image pull policy for the API container."
  type        = string
  default     = "Never"
}

variable "api_replicas" {
  description = "Number of API replicas."
  type        = number
  default     = 1
}

variable "api_node_port" {
  description = "Optional fixed NodePort for the API service (null = let Kubernetes assign)."
  type        = number
  default     = null

  validation {
    condition     = var.api_node_port == null ? true : (var.api_node_port >= 30000 && var.api_node_port <= 32767)
    error_message = "api_node_port must be null or between 30000 and 32767."
  }
}
