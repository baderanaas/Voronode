"""
Graph Explorer Page

Visualize and query the Neo4j knowledge graph.
"""

import streamlit as st
import sys
import time
from pathlib import Path
import networkx as nx
import plotly.graph_objects as go
from typing import List, Dict, Any

# Add paths
frontend_path = Path(__file__).parent.parent
sys.path.insert(0, str(frontend_path))

from utils.api_client import APIClient
from utils.formatters import format_currency, format_date
from utils.logger import get_logger

logger = get_logger(__name__)

_STATS_TTL = 60  # seconds


def _load_graph_stats(api: APIClient) -> dict:
    """Return graph stats from session-state cache, re-fetching when stale."""
    now = time.monotonic()
    cached_at = st.session_state.get("_graph_stats_cached_at", 0)
    cached = st.session_state.get("_graph_stats")
    if cached is not None and (now - cached_at) < _STATS_TTL:
        return cached
    data = api.get_graph_stats()
    st.session_state["_graph_stats"] = data
    st.session_state["_graph_stats_cached_at"] = now
    return data


st.title("🔍 Graph Explorer")
st.markdown("Visualize relationships in the knowledge graph.")

# Initialize API client
api = APIClient()
api.token = st.session_state.get("token")


def format_neo4j_value(value):
    """Format Neo4j values for display, handling datetime objects."""
    if isinstance(value, dict):
        # Check if it's a Neo4j date/datetime object
        if "_Date__year" in value:
            # Date object
            year = value.get("_Date__year")
            month = value.get("_Date__month")
            day = value.get("_Date__day")
            return f"{year}-{month:02d}-{day:02d}"
        elif "_DateTime__date" in value:
            # DateTime object
            date_part = value.get("_DateTime__date", {})
            time_part = value.get("_DateTime__time", {})
            year = date_part.get("_Date__year")
            month = date_part.get("_Date__month")
            day = date_part.get("_Date__day")
            hour = time_part.get("_Time__hour", 0)
            minute = time_part.get("_Time__minute", 0)
            return f"{year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}"
        else:
            # Other dict, return as string (truncated)
            return str(value)[:50]
    elif isinstance(value, (int, float)):
        # Format numbers nicely
        if isinstance(value, float) and value > 100:
            return f"${value:,.2f}"
        return str(value)
    else:
        return str(value)


def infer_node_type(props: dict) -> str:
    """Infer node type from properties."""
    if "invoice_number" in props:
        return "Invoice"
    elif "name" in props and "license_number" in props:
        return "Contractor"
    elif "cost_code" in props and "unit_price" in props:
        return "LineItem"
    elif "name" in props and "budget" in props:
        return "Project"
    elif "value" in props and "retention_rate" in props:
        return "Contract"
    else:
        return "Node"


