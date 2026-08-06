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
