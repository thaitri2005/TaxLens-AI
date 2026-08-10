resource "azurerm_postgresql_flexible_server_database" "airflow" {
  count     = var.airflow_enabled ? 1 : 0
  name      = "airflow"
  server_id = azurerm_postgresql_flexible_server.this.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

resource "azurerm_key_vault_secret" "airflow_internal_token" {
  count        = var.airflow_enabled ? 1 : 0
  name         = "airflow-internal-token"
  value        = var.airflow_internal_token
  key_vault_id = azurerm_key_vault.this.id
  depends_on   = [azurerm_role_assignment.terraform_key_vault_secrets]
}

resource "azurerm_key_vault_secret" "airflow_admin_password" {
  count        = var.airflow_enabled ? 1 : 0
  name         = "airflow-admin-password"
  value        = var.airflow_admin_password
  key_vault_id = azurerm_key_vault.this.id
  depends_on   = [azurerm_role_assignment.terraform_key_vault_secrets]
}

resource "azurerm_key_vault_secret" "airflow_metadata_connection" {
  count        = var.airflow_enabled ? 1 : 0
  name         = "airflow-metadata-connection"
  value        = "postgresql+psycopg2://taxlensadmin:${urlencode(var.postgres_admin_password)}@${azurerm_postgresql_flexible_server.this.fqdn}:5432/airflow?sslmode=require"
  key_vault_id = azurerm_key_vault.this.id
  depends_on   = [azurerm_role_assignment.terraform_key_vault_secrets, azurerm_postgresql_flexible_server_database.airflow]
}

resource "azurerm_key_vault_secret" "airflow_web_secret" {
  count        = var.airflow_enabled ? 1 : 0
  name         = "airflow-web-secret"
  value        = var.auth_internal_token
  key_vault_id = azurerm_key_vault.this.id
  depends_on   = [azurerm_role_assignment.terraform_key_vault_secrets]
}

resource "azurerm_container_app" "airflow_scheduler" {
  count                        = var.airflow_enabled ? 1 : 0
  name                         = "${var.name_prefix}-airflow-scheduler"
  container_app_environment_id = azurerm_container_app_environment.this.id
  resource_group_name          = azurerm_resource_group.this.name
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"
  depends_on = [
    azurerm_role_assignment.app_acr_pull,
    azurerm_role_assignment.app_key_vault_secrets,
    azurerm_key_vault_secret.airflow_metadata_connection,
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
    name                = "metadata-connection"
    key_vault_secret_id = azurerm_key_vault_secret.airflow_metadata_connection[0].versionless_id
    identity            = azurerm_user_assigned_identity.app.id
  }

  secret {
    name                = "airflow-token"
    key_vault_secret_id = azurerm_key_vault_secret.airflow_internal_token[0].versionless_id
    identity            = azurerm_user_assigned_identity.app.id
  }

  template {
    revision_suffix = "m7airflow1"
    min_replicas    = 1
    max_replicas    = 1

    container {
      name    = "scheduler"
      image   = var.airflow_image
      cpu     = 0.5
      memory  = "1Gi"
      command = ["bash", "-c"]
      args    = ["airflow db migrate && exec airflow scheduler"]

      env {
        name  = "AIRFLOW__CORE__EXECUTOR"
        value = "LocalExecutor"
      }
      env {
        name  = "AIRFLOW__CORE__LOAD_EXAMPLES"
        value = "false"
      }
      env {
        name  = "AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION"
        value = "true"
      }
      env {
        name        = "AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"
        secret_name = "metadata-connection"
      }
      env {
        name        = "TAXLENS_AIRFLOW_INTERNAL_TOKEN"
        secret_name = "airflow-token"
      }
      env {
        name  = "TAXLENS_API_URL"
        value = "http://${azurerm_container_app.api.name}"
      }
      # Azure Container Apps terminates HTTP requests after 240 seconds.
      # Keep processing batches to one document so a slow OCR job cannot
      # take down the whole Airflow task at the ingress boundary.
      env {
        name  = "TAXLENS_PROCESS_BATCH_SIZE"
        value = "1"
      }
      env {
        name  = "TAXLENS_PROCESS_MAX_BATCHES"
        value = "20"
      }
    }
  }
}

resource "azurerm_container_app" "airflow_webserver" {
  count                        = var.airflow_enabled ? 1 : 0
  name                         = "${var.name_prefix}-airflow-web"
  container_app_environment_id = azurerm_container_app_environment.this.id
  resource_group_name          = azurerm_resource_group.this.name
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"
  depends_on = [
    azurerm_role_assignment.app_acr_pull,
    azurerm_role_assignment.app_key_vault_secrets,
    azurerm_key_vault_secret.airflow_metadata_connection,
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
    name                = "metadata-connection"
    key_vault_secret_id = azurerm_key_vault_secret.airflow_metadata_connection[0].versionless_id
    identity            = azurerm_user_assigned_identity.app.id
  }

  secret {
    name                = "airflow-admin-password"
    key_vault_secret_id = azurerm_key_vault_secret.airflow_admin_password[0].versionless_id
    identity            = azurerm_user_assigned_identity.app.id
  }

  secret {
    name                = "airflow-web-secret"
    key_vault_secret_id = azurerm_key_vault_secret.airflow_web_secret[0].versionless_id
    identity            = azurerm_user_assigned_identity.app.id
  }

  template {
    revision_suffix = "m7airflow1"
    min_replicas    = 0
    max_replicas    = 1

    container {
      name    = "webserver"
      image   = var.airflow_image
      cpu     = 0.5
      memory  = "1Gi"
      command = ["bash", "-c"]
      args    = ["airflow db migrate && airflow users create --username \"$AIRFLOW_ADMIN_USERNAME\" --password \"$AIRFLOW_ADMIN_PASSWORD\" --firstname TaxLens --lastname Admin --role Admin --email admin@taxlens.local || true; exec airflow webserver"]

      env {
        name  = "AIRFLOW__CORE__EXECUTOR"
        value = "LocalExecutor"
      }
      env {
        name  = "AIRFLOW__CORE__LOAD_EXAMPLES"
        value = "false"
      }
      env {
        name  = "AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION"
        value = "true"
      }
      env {
        name        = "AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"
        secret_name = "metadata-connection"
      }
      env {
        name        = "AIRFLOW__WEBSERVER__SECRET_KEY"
        secret_name = "airflow-web-secret"
      }
      env {
        name  = "AIRFLOW_ADMIN_USERNAME"
        value = var.airflow_admin_username
      }
      env {
        name        = "AIRFLOW_ADMIN_PASSWORD"
        secret_name = "airflow-admin-password"
      }
    }
  }

  ingress {
    external_enabled           = var.airflow_web_external_enabled
    allow_insecure_connections = false
    target_port                = 8080
    transport                  = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }
}