def visualize_graph(graph_data: Dict[str, Any]):
    """Create interactive network visualization with Plotly."""
    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])

    if not nodes:
        st.warning("No nodes to visualize")
        return

    # Create NetworkX graph for layout
    G = nx.Graph()

    # Add nodes
    for node in nodes:
        node_id = node.get("id")
        G.add_node(node_id, **node.get("properties", {}))

    # Add edges
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if source and target:
            G.add_edge(source, target, **edge.get("properties", {}))

    # Compute layout
    pos = nx.spring_layout(G, k=2, iterations=50)

    # Create Plotly traces
    edge_trace = go.Scatter(
        x=[],
        y=[],
        line=dict(width=2, color="#888"),
        hoverinfo="none",
        mode="lines",
    )

    # Add edges to trace
    for edge in G.edges():
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        edge_trace["x"] += tuple([x0, x1, None])
        edge_trace["y"] += tuple([y0, y1, None])

    # Create node trace
    node_x = []
    node_y = []
    node_text = []
    node_color = []

    # Color by node type
    type_colors = {
        "Invoice": "#FF6B6B",
        "Project": "#4ECDC4",
        "Contract": "#45B7D1",
        "Contractor": "#FFA07A",
        "LineItem": "#98D8C8",
        "Node": "#808080",
    }

    for node_id in G.nodes():
        x, y = pos[node_id]
        node_x.append(x)
        node_y.append(y)

        # Find node data
        node_data = next((n for n in nodes if n.get("id") == node_id), {})
        props = node_data.get("properties", {})

        # Infer node type from properties
        node_type = infer_node_type(props)

        # Create hover text with formatted values
        hover_text = f"<b>{node_type}</b><br>"

        # Show key properties first
        key_props = ["name", "invoice_number", "description", "cost_code", "id"]
        shown_props = set()

        # Show key properties first
        for key in key_props:
            if key in props:
                value = format_neo4j_value(props[key])
                hover_text += f"{key}: {value}<br>"
                shown_props.add(key)

        # Show other properties (limit to 5 total)
        count = len(shown_props)
        for key, value in props.items():
            if count >= 5:
                break
            if key not in shown_props and not key.startswith("_"):
                formatted_value = format_neo4j_value(value)
                hover_text += f"{key}: {formatted_value}<br>"
                count += 1
                shown_props.add(key)

        node_text.append(hover_text)
        node_color.append(type_colors.get(node_type, "#808080"))

    # Create short labels for display
    short_labels = []
    for node in nodes:
        label = node.get("label", "")
        # Show icon/emoji instead of truncated text
        label_icons = {
            "Invoice": "📄",
            "Contractor": "👷",
            "LineItem": "📋",
            "Project": "🏗️",
            "Contract": "📝",
        }
        short_labels.append(label_icons.get(label, ""))

    node_trace = go.Scatter(
        x=node_x,
        y=node_y,
        mode="markers+text",
        hoverinfo="text",
        text=short_labels,
        hovertext=node_text,
        textfont=dict(size=12),
        marker=dict(
            color=node_color,
            size=25,
            line=dict(width=2, color="white"),
        ),
    )

    # Create figure
    fig = go.Figure(
        data=[edge_trace, node_trace],
        layout=go.Layout(
            title="Knowledge Graph Visualization",
            showlegend=False,
            hovermode="closest",
            margin=dict(b=0, l=0, r=0, t=40),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            height=600,
        ),
    )

    st.plotly_chart(fig, use_container_width=True)

    # Legend
    st.markdown("### Node Types")
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.markdown("🔴 Invoice")
    with col2:
        st.markdown("🟢 Project")
    with col3:
        st.markdown("🔵 Contract")
    with col4:
        st.markdown("🟠 Contractor")
    with col5:
        st.markdown("🟣 LineItem")


# Tabs for different query modes
tab1, tab2, tab3 = st.tabs(["📋 Predefined Queries", "✏️ Custom Query", "📊 Statistics"])

