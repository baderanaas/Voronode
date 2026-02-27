resource "azurerm_container_group" "neo4j" {
  name                = "aci-neo4j-${var.project_name}"
  location            = var.location
  resource_group_name = azurerm_resource_group.main.name
  os_type             = "Linux"
  restart_policy      = "Always"
  ip_address_type     = "Public"
  dns_name_label      = "neo4j-${var.project_name}"

  image_registry_credential {
    server   = azurerm_container_registry.main.login_server
    username = azurerm_container_registry.main.admin_username
    password = azurerm_container_registry.main.admin_password
  }

  container {
    name   = "neo4j"
    image  = "${azurerm_container_registry.main.login_server}/neo4j:5.18"
    cpu    = "1.0"
    memory = "2.0"

    ports {
      port     = 7474
      protocol = "TCP"
    }

    ports {
      port     = 7687
      protocol = "TCP"
    }

    environment_variables = {
      NEO4J_AUTH                         = "neo4j/${var.neo4j_password}"
      NEO4J_PLUGINS                      = "[\"apoc\"]"
      NEO4J_server_memory_heap_max__size = "1G"
      NEO4J_server_memory_pagecache_size = "512m"
    }

    volume {
      name                 = "neo4j-data"
      mount_path           = "/data"
      storage_account_name = azurerm_storage_account.main.name
      storage_account_key  = azurerm_storage_account.main.primary_access_key
      share_name           = azurerm_storage_share.neo4j_data.name
    }

    volume {
      name                 = "neo4j-logs"
      mount_path           = "/logs"
      storage_account_name = azurerm_storage_account.main.name
      storage_account_key  = azurerm_storage_account.main.primary_access_key
      share_name           = azurerm_storage_share.neo4j_logs.name
    }
  }

  tags = {
    project = var.project_name
  }
}

resource "azurerm_container_group" "chromadb" {
  name                = "aci-chromadb-${var.project_name}"
  location            = var.location
  resource_group_name = azurerm_resource_group.main.name
  os_type             = "Linux"
  restart_policy      = "Always"
  ip_address_type     = "Public"
  dns_name_label      = "chromadb-${var.project_name}"

  image_registry_credential {
    server   = azurerm_container_registry.main.login_server
    username = azurerm_container_registry.main.admin_username
    password = azurerm_container_registry.main.admin_password
  }

  container {
    name   = "chromadb"
    image  = "${azurerm_container_registry.main.login_server}/chromadb:latest"
    cpu    = "0.5"
    memory = "1.0"

    ports {
      port     = 8000
      protocol = "TCP"
    }

    environment_variables = {
      IS_PERSISTENT        = "TRUE"
      ANONYMIZED_TELEMETRY = "FALSE"
    }

    volume {
      name                 = "chroma-data"
      mount_path           = "/chroma/chroma"
      storage_account_name = azurerm_storage_account.main.name
      storage_account_key  = azurerm_storage_account.main.primary_access_key
      share_name           = azurerm_storage_share.chroma_data.name
    }
  }

  tags = {
    project = var.project_name
  }
}
