"""Generate synthetic invoices, contracts, and budgets for testing"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from faker import Faker
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
import random
from datetime import datetime, timedelta
import json

fake = Faker()


def generate_invoice_pdf(output_path: Path, invoice_data: dict):
    """Create a PDF invoice using ReportLab"""
    c = canvas.Canvas(str(output_path), pagesize=letter)
    width, height = letter

    # Header
    c.setFont("Helvetica-Bold", 20)
    c.drawString(1 * inch, height - 1 * inch, "INVOICE")

    # Invoice details
    c.setFont("Helvetica", 12)
    y = height - 1.5 * inch
    c.drawString(1 * inch, y, f"Invoice Number: {invoice_data['invoice_number']}")
    y -= 0.3 * inch
    c.drawString(1 * inch, y, f"Date: {invoice_data['date']}")
    y -= 0.3 * inch
    c.drawString(1 * inch, y, f"Contractor: {invoice_data['contractor_name']}")
    y -= 0.3 * inch
    c.drawString(1 * inch, y, f"Project: {invoice_data['project_name']}")

    # Line items header
    y -= 0.5 * inch
    c.setFont("Helvetica-Bold", 12)
    c.drawString(1 * inch, y, "Description")
    c.drawString(4 * inch, y, "Qty")
    c.drawString(5 * inch, y, "Unit Price")
    c.drawString(6.5 * inch, y, "Total")

    # Line items
    c.setFont("Helvetica", 10)
    y -= 0.3 * inch
    for item in invoice_data["line_items"]:
        c.drawString(1 * inch, y, item["description"][:30])
        c.drawString(4 * inch, y, str(item["quantity"]))
        c.drawString(5 * inch, y, f"${item['unit_price']:.2f}")
        c.drawString(6.5 * inch, y, f"${item['total']:.2f}")
        y -= 0.25 * inch

    # Total
    y -= 0.3 * inch
    c.setFont("Helvetica-Bold", 14)
    c.drawString(5.5 * inch, y, f"TOTAL: ${invoice_data['total_amount']:.2f}")

    c.save()


# --- Static reference data for contracts, projects, contractors, budgets ---

PROJECTS = [
    {
        "id": "PRJ-001",
        "name": "South Alyssa Tower",
        "budget": 2500000.00,
        "start_date": "2025-06-01",
        "end_date": "2026-12-31",
        "status": "active",
    },
    {
        "id": "PRJ-002",
        "name": "West George Tower",
        "budget": 1800000.00,
        "start_date": "2025-08-01",
        "end_date": "2027-02-28",
        "status": "active",
    },
    {
        "id": "PRJ-003",
        "name": "Sheltonhaven Tower",
        "budget": 3200000.00,
        "start_date": "2025-04-15",
        "end_date": "2027-06-30",
        "status": "active",
    },
]

CONTRACTORS = [
    {"id": "CONT-001", "name": "Schultz LLC", "license_number": "LIC-2024-0001", "rating": 4.2},
    {"id": "CONT-002", "name": "Baxter LLC", "license_number": "LIC-2024-0002", "rating": 3.8},
    {"id": "CONT-003", "name": "Edwards-James", "license_number": "LIC-2024-0003", "rating": 4.5},
    {"id": "CONT-004", "name": "Paul, Kelley and Simmons", "license_number": "LIC-2024-0004", "rating": 3.5},
    {"id": "CONT-005", "name": "Gates Inc", "license_number": "LIC-2024-0005", "rating": 4.0},
    {"id": "CONT-006", "name": "Wolfe-Bennett", "license_number": "LIC-2024-0006", "rating": 4.1},
    {"id": "CONT-007", "name": "Vance-Church", "license_number": "LIC-2024-0007", "rating": 3.9},
    {"id": "CONT-008", "name": "Jones Ltd", "license_number": "LIC-2024-0008", "rating": 4.3},
    {"id": "CONT-009", "name": "Thompson-Sandoval", "license_number": "LIC-2024-0009", "rating": 3.7},
    {"id": "CONT-010", "name": "Holmes, Berry and Holt", "license_number": "LIC-2024-0010", "rating": 4.4},
]

CONTRACTS = [
    {
        "contract_id": "CONTRACT-001",
        "contractor_id": "CONT-001",
        "project_id": "PRJ-001",
        "value": 250000.00,
        "retention_rate": 0.10,
        "start_date": "2025-06-01",
        "end_date": "2026-12-31",
        "terms": "Standard construction contract for structural, electrical, site prep, and plumbing work on South Alyssa Tower. Retention of 10% applies to all progress payments.",
        "unit_price_schedule": {"01-100": 450.00, "05-500": 460.00, "15-100": 250.00, "16-100": 400.00},
        "approved_cost_codes": ["01-100", "05-500", "15-100", "16-100"],
    },
    {
        "contract_id": "CONTRACT-002",
        "contractor_id": "CONT-002",
        "project_id": "PRJ-002",
        "value": 180000.00,
        "retention_rate": 0.05,
        "start_date": "2025-08-01",
        "end_date": "2027-02-28",
        "terms": "Site preparation, structural steel, and painting contract for West George Tower. 5% retention on all invoices.",
        "unit_price_schedule": {"01-100": 450.00, "05-500": 300.00, "09-900": 350.00},
        "approved_cost_codes": ["01-100", "05-500", "09-900"],
    },
    {
        "contract_id": "CONTRACT-003",
        "contractor_id": "CONT-003",
        "project_id": "PRJ-001",
        "value": 200000.00,
        "retention_rate": 0.10,
        "start_date": "2025-07-01",
        "end_date": "2026-12-31",
        "terms": "Electrical and structural steel contract for South Alyssa Tower. Scope limited to electrical and steel work only. 10% retention applies.",
        "unit_price_schedule": {"05-500": 450.00, "16-100": 350.00},
        "approved_cost_codes": ["05-500", "16-100"],
    },
    {
        "contract_id": "CONTRACT-004",
        "contractor_id": "CONT-004",
        "project_id": "PRJ-003",
        "value": 300000.00,
        "retention_rate": 0.10,
        "start_date": "2025-04-15",
        "end_date": "2027-06-30",
        "terms": "Concrete and painting contract for Sheltonhaven Tower. All concrete unit prices capped per schedule. 10% retention on progress payments.",
        "unit_price_schedule": {"03-300": 450.00, "09-900": 425.00},
        "approved_cost_codes": ["03-300", "09-900"],
    },
    {
        "contract_id": "CONTRACT-005",
        "contractor_id": "CONT-005",
        "project_id": "PRJ-003",
        "value": 120000.00,
        "retention_rate": 0.05,
        "start_date": "2025-05-01",
        "end_date": "2027-06-30",
        "terms": "Concrete, structural steel, and plumbing contract for Sheltonhaven Tower. Billing cap of $120,000. 5% retention applies.",
        "unit_price_schedule": {"03-300": 400.00, "05-500": 460.00, "15-100": 250.00},
        "approved_cost_codes": ["03-300", "05-500", "15-100"],
    },
]

BUDGETS = {
    "PRJ-001": [
        {"id": "BUD-001-01", "project_id": "PRJ-001", "cost_code": "01-100", "description": "Site Preparation", "allocated": 400000.00, "spent": 145000.00, "remaining": 255000.00},
        {"id": "BUD-001-02", "project_id": "PRJ-001", "cost_code": "05-500", "description": "Structural Steel", "allocated": 800000.00, "spent": 310000.00, "remaining": 490000.00},
        {"id": "BUD-001-03", "project_id": "PRJ-001", "cost_code": "15-100", "description": "Plumbing", "allocated": 350000.00, "spent": 88000.00, "remaining": 262000.00},
        {"id": "BUD-001-04", "project_id": "PRJ-001", "cost_code": "16-100", "description": "Electrical", "allocated": 600000.00, "spent": 420000.00, "remaining": 180000.00},
    ],
    "PRJ-002": [
        {"id": "BUD-002-01", "project_id": "PRJ-002", "cost_code": "01-100", "description": "Site Preparation", "allocated": 300000.00, "spent": 95000.00, "remaining": 205000.00},
        {"id": "BUD-002-02", "project_id": "PRJ-002", "cost_code": "05-500", "description": "Structural Steel", "allocated": 500000.00, "spent": 185000.00, "remaining": 315000.00},
        {"id": "BUD-002-03", "project_id": "PRJ-002", "cost_code": "09-900", "description": "Painting", "allocated": 250000.00, "spent": 232000.00, "remaining": 18000.00},
    ],
    "PRJ-003": [
        {"id": "BUD-003-01", "project_id": "PRJ-003", "cost_code": "03-300", "description": "Concrete Work", "allocated": 900000.00, "spent": 540000.00, "remaining": 360000.00},
        {"id": "BUD-003-02", "project_id": "PRJ-003", "cost_code": "05-500", "description": "Structural Steel", "allocated": 750000.00, "spent": 290000.00, "remaining": 460000.00},
        {"id": "BUD-003-03", "project_id": "PRJ-003", "cost_code": "09-900", "description": "Painting", "allocated": 350000.00, "spent": 110000.00, "remaining": 240000.00},
        {"id": "BUD-003-04", "project_id": "PRJ-003", "cost_code": "15-100", "description": "Plumbing", "allocated": 400000.00, "spent": 385000.00, "remaining": 15000.00},
    ],
}


def generate_contract_pdf(output_path: Path, contract_data: dict):
    """Create a PDF contract document using ReportLab."""
    c = canvas.Canvas(str(output_path), pagesize=letter)
    width, height = letter

    # Find contractor and project names from reference data
    contractor_name = "Unknown Contractor"
    for cont in CONTRACTORS:
        if cont["id"] == contract_data["contractor_id"]:
            contractor_name = cont["name"]
            break

    project_name = "Unknown Project"
    for proj in PROJECTS:
        if proj["id"] == contract_data["project_id"]:
            project_name = proj["name"]
            break

    # Header
    c.setFont("Helvetica-Bold", 20)
    c.drawString(1 * inch, height - 1 * inch, "CONSTRUCTION CONTRACT")

    c.setFont("Helvetica-Bold", 14)
    y = height - 1.4 * inch
    c.drawString(1 * inch, y, f"Contract ID: {contract_data['contract_id']}")

    # Parties
    y -= 0.5 * inch
    c.setFont("Helvetica-Bold", 12)
    c.drawString(1 * inch, y, "PARTIES")
    c.setFont("Helvetica", 11)
    y -= 0.3 * inch
    c.drawString(1 * inch, y, f"Contractor: {contractor_name} ({contract_data['contractor_id']})")
    y -= 0.25 * inch
    c.drawString(1 * inch, y, f"Project: {project_name} ({contract_data['project_id']})")

    # Contract Value and Dates
    y -= 0.4 * inch
    c.setFont("Helvetica-Bold", 12)
    c.drawString(1 * inch, y, "CONTRACT DETAILS")
    c.setFont("Helvetica", 11)
    y -= 0.3 * inch
    c.drawString(1 * inch, y, f"Contract Value: ${contract_data['value']:,.2f}")
    y -= 0.25 * inch
    c.drawString(1 * inch, y, f"Start Date: {contract_data['start_date']}")
    y -= 0.25 * inch
    c.drawString(1 * inch, y, f"End Date: {contract_data['end_date']}")

    # Scope of Work
    y -= 0.4 * inch
    c.setFont("Helvetica-Bold", 12)
    c.drawString(1 * inch, y, "SCOPE OF WORK")
    c.setFont("Helvetica", 11)
    y -= 0.3 * inch

    cost_code_names = {
        "01-100": "Site Preparation",
        "03-300": "Concrete Work",
        "05-500": "Structural Steel",
        "06-100": "Rough Carpentry",
        "09-900": "Painting",
        "15-100": "Plumbing",
        "16-100": "Electrical",
    }

    c.drawString(1 * inch, y, "Approved Cost Codes:")
    y -= 0.25 * inch
    for code in contract_data.get("approved_cost_codes", []):
        desc = cost_code_names.get(code, "Other")
        c.drawString(1.3 * inch, y, f"- {code}: {desc}")
        y -= 0.2 * inch

    # Unit Price Schedule
    schedule = contract_data.get("unit_price_schedule", {})
    if schedule:
        y -= 0.3 * inch
        c.setFont("Helvetica-Bold", 12)
        c.drawString(1 * inch, y, "UNIT PRICE SCHEDULE")
        c.setFont("Helvetica-Bold", 10)
        y -= 0.3 * inch
        c.drawString(1 * inch, y, "Cost Code")
        c.drawString(2.5 * inch, y, "Description")
        c.drawString(5 * inch, y, "Max Unit Price")

        c.setFont("Helvetica", 10)
        y -= 0.25 * inch
        for code, price in schedule.items():
            desc = cost_code_names.get(code, "Other")
            c.drawString(1 * inch, y, code)
            c.drawString(2.5 * inch, y, desc)
            c.drawString(5 * inch, y, f"${price:,.2f}")
            y -= 0.2 * inch

    # Payment Terms
    y -= 0.3 * inch
    c.setFont("Helvetica-Bold", 12)
    c.drawString(1 * inch, y, "PAYMENT TERMS")
    c.setFont("Helvetica", 11)
    y -= 0.3 * inch
    retention_pct = contract_data["retention_rate"] * 100
    c.drawString(1 * inch, y, f"Retention Rate: {retention_pct:.0f}%")
    y -= 0.25 * inch
    c.drawString(
        1 * inch, y,
        f"A retention of {retention_pct:.0f}% shall be withheld from each progress payment"
    )
    y -= 0.25 * inch
    c.drawString(1 * inch, y, "until substantial completion of the work.")

    # General Terms
    y -= 0.4 * inch
    c.setFont("Helvetica-Bold", 12)
    c.drawString(1 * inch, y, "GENERAL TERMS")
    c.setFont("Helvetica", 10)
    y -= 0.3 * inch

    terms_text = contract_data.get("terms", "")
    # Wrap long terms text
    max_chars = 80
    while terms_text and y > 1 * inch:
        line = terms_text[:max_chars]
        if len(terms_text) > max_chars:
            # Break at last space
            space_idx = line.rfind(" ")
            if space_idx > 0:
                line = terms_text[:space_idx]
                terms_text = terms_text[space_idx + 1:]
            else:
                terms_text = terms_text[max_chars:]
        else:
            terms_text = ""
        c.drawString(1 * inch, y, line)
        y -= 0.2 * inch

    c.save()


def generate_projects(fixtures_dir: Path):
    """Write projects.json fixture."""
    path = fixtures_dir / "projects.json"
    with open(path, "w") as f:
        json.dump(PROJECTS, f, indent=2)
    print(f"Generated: {path.name} ({len(PROJECTS)} projects)")


def generate_contractors(fixtures_dir: Path):
    """Write contractors.json fixture."""
    path = fixtures_dir / "contractors.json"
    with open(path, "w") as f:
        json.dump(CONTRACTORS, f, indent=2)
    print(f"Generated: {path.name} ({len(CONTRACTORS)} contractors)")


def generate_contracts(contracts_dir: Path):
    """Write individual contract JSON fixtures."""
    for contract in CONTRACTS:
        path = contracts_dir / f"{contract['contract_id']}.json"
        with open(path, "w") as f:
            json.dump(contract, f, indent=2)
        print(f"Generated: {path.name}")
    print(f"  -> {len(CONTRACTS)} contracts in {contracts_dir}")


def generate_budgets(budgets_dir: Path):
    """Write per-project budget JSON fixtures."""
    for project_id, lines in BUDGETS.items():
        path = budgets_dir / f"{project_id}-budgets.json"
        with open(path, "w") as f:
            json.dump(lines, f, indent=2)
        print(f"Generated: {path.name} ({len(lines)} budget lines)")


def main():
    fixtures_dir = Path(__file__).parent.parent / "backend/tests/fixtures"
    invoices_dir = fixtures_dir / "invoices"
    contracts_dir = fixtures_dir / "contracts"
    budgets_dir = fixtures_dir / "budgets"

    # Create directories
    invoices_dir.mkdir(parents=True, exist_ok=True)
    contracts_dir.mkdir(parents=True, exist_ok=True)
    budgets_dir.mkdir(parents=True, exist_ok=True)

    # Cost codes for construction
    cost_codes = [
        ("01-100", "Site Preparation"),
        ("03-300", "Concrete Work"),
        ("05-500", "Structural Steel"),
        ("06-100", "Rough Carpentry"),
        ("09-900", "Painting"),
        ("15-100", "Plumbing"),
        ("16-100", "Electrical"),
    ]

    # Generate 10 invoices
    for i in range(1, 11):
        invoice_number = f"INV-2024-{i:04d}"
        contractor_name = fake.company()
        project_name = f"Project {fake.city()} Tower"

        # Random line items
        line_items = []
        for _ in range(random.randint(2, 5)):
            cost_code, description = random.choice(cost_codes)
            qty = random.randint(1, 100)
            unit_price = round(random.uniform(50, 500), 2)
            total = round(qty * unit_price, 2)

            line_items.append(
                {
                    "cost_code": cost_code,
                    "description": description,
                    "quantity": qty,
                    "unit_price": unit_price,
                    "total": total,
                }
            )

        invoice_data = {
            "invoice_number": invoice_number,
            "date": (datetime.now() - timedelta(days=random.randint(1, 60))).strftime(
                "%Y-%m-%d"
            ),
            "contractor_name": contractor_name,
            "project_name": project_name,
            "line_items": line_items,
            "total_amount": sum(item["total"] for item in line_items),
        }

        # Generate PDF
        pdf_path = invoices_dir / f"{invoice_number}.pdf"
        generate_invoice_pdf(pdf_path, invoice_data)

        # Save metadata as JSON
        json_path = invoices_dir / f"{invoice_number}.json"
        with open(json_path, "w") as f:
            json.dump(invoice_data, f, indent=2)

        print(f"Generated: {pdf_path.name}")

    print(f"\nGenerated 10 test invoices in {invoices_dir}")

    # Generate contracts, projects, contractors, budgets
    generate_projects(fixtures_dir)
    generate_contractors(fixtures_dir)
    generate_contracts(contracts_dir)
    generate_budgets(budgets_dir)

    # Generate contract PDFs
    for contract in CONTRACTS:
        pdf_path = contracts_dir / f"{contract['contract_id']}.pdf"
        generate_contract_pdf(pdf_path, contract)
        print(f"Generated: {pdf_path.name}")

    print(f"\nGenerated {len(CONTRACTS)} contract PDFs in {contracts_dir}")

    print(f"\nAll fixtures generated in {fixtures_dir}")


if __name__ == "__main__":
    main()