with tab1:
    st.markdown("### Common Queries")

    query_options = {
        "All Invoices with Contracts": """
            MATCH (i:Invoice)-[r:BILLED_AGAINST]->(c:Contract)
            RETURN i, r, c
            LIMIT 50
        """,
        "Invoices and Line Items": """
            MATCH (i:Invoice)-[r:CONTAINS_ITEM]->(li:LineItem)
            RETURN i, r, li
            LIMIT 50
        """,
        "Full Invoice Relationships": """
            MATCH path = (i:Invoice)-[r]->(n)
            RETURN i, r, n
            LIMIT 100
        """,
        "Project with all Invoices": """
            MATCH (p:Project)<-[r:FOR_PROJECT]-(i:Invoice)
            RETURN p, r, i
            LIMIT 50
        """,
        "High-Value Invoices (>$50k)": """
            MATCH (i:Invoice)-[r]->(n)
            WHERE i.amount > 50000
            RETURN i, r, n
            LIMIT 50
        """,
        "Contractors and Invoices": """
            MATCH (c:Contractor)-[r:ISSUED]->(i:Invoice)
            RETURN c, r, i
            LIMIT 50
        """,
    }

    selected_query = st.selectbox("Select Query", list(query_options.keys()))

    if st.button("🔍 Execute Query", type="primary"):
        with st.spinner("Executing query..."):
            try:
                cypher = query_options[selected_query]
                st.code(cypher, language="cypher")

                result = api.query_graph(cypher)

                # Display results
                st.markdown("---")
                st.markdown("### Results")

                records = result.get("records", [])
                st.success(f"✅ Returned {len(records)} records")

                if records:
                    # Convert to graph format
                    nodes = []
                    edges = []
                    node_ids = set()

                    # Track element_id to property id mapping
                    element_to_prop_id = {}
                    raw_edges = []  # Store raw edges temporarily

                    for record in records:
                        # Each record can have nodes (n, i, c) and relationships (r)
                        for key, value in record.items():
                            if isinstance(value, dict):
                                # Check if it's a relationship
                                if value.get("_relationship"):
                                    # It's a relationship - store temporarily
                                    raw_edges.append({
                                        "source_element": value.get("start"),
                                        "target_element": value.get("end"),
                                        "type": value.get("type"),
                                        "properties": {}
                                    })

                                # Check if it's a node (has _element_id)
                                elif "_element_id" in value:
                                    element_id = value.get("_element_id")
                                    prop_id = value.get("id")  # Property ID from node

                                    if prop_id:
                                        # Map element ID to property ID
                                        element_to_prop_id[element_id] = prop_id

                                        if prop_id not in node_ids:
                                            # Clean properties
                                            clean_props = {
                                                k: v for k, v in value.items()
                                                if not k.startswith("_")
                                            }

                                            nodes.append({
                                                "id": prop_id,
                                                "label": infer_node_type(clean_props),
                                                "properties": clean_props,
                                            })
                                            node_ids.add(prop_id)

                    # Resolve relationships using the element-to-property ID mapping
                    for raw_edge in raw_edges:
                        source_id = element_to_prop_id.get(raw_edge["source_element"])
                        target_id = element_to_prop_id.get(raw_edge["target_element"])

                        if source_id and target_id:
                            edges.append({
                                "source": source_id,
                                "target": target_id,
                                "type": raw_edge["type"],
                                "properties": raw_edge.get("properties", {})
                            })

                    graph_data = {"nodes": nodes, "edges": edges}

                    # Visualize
                    if nodes:
                        visualize_graph(graph_data)

                        # Show node count
                        st.info(f"📊 Visualizing {len(nodes)} nodes")
                    else:
                        st.info("No graph structure to visualize. Showing raw data:")

                    # Show raw data
                    with st.expander("📄 Raw Data (for debugging)", expanded=False):
                        st.json(records)

                else:
                    st.info("Query returned no results")

            except Exception as e:
                logger.error("graph_query_failed", error=e)
                st.error(f"Query failed: {e}")

