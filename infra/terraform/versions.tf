terraform {
  required_version = ">= 1.8.0"

  backend "azurerm" {
    resource_group_name  = "taxlens-dev-rg"
    storage_account_name = "taxlensdevartifacts"
    container_name       = "terraform-state"
    key                  = "taxlens-dev.tfstate"
    use_azuread_auth     = true
  }

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}
