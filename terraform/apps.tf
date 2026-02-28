resource "azurerm_container_app_environment" "main" {
  name                       = "cae-${var.project_name}"
  location                   = var.location
  resource_group_name        = azurerm_resource_group.main.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

  tags = {
    project = var.project_name
  }
}


# Backend Container App (internal ingress only)
resource "azurerm_container_app" "backend" {
  name                         = "ca-backend-${var.project_name}"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app_identity.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.app_identity.id
  }

  ingress {
    external_enabled = false
    target_port      = 8080
    transport        = "http"

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  secret {
    name  = "neo4j-password"
    value = var.neo4j_password
  }
  secret {
    name  = "groq-api-key"
    value = var.groq_api_key
  }
  secret {
    name  = "openai-api-key"
    value = var.openai_api_key
  }
  secret {
    name  = "gemini-api-key"
    value = var.gemini_api_key
  }
  secret {
    name  = "anthropic-api-key"
    value = var.anthropic_api_key
  }
  secret {
    name  = "tavily-api-key"
    value = var.tavily_api_key
  }
  secret {
    name  = "jwt-secret-key"
    value = var.jwt_secret_key
  }
  secret {
    name  = "neon-database-url"
    value = var.neon_database_url
  }

  template {
    min_replicas = 0
    max_replicas = 1

    container {
      name   = "backend"
      image  = var.backend_image
      cpu    = 1.0
      memory = "2Gi"

      # Database connections — ACIs with public IPs via stable DNS labels
      env {
        name  = "NEO4J_URI"
        value = "bolt://${azurerm_container_group.neo4j.ip_address}:7687"
      }
      env {
        name  = "NEO4J_USER"
        value = "neo4j"
      }
      env {
        name        = "NEO4J_PASSWORD"
        secret_name = "neo4j-password"
      }
      env {
        name  = "CHROMADB_HOST"
        value = azurerm_container_group.chromadb.ip_address
      }
      env {
        name  = "CHROMADB_PORT"
        value = "8000"
      }

      # Postgres (Neon) — persistent cloud database
      env {
        name        = "DATABASE_URL"
        secret_name = "neon-database-url"
      }

      # API keys
      env {
        name        = "GROQ_API_KEY"
        secret_name = "groq-api-key"
      }
      env {
        name        = "OPENAI_API_KEY"
        secret_name = "openai-api-key"
      }
      env {
        name        = "GEMINI_API_KEY"
        secret_name = "gemini-api-key"
      }
      env {
        name        = "ANTHROPIC_API_KEY"
        secret_name = "anthropic-api-key"
      }
      env {
        name        = "TAVILY_API_KEY"
        secret_name = "tavily-api-key"
      }
      env {
        name        = "JWT_SECRET_KEY"
        secret_name = "jwt-secret-key"
      }

      # LLM model selection
      env {
        name  = "GROQ_MODEL"
        value = var.groq_model
      }
      env {
        name  = "OPENAI_CHAT_MODEL"
        value = var.openai_chat_model
      }
      env {
        name  = "OPENAI_EMBEDDING_MODEL"
        value = var.openai_embedding_model
      }
      env {
        name  = "GEMINI_MODEL"
        value = var.gemini_model
      }
      env {
        name  = "ANTHROPIC_MODEL"
        value = var.anthropic_model
      }

      env {
        name  = "ENV"
        value = "production"
      }
    }
  }

  tags = {
    project = var.project_name
  }

  depends_on = []
}

# Frontend Container App (external ingress)
resource "azurerm_container_app" "frontend" {
  name                         = "ca-frontend-${var.project_name}"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app_identity.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.app_identity.id
  }

  ingress {
    external_enabled = true
    target_port      = 8501
    transport        = "http"

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  template {
    min_replicas = 0
    max_replicas = 3

    container {
      name   = "frontend"
      image  = var.frontend_image
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "BACKEND_URL"
        value = "http://ca-backend-${var.project_name}"
      }
    }
  }

  tags = {
    project = var.project_name
  }

  depends_on = [azurerm_container_app.backend]
}
