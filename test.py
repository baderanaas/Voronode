import requests, json

with open("backend/tests/fixtures/invoices/INV-2024-0001.pdf", "rb") as f:
    r = requests.post(
        "http://localhost:8080/api/chat",
        data={"message": "", "conversation_id": ""},
        files=[("files", ("INV-2024-0001.pdf", f, "application/pdf"))],
    )
print(r.json()["response"])