with tab2:
    st.markdown("### Custom Cypher Query")

    st.info(
        "Write your own Cypher query to explore the graph. "
        "Be careful with queries that return large result sets."
    )

    # Example queries
    with st.expander("💡 Example Queries"):
        st.code(
            """
// Find all nodes
MATCH (n) RETURN n LIMIT 25

// Find invoices for a specific project
MATCH (p:Project {project_id: 'P001'})<-[:FOR_PROJECT]-(i:Invoice)
RETURN p, i

// Find contractors with multiple projects
MATCH (c:Contractor)-[:AWARDED_TO]-(con:Contract)-[:FOR_PROJECT]->(p:Project)
WITH c, count(DISTINCT p) as project_count
WHERE project_count > 1
RETURN c.name, project_count

// Find line items over $10k
MATCH (li:LineItem)-[:LINE_OF]->(i:Invoice)
WHERE li.amount > 10000
RETURN li, i
        """,
            language="cypher",
        )

    custom_query = st.text_area(
        "Cypher Query",
        height=200,
        placeholder="MATCH (n) RETURN n LIMIT 25",
    )

    if st.button("▶️ Run Custom Query", type="primary"):
        if not custom_query.strip():
            st.warning("Please enter a query")
        else:
            with st.spinner("Executing custom query..."):
                try:
                    result = api.query_graph(custom_query)

                    st.success("✅ Query executed successfully")

                    records = result.get("records", [])
                    st.info(f"Returned {len(records)} records")

                    if records:
                        # Try to visualize if nodes are returned
                        nodes = []
                        edges = []
                        node_ids = set()
                        element_to_prop_id = {}
                        raw_edges = []

                        for record in records:
                            for key, value in record.items():
                                if isinstance(value, dict):
                                    # Check if it's a relationship
                                    if value.get("_relationship"):
                                        raw_edges.append({
                                            "source_element": value.get("start"),
                                            "target_element": value.get("end"),
                                            "type": value.get("type"),
                                            "properties": {}
                                        })
                                    # Check if it's a node
                                    elif "_element_id" in value:
                                        element_id = value.get("_element_id")
                                        prop_id = value.get("id")
                                        if prop_id:
                                            element_to_prop_id[element_id] = prop_id
                                            if prop_id not in node_ids:
                                                clean_props = {
                                                    k: v for k, v in value.items()
                                                    if not k.startswith("_")
                                                }
                                                nodes.append({
                                                    "id": prop_id,
                                                    "label": infer_node_type(clean_props),
                                                    "properties": clean_props,
                                                })
                                                node_ids.add(prop_id)

                        # Resolve relationships
                        for raw_edge in raw_edges:
                            source_id = element_to_prop_id.get(raw_edge["source_element"])
                            target_id = element_to_prop_id.get(raw_edge["target_element"])
                            if source_id and target_id:
                                edges.append({
                                    "source": source_id,
                                    "target": target_id,
                                    "type": raw_edge["type"],
                                    "properties": raw_edge.get("properties", {})
                                })

                        if nodes:
                            graph_data = {"nodes": nodes, "edges": edges}
                            visualize_graph(graph_data)
                            st.info(f"📊 Visualizing {len(nodes)} nodes and {len(edges)} relationships")

                        # Show raw data
                        with st.expander("📄 Raw Data", expanded=not nodes):
                            st.json(records[:50])  # Limit display to 50 records

                        if len(records) > 50:
                            st.caption(f"Showing first 50 of {len(records)} records")
                    else:
                        st.info("Query returned no results")

                except Exception as e:
                    logger.error("custom_query_failed", error=e)
                    st.error(f"❌ Query failed: {e}")

with tab3:
    st.markdown("### Graph Statistics")

    try:
        stats = _load_graph_stats(api)

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Total Nodes", stats.get("total_nodes", 0))
            st.metric("Invoices", stats.get("invoice_count", 0))
            st.metric("Projects", stats.get("project_count", 0))

        with col2:
            st.metric("Contracts", stats.get("contract_count", 0))
            st.metric("Contractors", stats.get("contractor_count", 0))
            st.metric("Line Items", stats.get("line_item_count", 0))

        with col3:
            st.metric("Total Relationships", stats.get("total_relationships", 0))

        # Node type distribution
        st.markdown("---")
        st.markdown("### Node Distribution")

        node_counts = {
            "Invoice": stats.get("invoice_count", 0),
            "Project": stats.get("project_count", 0),
            "Contract": stats.get("contract_count", 0),
            "Contractor": stats.get("contractor_count", 0),
            "LineItem": stats.get("line_item_count", 0),
        }

        # Pie chart
        import plotly.express as px

        fig = px.pie(
            values=list(node_counts.values()),
            names=list(node_counts.keys()),
            title="Node Type Distribution",
        )
        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        logger.error("graph_stats_load_failed", error=e)
        st.error(f"Failed to load statistics: {e}")

# Sidebar
with st.sidebar:
    st.markdown("### 🔍 Graph Info")

    try:
        stats = _load_graph_stats(api)

        st.metric("Total Nodes", stats.get("total_nodes", 0))
        st.metric("Relationships", stats.get("total_relationships", 0))

    except:
        st.info("Stats unavailable")

    st.markdown("---")
    st.markdown("### 📚 Resources")

    st.markdown(
        """
    - [Neo4j Cypher Docs](https://neo4j.com/docs/cypher-manual/current/)
    - [Graph Query Patterns](https://neo4j.com/docs/cypher-manual/current/queries/)
    """
    )
