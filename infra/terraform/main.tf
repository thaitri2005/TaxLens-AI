resource "azurerm_resource_provider_registration" "container_apps" {
  name = "Microsoft.App"
}

resource "azurerm_resource_group" "this" {
  name     = "${var.name_prefix}-rg"
  location = var.location
  tags     = var.tags
}

resource "azurerm_log_analytics_workspace" "this" {
  name                = "${var.name_prefix}-logs"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = var.tags
}

resource "azurerm_storage_account" "artifacts" {
  name                            = replace("${var.name_prefix}artifacts", "-", "")
  resource_group_name             = azurerm_resource_group.this.name
  location                        = azurerm_resource_group.this.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  shared_access_key_enabled       = true
  tags                            = var.tags
}

resource "azurerm_storage_container" "artifacts" {
  name                  = "raw-documents"
  storage_account_id    = azurerm_storage_account.artifacts.id
  container_access_type = "private"
}

resource "azurerm_storage_container" "normalized" {
  name                  = "normalized-text"
  storage_account_id    = azurerm_storage_account.artifacts.id
  container_access_type = "private"
}

resource "azurerm_container_registry" "this" {
  name                = replace("${var.name_prefix}acr", "-", "")
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  sku                 = "Basic"
  admin_enabled       = false
  tags                = var.tags
}

resource "azurerm_postgresql_flexible_server" "this" {
  name                          = "${var.name_prefix}-pg"
  resource_group_name           = azurerm_resource_group.this.name
  location                      = azurerm_resource_group.this.location
  version                       = "16"
  administrator_login           = "taxlensadmin"
  administrator_password        = var.postgres_admin_password
  sku_name                      = "B_Standard_B1ms"
  zone                          = "1"
  storage_mb                    = 32768
  backup_retention_days         = 7
  geo_redundant_backup_enabled  = false
  public_network_access_enabled = true
  tags                          = var.tags
}

