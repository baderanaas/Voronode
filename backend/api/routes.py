"""API routes for invoice processing."""

import time
import tempfile
from pathlib import Path
from datetime import datetime
from typing import List

from fastapi import APIRouter, UploadFile, File, HTTPException
import structlog

from backend.api.schemas import (
    InvoiceUploadResponse,
    InvoiceDetailResponse,
    HealthResponse,
    ValidationAnomalyResponse,
    LineItemResponse,
    WorkflowStatusResponse,
    QuarantinedWorkflowResponse,
    WorkflowResumeRequest,
    ContractUploadResponse,
    ContractDetailResponse,
    BudgetUploadResponse,
    BudgetDetailResponse,
    BudgetVarianceResponse,
    BudgetLineResponse,
    ChatRequest,
    ChatResponse,
)
from backend.agents.extractor import InvoiceExtractor
from backend.agents.validator import InvoiceValidator
from backend.agents.contract_extractor import ContractExtractor
from backend.services.graph_builder import GraphBuilder
from backend.services.workflow_manager import WorkflowManager
from backend.vector.client import ChromaDBClient
from backend.graph.client import Neo4jClient
from backend.core.config import settings

logger = structlog.get_logger()

router = APIRouter()

# Initialize services (lazy loading in production would be better)
extractor = InvoiceExtractor()
validator = InvoiceValidator()
graph_builder = GraphBuilder()
chroma_client = ChromaDBClient()
workflow_manager = WorkflowManager()  # Phase 3
contract_extractor = ContractExtractor()


@router.post("/invoices/upload", response_model=InvoiceUploadResponse)
async def upload_invoice(file: UploadFile = File(...)):
    """
    Upload and process an invoice PDF.

    Pipeline:
    1. Save uploaded file to temp
    2. Extract with InvoiceExtractor
    3. Validate with InvoiceValidator
    4. Insert with GraphBuilder
    5. Embed text in ChromaDB
    6. Return JSON response
    """
    start_time = time.time()

    logger.info("invoice_upload_started", filename=file.filename)

    # Validate file type
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    # Check file size
    file.file.seek(0, 2)  # Seek to end
    file_size = file.file.tell()
    file.file.seek(0)  # Reset to start

    if file_size > settings.api_upload_max_size:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {settings.api_upload_max_size} bytes",
        )

    temp_file_path = None

    try:
        # Step 1: Save to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_file_path = Path(temp_file.name)

        logger.info("temp_file_created", path=str(temp_file_path))

        # Step 2: Extract invoice
        invoice = extractor.extract_invoice_from_pdf(temp_file_path)

        # Step 3: Validate invoice
        anomalies = validator.validate_invoice(invoice)

        # Convert anomalies to response models
        anomaly_responses = [
            ValidationAnomalyResponse(**anomaly.to_dict()) for anomaly in anomalies
        ]

        # Check for blocking anomalies (high severity)
        high_severity_count = sum(1 for a in anomalies if a.severity == "high")

        if high_severity_count > 0:
            logger.warning(
                "invoice_has_high_severity_anomalies",
                invoice_number=invoice.invoice_number,
                count=high_severity_count,
            )

        # Step 4: Insert into Neo4j
        invoice_id = graph_builder.insert_invoice(invoice)

        # Step 5: Embed in ChromaDB
        try:
            # Create searchable text from invoice
            invoice_text = f"""
            Invoice: {invoice.invoice_number}
            Date: {invoice.date}
            Contractor: {invoice.contractor_id}
            Amount: ${invoice.amount}

            Line Items:
            """
            for item in invoice.line_items:
                invoice_text += f"\n- {item.cost_code}: {item.description} (${item.total})"

            chroma_client.add_document(
                collection_name="invoices",
                doc_id=invoice_id,
                text=invoice_text,
                metadata={
                    "invoice_number": invoice.invoice_number,
                    "date": str(invoice.date),
                    "amount": float(invoice.amount),
                    "contractor_id": invoice.contractor_id,
                },
            )

            logger.info("invoice_embedded", invoice_id=invoice_id)

        except Exception as e:
            # Don't fail the entire upload if embedding fails
            logger.warning("chromadb_embedding_failed", error=str(e))

        # Calculate processing time
        processing_time = time.time() - start_time

        logger.info(
            "invoice_upload_complete",
            invoice_id=invoice_id,
            processing_time=processing_time,
            anomalies=len(anomalies),
        )

        return InvoiceUploadResponse(
            success=True,
            message=f"Invoice {invoice.invoice_number} processed successfully",
            invoice_id=invoice_id,
            invoice_number=invoice.invoice_number,
            amount=invoice.amount,
            line_items_count=len(invoice.line_items),
            validation_anomalies=anomaly_responses,
            processing_time_seconds=round(processing_time, 2),
        )

    except Exception as e:
        logger.error("invoice_upload_failed", error=str(e), filename=file.filename)

        return InvoiceUploadResponse(
            success=False,
            message=f"Failed to process invoice: {str(e)}",
            processing_time_seconds=round(time.time() - start_time, 2),
        )

    finally:
        # Clean up temp file
        if temp_file_path and temp_file_path.exists():
            temp_file_path.unlink()
            logger.debug("temp_file_deleted", path=str(temp_file_path))


