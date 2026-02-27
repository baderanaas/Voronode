resource "random_string" "storage_suffix" {
  length  = 4
  special = false
  upper   = false
}

resource "azurerm_storage_account" "main" {
  name                     = "stvoronode${random_string.storage_suffix.result}"
  resource_group_name      = azurerm_resource_group.main.name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = "LRS"

  tags = {
    project = var.project_name
  }
}

resource "azurerm_storage_share" "neo4j_data" {
  name                 = "neo4j-data"
  storage_account_name = azurerm_storage_account.main.name
  quota                = 50
}

resource "azurerm_storage_share" "neo4j_logs" {
  name                 = "neo4j-logs"
  storage_account_name = azurerm_storage_account.main.name
  quota                = 10
}

resource "azurerm_storage_share" "chroma_data" {
  name                 = "chroma-data"
  storage_account_name = azurerm_storage_account.main.name
  quota                = 50
}

resource "azurerm_storage_share" "sqlite_data" {
  name                 = "sqlite-data"
  storage_account_name = azurerm_storage_account.main.name
  quota                = 5
}
