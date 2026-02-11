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
