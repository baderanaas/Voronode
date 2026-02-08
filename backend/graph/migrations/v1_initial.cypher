// Node Constraints
CREATE CONSTRAINT Project_id_unique IF NOT EXISTS FOR (n:Project) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT Contractor_id_unique IF NOT EXISTS FOR (n:Contractor) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT Contractor_license_number_unique IF NOT EXISTS FOR (n:Contractor) REQUIRE n.license_number IS UNIQUE;
CREATE CONSTRAINT Contract_id_unique IF NOT EXISTS FOR (n:Contract) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT Invoice_id_unique IF NOT EXISTS FOR (n:Invoice) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT Invoice_invoice_number_unique IF NOT EXISTS FOR (n:Invoice) REQUIRE n.invoice_number IS UNIQUE;
CREATE CONSTRAINT LineItem_id_unique IF NOT EXISTS FOR (n:LineItem) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT BudgetLine_id_unique IF NOT EXISTS FOR (n:BudgetLine) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT RiskFactor_id_unique IF NOT EXISTS FOR (n:RiskFactor) REQUIRE n.id IS UNIQUE;

// Indexes
CREATE INDEX Project_name_idx IF NOT EXISTS FOR (n:Project) ON (n.name);
CREATE INDEX Project_status_idx IF NOT EXISTS FOR (n:Project) ON (n.status);
CREATE INDEX Contractor_name_idx IF NOT EXISTS FOR (n:Contractor) ON (n.name);
CREATE INDEX Invoice_date_idx IF NOT EXISTS FOR (n:Invoice) ON (n.date);
CREATE INDEX Invoice_status_idx IF NOT EXISTS FOR (n:Invoice) ON (n.status);
CREATE INDEX LineItem_cost_code_idx IF NOT EXISTS FOR (n:LineItem) ON (n.cost_code);
CREATE INDEX BudgetLine_cost_code_idx IF NOT EXISTS FOR (n:BudgetLine) ON (n.cost_code);
CREATE INDEX RiskFactor_severity_idx IF NOT EXISTS FOR (n:RiskFactor) ON (n.severity);
