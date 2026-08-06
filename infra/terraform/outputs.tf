output "resource_group_name" {
  value = azurerm_resource_group.this.name
}

output "log_analytics_workspace_id" {
  value = azurerm_log_analytics_workspace.this.id
}

output "storage_account_name" {
  value = azurerm_storage_account.artifacts.name
}

output "raw_storage_container_name" {
  value = azurerm_storage_container.artifacts.name
}

output "normalized_storage_container_name" {
  value = azurerm_storage_container.normalized.name
}

output "container_registry_login_server" {
  value = azurerm_container_registry.this.login_server
}

output "postgres_server_fqdn" {
  value = azurerm_postgresql_flexible_server.this.fqdn
}

output "postgres_database_name" {
  value = azurerm_postgresql_flexible_server_database.taxlens.name
}

output "key_vault_name" {
  value = azurerm_key_vault.this.name
}

output "app_identity_client_id" {
  value = azurerm_user_assigned_identity.app.client_id
}

output "web_container_app_url" {
  value = "https://${azurerm_container_app.web.ingress[0].fqdn}"
}

output "api_container_app_name" {
  value = azurerm_container_app.api.name
}
