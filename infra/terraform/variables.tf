variable "subscription_id" {
  type        = string
  description = "Azure subscription ID. Prefer ARM_SUBSCRIPTION_ID in CI."
}

variable "location" {
  type        = string
  description = "Azure region for the development environment."
  default     = "eastasia"
}

variable "name_prefix" {
  type        = string
  description = "Globally unique lowercase prefix for Azure resource names."
  default     = "taxlens-dev"
}

variable "tags" {
  type        = map(string)
  description = "Common resource tags."
  default = {
    application = "taxlens"
    environment = "dev"
    managed_by  = "terraform"
  }
}

variable "postgres_admin_password" {
  type        = string
  description = "Administrator password for PostgreSQL Flexible Server. Supply via TF_VAR_postgres_admin_password; never commit it."
  sensitive   = true
}

variable "postgres_allowed_ip" {
  type        = string
  description = "Optional public IPv4 address allowed to connect to PostgreSQL. Leave empty to create no firewall rule."
  default     = ""
}

variable "hf_token" {
  type        = string
  description = "Hugging Face API token for production inference. Supply locally and never commit it."
  sensitive   = true
}

variable "auth_internal_token" {
  type        = string
  description = "Shared secret used only between Next.js and the private FastAPI service. Never commit it."
  sensitive   = true
}

variable "nextauth_secret" {
  type        = string
  description = "Auth.js session encryption secret. Never commit it."
  sensitive   = true
}

variable "key_vault_name" {
  type        = string
  description = "Globally unique Azure Key Vault name."
  default     = "taxlensdevkv"
}

variable "api_image" {
  type        = string
  description = "API image in Azure Container Registry. Build and push it before applying Phase 4."
  default     = "taxlensdevacr.azurecr.io/taxlens-api:phase4"
}

variable "web_image" {
  type        = string
  description = "Web image in Azure Container Registry. Build and push it before applying Phase 4."
  default     = "taxlensdevacr.azurecr.io/taxlens-web:phase4"
}

variable "airflow_enabled" {
  type        = bool
  description = "Enable the optional Azure Airflow scheduler and webserver. Keep false until M7 deployment approval."
  default     = false
}

variable "airflow_web_external_enabled" {
  type        = bool
  description = "Expose the Airflow webserver through public Container Apps ingress when Airflow is enabled."
  default     = false
}

variable "airflow_image" {
  type        = string
  description = "Airflow image in Azure Container Registry. Build and push it before enabling M7."
  default     = "taxlensdevacr.azurecr.io/taxlens-airflow:m7"
}

variable "airflow_admin_username" {
  type        = string
  description = "Initial Airflow UI administrator username."
  default     = "admin"
}

variable "airflow_admin_password" {
  type        = string
  description = "Initial Airflow UI administrator password. Required when Airflow is enabled."
  sensitive   = true
  default     = ""
}

variable "airflow_internal_token" {
  type        = string
  description = "Secret used by Airflow DAGs to authenticate to the internal API job endpoints. Required when Airflow is enabled."
  sensitive   = true
  default     = ""
}
