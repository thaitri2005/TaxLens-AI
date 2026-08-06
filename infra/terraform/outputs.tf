output "resource_group_name" {
  value = azurerm_resource_group.this.name
}

output "log_analytics_workspace_id" {
  value = azurerm_log_analytics_workspace.this.id
}

output "storage_account_name" {
  value = azurerm_storage_account.artifacts.name
}

output "storage_container_name" {
  value = azurerm_storage_container.artifacts.name
}

output "container_registry_login_server" {
  value = azurerm_container_registry.this.login_server
}
