resource "azurerm_log_analytics_workspace" "main" {
  name                = "law-${var.project_name}"
  location            = var.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30

  tags = {
    project = var.project_name
  }
}

resource "azurerm_application_insights" "main" {
  name                = "appi-${var.project_name}"
  location            = var.location
  resource_group_name = azurerm_resource_group.main.name
  workspace_id        = azurerm_log_analytics_workspace.main.id
  application_type    = "web"

  tags = {
    project = var.project_name
  }
}
