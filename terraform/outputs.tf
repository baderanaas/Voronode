output "frontend_url" {
  description = "Public URL for the Streamlit frontend"
  value       = "https://${azurerm_container_app.frontend.ingress[0].fqdn}"
}

output "backend_internal_url" {
  description = "Internal Container Apps DNS URL for the FastAPI backend"
  value       = "http://ca-backend-${var.project_name}"
}

output "acr_login_server" {
  description = "Azure Container Registry login server URL"
  value       = azurerm_container_registry.main.login_server
}

output "acr_admin_username" {
  description = "ACR admin username (use for docker login)"
  value       = azurerm_container_registry.main.admin_username
  sensitive   = true
}

output "neo4j_bolt_uri" {
  description = "Neo4j Bolt URI"
  value       = "bolt://${azurerm_container_group.neo4j.ip_address}:7687"
}

output "neo4j_private_ip" {
  description = "Private IP address of the Neo4j container instance"
  value       = azurerm_container_group.neo4j.ip_address
}

output "chromadb_private_ip" {
  description = "Private IP address of the ChromaDB container instance"
  value       = azurerm_container_group.chromadb.ip_address
}

output "key_vault_uri" {
  description = "Key Vault URI"
  value       = azurerm_key_vault.main.vault_uri
}

output "app_insights_connection_string" {
  description = "Application Insights connection string for telemetry"
  value       = azurerm_application_insights.main.connection_string
  sensitive   = true
}
