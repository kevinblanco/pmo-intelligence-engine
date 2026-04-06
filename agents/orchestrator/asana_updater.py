"""
Asana REST API write-back module.
Updates task custom fields and adds a formatted AI analysis comment.
Uses the Asana Python SDK with PAT auth (NOT MCP — MCP is read-only for agents).

Custom field types verified against the "New Project Requests" project:
  Resource Signal      → enum  (Available, Limited, Constrained, Unknown)
  Strategic Fit        → enum  (Strong, Moderate, Weak, Misaligned)
  Live Workspace Context → enum (Context Available, Partial Context, No Context)
  AI Recommendation    → enum  (Approve, Flag for Review, Escalate)
  Analysis Status      → enum  (Pending, In Progress, Complete, Error)

Note: "AI Risk Score" does NOT exist as a custom field — the score appears
in the comment only.
"""

import logging
import os

import asana
from asana.rest import ApiException

logger = logging.getLogger("orchestrator.asana-updater")

ASANA_PAT = os.environ["ASANA_PAT"]

# Maps Asana custom field display_name → (payload_key, field_type)
# field_type must match the actual Asana field type (enum / number / text)
FIELD_MAP = {
    "Resource Signal":        ("resource_signal",      "enum"),
    "Strategic Fit":          ("strategic_fit",        "enum"),
    "Live Workspace Context": ("live_context_summary", "enum"),
    "AI Recommendation":      ("recommendation",       "enum"),
    "Analysis Status":        ("_status_complete",     "enum"),
}

_ANALYSIS_STATUS_VALUE = "Complete"


# ─── Value transformation helpers ────────────────────────────────────────────

def _transform_strategic_fit(value: str) -> str:
    """Map risk_scorer output ('High'/'Medium'/'Low') to Asana enum names."""
    mapping = {
        "high":   "Strong",
        "medium": "Moderate",
        "low":    "Weak",
    }
    return mapping.get(str(value).lower(), "Misaligned")


def _transform_live_context(value: str) -> str:
    """Derive enum from live_context_summary text."""
    if not value or "no matching data" in value.lower():
        return "No Context"
    if len(value) < 80:
        return "Partial Context"
    return "Context Available"


def _transform_resource_signal(value: str) -> str:
    """Resource signal values match Asana enum directly; fall back to Unknown."""
    valid = {"Available", "Limited", "Constrained", "Unknown"}
    return value if value in valid else "Unknown"


def _prepare_enum_value(field_name: str, payload_key: str, raw_value) -> str | None:
    """Return the Asana enum name for a given field, applying any transforms."""
    if payload_key == "_status_complete":
        return _ANALYSIS_STATUS_VALUE

    if field_name == "Strategic Fit":
        return _transform_strategic_fit(str(raw_value)) if raw_value else None

    if field_name == "Live Workspace Context":
        return _transform_live_context(str(raw_value) if raw_value else "")

    if field_name == "Resource Signal":
        return _transform_resource_signal(str(raw_value)) if raw_value else "Unknown"

    # AI Recommendation: "Approve" / "Flag for Review" / "Escalate" — direct match
    return str(raw_value) if raw_value else None


# ─── Asana SDK helpers ────────────────────────────────────────────────────────

def _build_asana_client():
    configuration = asana.Configuration()
    configuration.access_token = ASANA_PAT
    api_client = asana.ApiClient(configuration)
    return asana.TasksApi(api_client), asana.StoriesApi(api_client)


def _resolve_custom_fields(tasks_api, task_gid: str) -> dict:
    """
    Returns a mapping of display_name → {gid, type, enum_options}
    by fetching the task with opt_fields for custom_fields + enum_options.
    Falls back to 'name' if 'display_name' is absent (SDK version difference).
    """
    opts = {
        "opt_fields": (
            "custom_fields.gid"
            ",custom_fields.name"
            ",custom_fields.display_name"
            ",custom_fields.resource_subtype"
            ",custom_fields.enum_options"
            ",custom_fields.enum_options.gid"
            ",custom_fields.enum_options.name"
        )
    }
    task = tasks_api.get_task(task_gid, opts)

    # SDK v5 may return the raw {"data": {...}} envelope on some calls
    if isinstance(task, dict) and "data" in task and "gid" not in task:
        task = task["data"]

    field_map = {}
    for cf in task.get("custom_fields", []):
        # SDK may return display_name or name depending on version
        name = cf.get("display_name") or cf.get("name", "")
        if not name:
            continue
        field_map[name] = {
            "gid": cf["gid"],
            "type": cf.get("resource_subtype", ""),
            "enum_options": {
                opt["name"]: opt["gid"]
                for opt in cf.get("enum_options") or []
            },
        }

    if not field_map:
        logger.warning(
            f"_resolve_custom_fields returned empty map for task {task_gid} — "
            f"task keys: {list(task.keys()) if isinstance(task, dict) else type(task)}"
        )

    return field_map


def _build_custom_fields_update(cf_meta: dict, payload: dict) -> dict:
    """Builds the custom_fields dict for the Asana task update call."""
    updates = {}

    for display_name, (payload_key, _field_type) in FIELD_MAP.items():
        if display_name not in cf_meta:
            logger.warning(f"Custom field '{display_name}' not found on task — skipping")
            continue

        meta = cf_meta[display_name]
        gid = meta["gid"]
        raw_value = payload.get(payload_key)

        # All fields in FIELD_MAP are enum type
        enum_name = _prepare_enum_value(display_name, payload_key, raw_value)
        if not enum_name:
            logger.warning(f"No enum value resolved for field '{display_name}' (raw={raw_value!r})")
            continue

        if enum_name not in meta["enum_options"]:
            logger.warning(
                f"Enum value '{enum_name}' not in options for '{display_name}': "
                f"{list(meta['enum_options'].keys())}"
            )
            continue

        updates[gid] = meta["enum_options"][enum_name]
        logger.info(f"  → {display_name}: '{enum_name}' (gid={updates[gid]})")

    return updates