@router.get("/invoices/{invoice_id}", response_model=InvoiceDetailResponse)
async def get_invoice(invoice_id: str):
    """
    Get invoice details by ID.

    Args:
        invoice_id: Invoice ID from Neo4j

    Returns:
        Invoice with line items
    """
    logger.info("invoice_detail_requested", invoice_id=invoice_id)

    try:
        invoice_data = graph_builder.get_invoice_by_id(invoice_id)

        if not invoice_data:
            raise HTTPException(status_code=404, detail="Invoice not found")

        # Convert to response model
        line_items = [LineItemResponse(**item) for item in invoice_data["line_items"]]

        response = InvoiceDetailResponse(
            id=invoice_data["id"],
            invoice_number=invoice_data["invoice_number"],
            date=invoice_data["date"],
            due_date=invoice_data["due_date"],
            amount=invoice_data["amount"],
            status=invoice_data["status"],
            contractor_name=invoice_data["contractor_name"],
            line_items=line_items,
        )

        logger.info("invoice_detail_retrieved", invoice_id=invoice_id)
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error("invoice_detail_failed", invoice_id=invoice_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to retrieve invoice: {e}")


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Check service connectivity.

    Returns:
        Status of Neo4j and ChromaDB connections
    """
    neo4j_client = Neo4jClient()

    services_status = {
        "neo4j": neo4j_client.verify_connectivity(),
        "chromadb": chroma_client.verify_connectivity(),
    }

    overall_status = "healthy" if all(services_status.values()) else "degraded"

    logger.info("health_check", status=overall_status, services=services_status)

    return HealthResponse(
        status=overall_status, services=services_status, timestamp=datetime.utcnow()
    )


# Phase 3: LangGraph Workflow Endpoints

@router.post("/invoices/upload-graph", response_model=InvoiceUploadResponse)
async def upload_invoice_with_workflow(file: UploadFile = File(...)):
    """
    Upload and process an invoice PDF using LangGraph workflow.

    Pipeline (with conditional routing):
    1. Extract text from PDF
    2. Structure invoice with LLM (retry with critic if needed)
    3. Validate invoice (quarantine if high risk)
    4. Insert into Neo4j graph
    5. Embed in ChromaDB
    6. Return response (or quarantine for review)
    """
    start_time = time.time()

    logger.info("invoice_upload_graph_started", filename=file.filename)

    # Validate file type
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    # Check file size
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)

    if file_size > settings.api_upload_max_size:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {settings.api_upload_max_size} bytes",
        )

    temp_file_path = None

    try:
        # Save to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_file_path = Path(temp_file.name)

        logger.info("temp_file_created", path=str(temp_file_path))

        # Execute LangGraph workflow
        final_state = workflow_manager.execute_sync(temp_file_path)

        # Extract response data
        extracted_data = final_state.get("extracted_data", {})
        anomaly_dicts = final_state.get("anomalies", [])

        # Convert anomalies to response models
        anomaly_responses = [
            ValidationAnomalyResponse(**a) for a in anomaly_dicts
        ]

        # Check if workflow was quarantined
        is_quarantined = final_state.get("status") == "quarantined"

        # Calculate processing time
        processing_time = time.time() - start_time

        logger.info(
            "invoice_upload_graph_complete",
            document_id=final_state["document_id"],
            status=final_state.get("status"),
            processing_time=processing_time,
        )

        return InvoiceUploadResponse(
            success=final_state.get("status") in ["completed", "quarantined"],
            message=(
                f"Invoice {extracted_data.get('invoice_number', 'N/A')} requires human review"
                if is_quarantined
                else f"Invoice {extracted_data.get('invoice_number', 'N/A')} processed successfully"
            ),
            invoice_id=final_state.get("neo4j_id"),
            invoice_number=extracted_data.get("invoice_number"),
            amount=extracted_data.get("total_amount"),
            line_items_count=len(extracted_data.get("line_items", [])),
            validation_anomalies=anomaly_responses,
            processing_time_seconds=round(processing_time, 2),
            workflow_id=final_state["document_id"],
            retry_count=final_state.get("retry_count", 0),
            risk_level=final_state.get("risk_level"),
            requires_review=is_quarantined,
        )

    except Exception as e:
        logger.error("invoice_upload_graph_failed", error=str(e), filename=file.filename)

        return InvoiceUploadResponse(
            success=False,
            message=f"Failed to process invoice: {str(e)}",
            processing_time_seconds=round(time.time() - start_time, 2),
        )

    finally:
        # Clean up temp file
        if temp_file_path and temp_file_path.exists():
            temp_file_path.unlink()
            logger.debug("temp_file_deleted", path=str(temp_file_path))


@router.get("/workflows/quarantined", response_model=List[QuarantinedWorkflowResponse])
async def get_quarantined_workflows():
    """
    Get all workflows awaiting human review.

    Returns:
        List of quarantined workflows
    """
    logger.info("quarantined_workflows_requested")

    try:
        workflows = workflow_manager.get_quarantined_workflows()

        responses = []
        for wf in workflows:
            state = wf["state"]
            anomaly_dicts = state.get("anomalies", [])

            responses.append(
                QuarantinedWorkflowResponse(
                    document_id=wf["document_id"],
                    status=wf["status"],
                    risk_level=wf["risk_level"],
                    retry_count=wf["retry_count"],
                    pause_reason=state.get("pause_reason"),
                    anomalies=[ValidationAnomalyResponse(**a) for a in anomaly_dicts],
                    created_at=wf["created_at"],
                    updated_at=wf["updated_at"],
                )
            )

        logger.info("quarantined_workflows_retrieved", count=len(responses))

        return responses

    except Exception as e:
        logger.error("quarantined_workflows_failed", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve quarantined workflows: {e}"
        )


@router.post("/workflows/{document_id}/resume", response_model=InvoiceUploadResponse)
async def resume_workflow(document_id: str, request: WorkflowResumeRequest):
    """
    Resume a quarantined workflow with human feedback.

    Args:
        document_id: Workflow document ID
        request: Human feedback (approved/corrections)

    Returns:
        Final processing result
    """
    logger.info(
        "workflow_resume_requested",
        document_id=document_id,
        approved=request.approved,
    )

    try:
        # Build feedback dictionary
        human_feedback = {
            "approved": request.approved,
            "corrections": request.corrections or {},
            "notes": request.notes,
        }

        # Resume workflow
        final_state = workflow_manager.resume_workflow(document_id, human_feedback)

        # Extract response data
        extracted_data = final_state.get("extracted_data", {})
        anomaly_dicts = final_state.get("anomalies", [])

        anomaly_responses = [
            ValidationAnomalyResponse(**a) for a in anomaly_dicts
        ]

        return InvoiceUploadResponse(
            success=final_state.get("status") == "completed",
            message=f"Workflow resumed: {final_state.get('status')}",
            invoice_id=final_state.get("neo4j_id"),
            invoice_number=extracted_data.get("invoice_number"),
            amount=extracted_data.get("total_amount"),
            line_items_count=len(extracted_data.get("line_items", [])),
            validation_anomalies=anomaly_responses,
            processing_time_seconds=final_state.get("processing_time_ms", 0) / 1000.0,
            workflow_id=document_id,
            retry_count=final_state.get("retry_count", 0),
            risk_level=final_state.get("risk_level"),
            requires_review=False,
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("workflow_resume_failed", document_id=document_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to resume workflow: {e}")


@router.get("/workflows/{document_id}/status", response_model=WorkflowStatusResponse)
async def get_workflow_status(document_id: str):
    """
    Get current workflow status.

    Args:
        document_id: Workflow document ID

    Returns:
        Workflow status
    """
    logger.info("workflow_status_requested", document_id=document_id)

    try:
        workflow = workflow_manager.get_workflow_status(document_id)

        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

        return WorkflowStatusResponse(
            document_id=workflow["document_id"],
            status=workflow["status"],
            paused=workflow["paused"],
            risk_level=workflow["risk_level"],
            retry_count=workflow["retry_count"],
            created_at=workflow["created_at"],
            updated_at=workflow["updated_at"],
            state=workflow["state"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("workflow_status_failed", document_id=document_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get workflow status: {e}")


@router.get("/workflows")
async def list_workflows(status: str = None, limit: int = 100):
    """
    List all workflows, optionally filtered by status.

    Args:
        status: Optional status filter (completed, quarantined, processing, failed)
        limit: Maximum number of workflows to return

    Returns:
        List of workflows
    """
    logger.info("workflows_list_requested", status=status, limit=limit)

    try:
        workflows = workflow_manager.list_workflows(status=status, limit=limit)
        return workflows

    except Exception as e:
        logger.error("workflows_list_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to list workflows: {e}")


@router.get("/workflows/{workflow_id}")
async def get_workflow(workflow_id: str):
    """
    Get detailed workflow information by ID.

    Args:
        workflow_id: Workflow ID (document_id)

    Returns:
        Complete workflow state and metadata
    """
    logger.info("workflow_get_requested", workflow_id=workflow_id)

    try:
        workflow = workflow_manager.get_workflow_status(workflow_id)

        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

        return workflow

    except HTTPException:
        raise
    except Exception as e:
        logger.error("workflow_get_failed", workflow_id=workflow_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get workflow: {e}")


@router.get("/graph/stats")
async def get_graph_stats():
    """
    Get Neo4j graph database statistics.

    Returns:
        Node counts, relationship counts, and other graph metrics
    """
    logger.info("graph_stats_requested")

    try:
        neo4j_client = Neo4jClient()

        # Count nodes by label
        node_counts_query = """
        MATCH (n)
        RETURN labels(n)[0] as label, count(*) as count
        """
        node_results = neo4j_client.run_query(node_counts_query)

        # Count relationships
        rel_count_query = """
        MATCH ()-[r]->()
        RETURN count(r) as count
        """
        rel_results = neo4j_client.run_query(rel_count_query)

        # Build response
        stats = {
            "total_nodes": sum(r["count"] for r in node_results),
            "total_relationships": rel_results[0]["count"] if rel_results else 0,
        }

        # Add individual node type counts
        for result in node_results:
            label = result["label"]
            count = result["count"]
            stats[f"{label.lower()}_count"] = count

        logger.info("graph_stats_retrieved", stats=stats)
        return stats

    except Exception as e:
        logger.error("graph_stats_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get graph stats: {e}")


@router.post("/contracts/upload", response_model=ContractUploadResponse)
async def upload_contract(file: UploadFile = File(...)):
    """
    Upload and process a contract PDF.

    Pipeline:
    1. Save uploaded file to temp
    2. Extract with ContractExtractor (pdfplumber + Groq/Llama3)
    3. Validate extracted terms
    4. Insert into Neo4j graph
    5. Return extracted contract data
    """
    start_time = time.time()

    logger.info("contract_upload_started", filename=file.filename)

    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)

    if file_size > settings.api_upload_max_size:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {settings.api_upload_max_size} bytes",
        )

    temp_file_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_file_path = Path(temp_file.name)

        logger.info("temp_file_created", path=str(temp_file_path))

        # Extract raw text and structure with LLM
        raw_text = contract_extractor._extract_text_from_pdf(temp_file_path)
        contract_data = contract_extractor.structure_contract(raw_text)

        # Validate and collect warnings
        warnings = contract_extractor.validate_extracted_contract(contract_data)

        # Build Contract model (reuses the structured data)
        contract = contract_extractor._build_contract_model(contract_data, warnings)

        # Insert into Neo4j
        contract_id = graph_builder.insert_contract(contract)

        processing_time = time.time() - start_time

        logger.info(
            "contract_upload_complete",
            contract_id=contract_id,
            processing_time=processing_time,
        )

        return ContractUploadResponse(
            success=True,
            message=f"Contract {contract.id} processed successfully",
            contract_id=contract.id,
            contractor_name=contract.contractor_name,
            project_name=contract.project_name,
            value=contract.value,
            retention_rate=contract.retention_rate,
            start_date=contract.start_date,
            end_date=contract.end_date,
            approved_cost_codes=contract.approved_cost_codes,
            unit_price_schedule={k: float(v) for k, v in contract.unit_price_schedule.items()},
            extraction_warnings=warnings,
            processing_time_seconds=round(processing_time, 2),
        )

    except Exception as e:
        logger.error("contract_upload_failed", error=str(e), filename=file.filename)

        return ContractUploadResponse(
            success=False,
            message=f"Failed to process contract: {str(e)}",
            processing_time_seconds=round(time.time() - start_time, 2),
        )

    finally:
        if temp_file_path and temp_file_path.exists():
            temp_file_path.unlink()
            logger.debug("temp_file_deleted", path=str(temp_file_path))


@router.get("/contracts/{contract_id}", response_model=ContractDetailResponse)
async def get_contract(contract_id: str):
    """
    Get contract details by ID.

    Args:
        contract_id: Contract ID

    Returns:
        Contract details
    """
    logger.info("contract_detail_requested", contract_id=contract_id)

    try:
        contract_data = graph_builder.get_contract_by_id(contract_id)

        if not contract_data:
            raise HTTPException(status_code=404, detail="Contract not found")

        return ContractDetailResponse(**contract_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("contract_detail_failed", contract_id=contract_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to retrieve contract: {e}")


@router.post("/budgets/upload", response_model=BudgetUploadResponse)
async def upload_budget(file: UploadFile = File(...)):
    """
    Upload and process a budget Excel/CSV file.

    Pipeline:
    1. Save uploaded file to temp
    2. Extract with BudgetExtractor (pandas + Groq/Llama3)
    3. Validate budget data
    4. Insert into Neo4j graph
    5. Return budget summary

    Args:
        file: Excel (.xlsx, .xls) or CSV file

    Returns:
        Budget upload response with summary
    """
    start_time = time.time()

    logger.info("budget_upload_started", filename=file.filename)

    # Validate file type
    if not file.filename.endswith((".xlsx", ".xls", ".csv")):
        raise HTTPException(
            status_code=400,
            detail="Only Excel (.xlsx, .xls) and CSV (.csv) files are supported"
        )

    # Check file size
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)

    if file_size > settings.api_upload_max_size:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {settings.api_upload_max_size} bytes",
        )

    temp_file_path = None

    try:
        # Save to temp file
        suffix = Path(file.filename).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_file_path = Path(temp_file.name)

        logger.info("temp_file_created", path=str(temp_file_path))

        # Extract budget data
        from backend.agents.budget_extractor import BudgetExtractor
        extractor = BudgetExtractor()
        budget_data = extractor.extract_and_validate(temp_file_path)

        # Build Budget and BudgetLine models
        from backend.core.models import Budget, BudgetLine

        budget = Budget(
            id=budget_data["budget_id"] if "budget_id" in budget_data else budget_data["project_id"] + "-BUD-001",
            project_id=budget_data["project_id"],
            project_name=budget_data["project_name"],
            total_allocated=budget_data["metadata"]["total_allocated"],
            total_spent=budget_data["metadata"]["total_spent"],
            total_remaining=budget_data["metadata"]["total_allocated"] - budget_data["metadata"]["total_spent"],
            line_count=budget_data["metadata"]["line_count"],
            extracted_at=datetime.fromisoformat(budget_data["metadata"]["extracted_at"]),
            validation_warnings=budget_data["metadata"]["validation_warnings"],
        )

        budget_lines = [
            BudgetLine(**line_data) for line_data in budget_data["budget_lines"]
        ]

        # Insert into Neo4j
        budget_id = graph_builder.insert_budget(budget, budget_lines)

        processing_time = time.time() - start_time

        logger.info(
            "budget_upload_complete",
            budget_id=budget_id,
            processing_time=processing_time,
        )

        return BudgetUploadResponse(
            success=True,
            message=f"Budget for {budget.project_name} processed successfully",
            budget_id=budget.id,
            project_id=budget.project_id,
            project_name=budget.project_name,
            total_allocated=float(budget.total_allocated),
            total_spent=float(budget.total_spent),
            total_remaining=float(budget.total_remaining),
            line_count=budget.line_count,
            validation_warnings=budget.validation_warnings,
            processing_time_seconds=round(processing_time, 2),
        )

    except Exception as e:
        logger.error("budget_upload_failed", error=str(e), filename=file.filename)

        return BudgetUploadResponse(
            success=False,
            message=f"Failed to process budget: {str(e)}",
            processing_time_seconds=round(time.time() - start_time, 2),
        )

    finally:
        if temp_file_path and temp_file_path.exists():
            temp_file_path.unlink()
            logger.debug("temp_file_deleted", path=str(temp_file_path))


@router.get("/budgets/{budget_id}", response_model=BudgetDetailResponse)
async def get_budget(budget_id: str):
    """
    Get budget details by ID.

    Args:
        budget_id: Budget ID

    Returns:
        Budget details with all budget lines
    """
    logger.info("budget_detail_requested", budget_id=budget_id)

    try:
        budget_data = graph_builder.get_budget_by_id(budget_id)

        if not budget_data:
            raise HTTPException(status_code=404, detail="Budget not found")

        # Convert budget lines to response format
        from backend.api.schemas import BudgetLineResponse

        budget_lines = [
            BudgetLineResponse(
                id=line["id"],
                cost_code=line["cost_code"],
                description=line["description"],
                allocated=line["allocated"],
                spent=line["spent"],
                remaining=line["remaining"],
                variance_percent=(
                    ((line["spent"] - line["allocated"]) / line["allocated"] * 100)
                    if line["allocated"] > 0 else 0
                ),
            )
            for line in budget_data["budget_lines"]
        ]

        return BudgetDetailResponse(
            id=budget_data["id"],
            project_id=budget_data["project_id"],
            project_name=budget_data["project_name"],
            total_allocated=budget_data["total_allocated"],
            total_spent=budget_data["total_spent"],
            total_remaining=budget_data["total_remaining"],
            line_count=budget_data["line_count"],
            status=budget_data["status"],
            budget_lines=budget_lines,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("budget_detail_failed", budget_id=budget_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to retrieve budget: {e}")


@router.get("/budgets/project/{project_id}")
async def get_project_budgets(project_id: str):
    """
    Get all budgets for a project.

    Args:
        project_id: Project ID

    Returns:
        List of budgets for the project
    """
    logger.info("project_budgets_requested", project_id=project_id)

    try:
        budgets = graph_builder.get_budgets_by_project(project_id)

        return {
            "project_id": project_id,
            "budget_count": len(budgets),
            "budgets": budgets,
        }

    except Exception as e:
        logger.error("project_budgets_failed", project_id=project_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to retrieve budgets: {e}")


@router.get("/budgets/{budget_id}/variance", response_model=BudgetVarianceResponse)
async def get_budget_variance(budget_id: str):
    """
    Calculate budget variance (budget vs actual spend).

    Args:
        budget_id: Budget ID

    Returns:
        Variance analysis with per-line breakdown
    """
    logger.info("budget_variance_requested", budget_id=budget_id)

    try:
        budget_data = graph_builder.get_budget_by_id(budget_id)

        if not budget_data:
            raise HTTPException(status_code=404, detail="Budget not found")

        # Calculate overall variance
        total_allocated = budget_data["total_allocated"]
        total_spent = budget_data["total_spent"]
        overall_variance = (
            ((total_spent - total_allocated) / total_allocated * 100)
            if total_allocated > 0 else 0
        )
        overall_variance_amount = total_spent - total_allocated

        # Calculate per-line variance
        line_variances = []
        overrun_lines = []
        underrun_lines = []
        at_risk_lines = []

        for line in budget_data["budget_lines"]:
            allocated = line["allocated"]
            spent = line["spent"]
            variance_pct = ((spent - allocated) / allocated * 100) if allocated > 0 else 0
            variance_amt = spent - allocated
            utilization_pct = (spent / allocated * 100) if allocated > 0 else 0

            line_variances.append({
                "cost_code": line["cost_code"],
                "description": line["description"],
                "allocated": allocated,
                "spent": spent,
                "variance_percent": round(variance_pct, 2),
                "variance_amount": round(variance_amt, 2),
                "utilization_percent": round(utilization_pct, 2),
            })

            # Categorize lines
            if variance_amt > 0:
                overrun_lines.append(line["cost_code"])
            elif variance_amt < 0:
                underrun_lines.append(line["cost_code"])

            if utilization_pct > 90:
                at_risk_lines.append(line["cost_code"])

        return BudgetVarianceResponse(
            budget_id=budget_id,
            project_id=budget_data["project_id"],
            project_name=budget_data["project_name"],
            overall_variance=round(overall_variance, 2),
            overall_variance_amount=round(overall_variance_amount, 2),
            line_variances=line_variances,
            overrun_lines=overrun_lines,
            underrun_lines=underrun_lines,
            at_risk_lines=at_risk_lines,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("budget_variance_failed", budget_id=budget_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to calculate variance: {e}")


@router.post("/graph/query")
async def query_graph(query: dict):
    """
    Execute custom Cypher query on Neo4j.

    Args:
        query: Dictionary with 'query' key containing Cypher query string

    Returns:
        Query results as list of records
    """
    cypher_query = query.get("query")

    if not cypher_query:
        raise HTTPException(status_code=400, detail="Missing 'query' in request body")

    logger.info("graph_query_requested", query=cypher_query[:100])

    try:
        neo4j_client = Neo4jClient()
        results = neo4j_client.run_query(cypher_query)

        logger.info("graph_query_executed", record_count=len(results))
        return {"records": results, "count": len(results)}

    except Exception as e:
        logger.error("graph_query_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Query execution failed: {e}")


# Phase 7: Conversational AI Chat Endpoint

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Conversational AI endpoint using multi-agent system.

    Pipeline:
    1. Planner analyzes query and routes (generic_response, execution_plan, clarification)
    2. If execution_plan, Executor runs tools in one_way or react mode
    3. Validator checks response quality (retry loop if needed)
    4. Responder formats response with markdown

    Args:
        request: User message and conversation history

    Returns:
        Formatted response with display format and data
    """
    start_time = time.time()

    logger.info("chat_request_received", message=request.message[:100])

    try:
        # Import orchestrator
        from backend.agents.multi_agent.orchestrator import create_multi_agent_graph

        # Initialize multi-agent graph
        graph = create_multi_agent_graph()

        # Convert conversation history to state format
        history = [
            {"role": msg.role, "content": msg.content}
            for msg in request.conversation_history
        ]

        # Create initial state
        initial_state = {
            "user_query": request.message,
            "conversation_history": history,
            "retry_count": 0,
            "current_step": 0,
            "completed_steps": [],
            "react_max_steps": 5,
        }

        # Execute graph
        config = {"configurable": {"thread_id": request.session_id or "default"}}
        final_state = graph.invoke(initial_state, config)

        # Extract response
        response_text = final_state.get("final_response", "")
        display_format = final_state.get("display_format", "text")
        display_data = final_state.get("display_data")
        route = final_state.get("route", "unknown")
        execution_mode = final_state.get("execution_mode")

        # Build metadata
        metadata = {
            "processing_time_seconds": round(time.time() - start_time, 2),
            "retry_count": final_state.get("retry_count", 0),
            "react_steps": len(final_state.get("completed_steps", [])),
        }

        logger.info(
            "chat_request_complete",
            route=route,
            execution_mode=execution_mode,
            processing_time=metadata["processing_time_seconds"],
        )

        return ChatResponse(
            response=response_text,
            display_format=display_format,
            display_data=display_data,
            route=route,
            execution_mode=execution_mode,
            metadata=metadata,
            session_id=request.session_id,
        )

    except Exception as e:
        logger.error("chat_request_failed", error=str(e), message=request.message[:100])

        # Return friendly error response
        return ChatResponse(
            response=f"I encountered an error while processing your request: {str(e)}",
            display_format="text",
            display_data=None,
            route="generic_response",
            execution_mode=None,
            metadata={"error": str(e), "processing_time_seconds": round(time.time() - start_time, 2)},
            session_id=request.session_id,
        )