resource "azurerm_postgresql_flexible_server_database" "taxlens" {
  name      = "taxlens"
  server_id = azurerm_postgresql_flexible_server.this.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

resource "azurerm_postgresql_flexible_server_configuration" "extensions" {
  name      = "azure.extensions"
  server_id = azurerm_postgresql_flexible_server.this.id
  value     = "vector"
}

resource "azurerm_postgresql_flexible_server_firewall_rule" "developer" {
  count            = var.postgres_allowed_ip == "" ? 0 : 1
  name             = "developer-ip"
  server_id        = azurerm_postgresql_flexible_server.this.id
  start_ip_address = var.postgres_allowed_ip
  end_ip_address   = var.postgres_allowed_ip
}

resource "azurerm_postgresql_flexible_server_firewall_rule" "azure_services" {
  name             = "azure-services"
  server_id        = azurerm_postgresql_flexible_server.this.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

data "azurerm_client_config" "current" {}

resource "azurerm_user_assigned_identity" "app" {
  name                = "${var.name_prefix}-app-identity"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  tags                = var.tags
}

resource "azurerm_key_vault" "this" {
  name                          = var.key_vault_name
  location                      = azurerm_resource_group.this.location
  resource_group_name           = azurerm_resource_group.this.name
  tenant_id                     = data.azurerm_client_config.current.tenant_id
  sku_name                      = "standard"
  soft_delete_retention_days    = 7
  purge_protection_enabled      = false
  rbac_authorization_enabled    = true
  public_network_access_enabled = true
  tags                          = var.tags
}

resource "azurerm_role_assignment" "app_key_vault_secrets" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

resource "azurerm_role_assignment" "terraform_key_vault_secrets" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_role_assignment" "app_blob_contributor" {
  scope                = azurerm_storage_account.artifacts.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

resource "azurerm_role_assignment" "app_acr_pull" {
  scope                = azurerm_container_registry.this.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

resource "azurerm_key_vault_secret" "postgres_admin_password" {
  name         = "postgres-admin-password"
  value        = var.postgres_admin_password
  key_vault_id = azurerm_key_vault.this.id
  depends_on   = [azurerm_role_assignment.terraform_key_vault_secrets]
}

resource "azurerm_key_vault_secret" "hf_token" {
  name         = "hf-token"
  value        = var.hf_token
  key_vault_id = azurerm_key_vault.this.id
  depends_on   = [azurerm_role_assignment.terraform_key_vault_secrets]
}

resource "azurerm_key_vault_secret" "auth_internal_token" {
  name         = "auth-internal-token"
  value        = var.auth_internal_token
  key_vault_id = azurerm_key_vault.this.id
  depends_on   = [azurerm_role_assignment.terraform_key_vault_secrets]
}

resource "azurerm_key_vault_secret" "nextauth_secret" {
  name         = "nextauth-secret"
  value        = var.nextauth_secret
  key_vault_id = azurerm_key_vault.this.id
  depends_on   = [azurerm_role_assignment.terraform_key_vault_secrets]
}

resource "azurerm_container_app_environment" "this" {
  name                       = "${var.name_prefix}-aca-env"
  location                   = azurerm_resource_group.this.location
  resource_group_name        = azurerm_resource_group.this.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.this.id
  depends_on                 = [azurerm_resource_provider_registration.container_apps]

  workload_profile {
    name                  = "Consumption"
    workload_profile_type = "Consumption"
    minimum_count         = 0
    maximum_count         = 0
  }

  tags = var.tags
}

resource "azurerm_container_app" "api" {
  name                         = "${var.name_prefix}-api"
  container_app_environment_id = azurerm_container_app_environment.this.id
  resource_group_name          = azurerm_resource_group.this.name
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"
  depends_on = [
    azurerm_role_assignment.app_acr_pull,
    azurerm_role_assignment.app_blob_contributor,
    azurerm_role_assignment.app_key_vault_secrets,
  ]

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  registry {
    server   = azurerm_container_registry.this.login_server
    identity = azurerm_user_assigned_identity.app.id
  }

  secret {
    name                = "hf-token"
    key_vault_secret_id = azurerm_key_vault_secret.hf_token.versionless_id
    identity            = azurerm_user_assigned_identity.app.id
  }

  secret {
    name                = "postgres-admin-password"
    key_vault_secret_id = azurerm_key_vault_secret.postgres_admin_password.versionless_id
    identity            = azurerm_user_assigned_identity.app.id
  }

  secret {
    name                = "auth-internal-token"
    key_vault_secret_id = azurerm_key_vault_secret.auth_internal_token.versionless_id
    identity            = azurerm_user_assigned_identity.app.id
  }

  template {
    revision_suffix = "m64ops1"
    min_replicas    = 0
    max_replicas    = 1

    container {
      name   = "api"
      image  = var.api_image
      cpu    = 1.0
      memory = "2Gi"

      env {
        name  = "APP_ENV"
        value = "production"
      }
      env {
        name  = "DATABASE_HOST"
        value = azurerm_postgresql_flexible_server.this.fqdn
      }
      env {
        name  = "DATABASE_PORT"
        value = "5432"
      }
      env {
        name  = "DATABASE_NAME"
        value = azurerm_postgresql_flexible_server_database.taxlens.name
      }
      env {
        name  = "DATABASE_USER"
        value = "taxlensadmin"
      }
      env {
        name  = "DATABASE_SSL_MODE"
        value = "require"
      }
      env {
        name  = "OBJECT_STORAGE_BACKEND"
        value = "azure_blob"
      }
      env {
        name  = "AZURE_STORAGE_ACCOUNT_URL"
        value = "https://${azurerm_storage_account.artifacts.name}.blob.core.windows.net"
      }
      env {
        name  = "AZURE_STORAGE_CONTAINER"
        value = azurerm_storage_container.artifacts.name
      }
      env {
        name  = "AZURE_STORAGE_NORMALIZED_CONTAINER"
        value = azurerm_storage_container.normalized.name
      }
      env {
        name        = "HF_TOKEN"
        secret_name = "hf-token"
      }
      env {
        name        = "AUTH_INTERNAL_TOKEN"
        secret_name = "auth-internal-token"
      }
      env {
        name        = "DATABASE_PASSWORD"
        secret_name = "postgres-admin-password"
      }
      env {
        name  = "AZURE_CLIENT_ID"
        value = azurerm_user_assigned_identity.app.client_id
      }

      liveness_probe {
        transport = "HTTP"
        port      = 8000
        path      = "/health"
      }

      readiness_probe {
        transport = "HTTP"
        port      = 8000
        path      = "/ready"
      }
    }
  }

  ingress {
    external_enabled           = false
    allow_insecure_connections = true
    target_port                = 8000
    transport                  = "http"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  tags = var.tags
}

resource "azurerm_container_app" "web" {
  name                         = "${var.name_prefix}-web"
  container_app_environment_id = azurerm_container_app_environment.this.id
  resource_group_name          = azurerm_resource_group.this.name
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  registry {
    server   = azurerm_container_registry.this.login_server
    identity = azurerm_user_assigned_identity.app.id
  }

  secret {
    name                = "auth-internal-token"
    key_vault_secret_id = azurerm_key_vault_secret.auth_internal_token.versionless_id
    identity            = azurerm_user_assigned_identity.app.id
  }

  secret {
    name                = "nextauth-secret"
    key_vault_secret_id = azurerm_key_vault_secret.nextauth_secret.versionless_id
    identity            = azurerm_user_assigned_identity.app.id
  }

  template {
    revision_suffix = "m63auth1"
    min_replicas    = 0
    max_replicas    = 1

    container {
      name   = "web"
      image  = var.web_image
      cpu    = 0.25
      memory = "0.5Gi"

      env {
        name        = "AUTH_INTERNAL_TOKEN"
        secret_name = "auth-internal-token"
      }
      env {
        name        = "NEXTAUTH_SECRET"
        secret_name = "nextauth-secret"
      }
    }
  }

  ingress {
    external_enabled = true
    target_port      = 3000
    transport        = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  tags = var.tags
}
