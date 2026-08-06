variable "subscription_id" {
  type        = string
  description = "Azure subscription ID. Prefer ARM_SUBSCRIPTION_ID in CI."
}

variable "location" {
  type        = string
  description = "Azure region for the development environment."
  default     = "southeastasia"
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
