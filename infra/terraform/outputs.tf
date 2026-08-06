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
