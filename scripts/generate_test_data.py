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

    print(f"\n✅ Generated 10 test invoices in {invoices_dir}")


if __name__ == "__main__":
    main()
