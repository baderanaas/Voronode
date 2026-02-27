variable "project_name" {
  description = "Project name used as prefix for all resources"
  type        = string
  default     = "voronode"
}

variable "location" {
  description = "Azure region for all resources"
  type        = string
  default     = "westeurope"
}

variable "resource_group_name" {
  description = "Name of the Azure resource group"
  type        = string
  default     = "rg-voronode-dev"
}

variable "acr_sku" {
  description = "SKU for Azure Container Registry"
  type        = string
  default     = "Basic"
}

# --- Secrets (sensitive) ---

variable "groq_api_key" {
  description = "Groq API key"
  type        = string
  sensitive   = true
}

variable "openai_api_key" {
  description = "OpenAI API key"
  type        = string
  sensitive   = true
}

variable "gemini_api_key" {
  description = "Google Gemini API key"
  type        = string
  sensitive   = true
}

variable "anthropic_api_key" {
  description = "Anthropic API key"
  type        = string
  sensitive   = true
}

variable "tavily_api_key" {
  description = "Tavily search API key (optional)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "neo4j_password" {
  description = "Neo4j database password"
  type        = string
  sensitive   = true
  default     = "voronode123"
}

variable "jwt_secret_key" {
  description = "JWT signing secret key"
  type        = string
  sensitive   = true
}

# --- LLM model names ---

variable "groq_model" {
  description = "Groq model for document extraction"
  type        = string
  default     = "llama-3.3-70b-versatile"
}

variable "openai_chat_model" {
  description = "OpenAI model for conversational agents"
  type        = string
  default     = "gpt-4o-mini"
}

variable "openai_embedding_model" {
  description = "OpenAI model for embeddings"
  type        = string
  default     = "text-embedding-3-small"
}

variable "gemini_model" {
  description = "Gemini model for planner agent"
  type        = string
  default     = "gemini-2.5-pro"
}

variable "anthropic_model" {
  description = "Anthropic model for Cypher query generation"
  type        = string
  default     = "claude-haiku-4-5-20251001"
}

# --- Container images (set after first ACR push) ---

variable "backend_image" {
  description = "Full image URI for backend container (e.g. voronodeacr.azurecr.io/backend:latest)"
  type        = string
  default     = ""
}

variable "frontend_image" {
  description = "Full image URI for frontend container (e.g. voronodeacr.azurecr.io/frontend:latest)"
  type        = string
  default     = ""
}