# ─── Comment builder ──────────────────────────────────────────────────────────

def _build_analysis_comment(payload: dict) -> str:
    """Formats the AI analysis as an Asana-compatible rich text comment."""
    risk_score = payload.get("risk_score", "N/A")
    risk_level = payload.get("risk_level", "Unknown")
    recommendation = payload.get("recommendation", "Unknown")
    confidence = payload.get("confidence", "Unknown")
    resource_signal = payload.get("resource_signal", "Unknown")
    strategic_fit_raw = payload.get("strategic_fit", "Unknown")
    strategic_fit = _transform_strategic_fit(strategic_fit_raw) if strategic_fit_raw not in ("Unknown", None) else "Unknown"
    strategic_fit_reason = payload.get("strategic_fit_reason", "")
    live_context = payload.get("live_context_summary", "")
    resource_rec = payload.get("resource_recommendation", "")
    risk_factors = payload.get("risk_factors", [])
    potential_duplicate = payload.get("potential_duplicate", False)
    duplicate_reason = payload.get("potential_duplicate_reason", "")
    similar_count = payload.get("similar_projects_count", 0)
    pct_over_budget = payload.get("pct_over_budget", 0)

    lines = [
        f"**AI Recommendation: {recommendation}**",
        "",
        "**Risk Assessment**",
        f"Score: {risk_score}/10 ({risk_level}) | Confidence: {confidence}",
    ]

    if similar_count:
        lines.append(f"Based on {similar_count} similar historical projects ({pct_over_budget:.0f}% went over budget)")

    if risk_factors:
        lines.append("")
        lines.append("**Top Risk Factors**")
        for rf in risk_factors[:3]:
            severity = rf.get("severity", "")
            factor = rf.get("factor", "")
            description = rf.get("description", "")
            lines.append(f"• [{severity.upper()}] {factor}: {description}")

    lines += [
        "",
        "**Resource & Strategic Fit**",
        f"Resource Signal: {resource_signal}",
        f"Strategic Fit: {strategic_fit}",
    ]
    if strategic_fit_reason:
        lines.append(f"Reason: {strategic_fit_reason}")
    if resource_rec:
        lines.append(f"Resource Note: {resource_rec}")

    lines += [
        "",
        "**Live Workspace Context (Asana MCP)**",
        live_context if live_context else "No matching data found in current workspace.",
    ]

    if potential_duplicate:
        lines += [
            "",
            "⚠ **Potential Duplicate Detected**",
            duplicate_reason or "A similar project may already be in progress.",
        ]

    lines += [
        "",
        "---",
        "_Analysis generated by PMO Intelligence Engine (A2A · MCP · Vertex AI)_",
    ]

    return "\n".join(lines)


# ─── Public API ───────────────────────────────────────────────────────────────

def update_task_with_enrichment(task_gid: str, payload: dict) -> None:
    """
    Writes AI enrichment data back to the Asana task.
    1. Resolves custom field GIDs by display_name at runtime.
    2. Updates all output custom fields.
    3. Adds formatted AI analysis comment.
    """
    tasks_api, stories_api = _build_asana_client()

    # Resolve field GIDs
    try:
        cf_meta = _resolve_custom_fields(tasks_api, task_gid)
    except ApiException as e:
        logger.error(f"Failed to resolve custom fields for task {task_gid}: {e}")
        raise

    # Build and apply custom field updates
    custom_fields_update = _build_custom_fields_update(cf_meta, payload)

    if custom_fields_update:
        try:
            tasks_api.update_task(
                {"data": {"custom_fields": custom_fields_update}},
                task_gid,
                {},
            )
            logger.info(f"Updated {len(custom_fields_update)} custom fields on task {task_gid}")
        except ApiException as e:
            logger.error(f"Failed to update custom fields on task {task_gid}: {e}")
            raise
    else:
        logger.warning(f"No custom fields to update for task {task_gid} — cf_meta had {len(cf_meta)} entries")

    # Add comment
    comment = _build_analysis_comment(payload)
    try:
        stories_api.create_story_for_task(
            {"data": {"text": comment}},
            task_gid,
            {},
        )
        logger.info(f"Added AI analysis comment to task {task_gid}")
    except ApiException as e:
        logger.error(f"Failed to add comment to task {task_gid}: {e}")
        raise


def set_analysis_status(task_gid: str, status: str) -> None:
    """Sets the Analysis Status custom field to the given status value."""
    tasks_api, _ = _build_asana_client()

    try:
        cf_meta = _resolve_custom_fields(tasks_api, task_gid)
    except ApiException as e:
        logger.warning(f"Could not resolve fields for status update: {e}")
        return

    if "Analysis Status" not in cf_meta:
        logger.warning("'Analysis Status' field not found on task")
        return

    meta = cf_meta["Analysis Status"]
    if status not in meta["enum_options"]:
        logger.warning(f"Status value '{status}' not in enum options: {list(meta['enum_options'].keys())}")
        return

    try:
        tasks_api.update_task(
            {"data": {"custom_fields": {meta["gid"]: meta["enum_options"][status]}}},
            task_gid,
            {},
        )
        logger.info(f"Set Analysis Status to '{status}' on task {task_gid}")
    except ApiException as e:
        logger.warning(f"Could not set Analysis Status to '{status}': {e}")
