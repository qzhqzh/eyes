#!/usr/bin/env python3
"""Eyes fleet control-plane storage.

This module keeps multi-node state separate from the legacy single-host check
tables.  It intentionally uses the repository's existing SQLite connection so
the first vertical slice does not require a new service dependency.
"""

import hashlib
import hmac
import json
import os
import secrets
import uuid
from datetime import datetime, timezone

from models import get_db


SNAPSHOT_KINDS = {"inventory", "resources", "capabilities", "links"}
TERMINAL_COMMAND_STATES = {"succeeded", "failed", "rejected"}
NODE_ONLINE_AFTER_SECONDS = int(os.environ.get("EYES_NODE_ONLINE_SECONDS", "90"))
NODE_OFFLINE_AFTER_SECONDS = int(os.environ.get("EYES_NODE_OFFLINE_SECONDS", "300"))


class FleetError(Exception):
    """Base error for fleet operations."""


class ConflictError(FleetError):
    """Raised when a stale or conflicting generation is submitted."""


class NotFoundError(FleetError):
    """Raised when a requested fleet object does not exist."""


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _json_dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _json_load(value, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def init_fleet_db():
    """Create the first control-plane tables without changing legacy tables."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.executescript(
        """
        CREATE TABLE IF NOT EXISTS nodes (
            id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            hostname TEXT NOT NULL,
            roles_json TEXT NOT NULL DEFAULT '[]',
            labels_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'enrolled',
            agent_version TEXT,
            protocol_version TEXT,
            boot_id TEXT,
            last_sequence INTEGER NOT NULL DEFAULT 0,
            last_seen_at TEXT,
            enrolled_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS node_credentials (
            node_id TEXT PRIMARY KEY,
            token_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            revoked_at TEXT,
            FOREIGN KEY (node_id) REFERENCES nodes(id)
        );

        CREATE TABLE IF NOT EXISTS node_snapshots (
            node_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            generation INTEGER NOT NULL,
            content_hash TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            observed_at TEXT,
            received_at TEXT NOT NULL,
            PRIMARY KEY (node_id, kind),
            FOREIGN KEY (node_id) REFERENCES nodes(id)
        );

        CREATE TABLE IF NOT EXISTS node_commands (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            id TEXT NOT NULL UNIQUE,
            node_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            expires_at TEXT,
            idempotency_key TEXT,
            result_json TEXT,
            created_at TEXT NOT NULL,
            acknowledged_at TEXT,
            FOREIGN KEY (node_id) REFERENCES nodes(id)
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_node_commands_idempotency
            ON node_commands(node_id, idempotency_key)
            WHERE idempotency_key IS NOT NULL;

        CREATE TABLE IF NOT EXISTS workloads (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            actor_id TEXT NOT NULL,
            spec_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            priority INTEGER NOT NULL DEFAULT 0,
            selected_node_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (selected_node_id) REFERENCES nodes(id)
        );

        CREATE TABLE IF NOT EXISTS resource_claims (
            id TEXT PRIMARY KEY,
            workload_id TEXT NOT NULL,
            node_id TEXT,
            request_json TEXT NOT NULL,
            allocation_json TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            generation INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (workload_id) REFERENCES workloads(id),
            FOREIGN KEY (node_id) REFERENCES nodes(id)
        );

        CREATE TABLE IF NOT EXISTS leases (
            id TEXT PRIMARY KEY,
            claim_id TEXT NOT NULL UNIQUE,
            node_id TEXT NOT NULL,
            fencing_token INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'prepared',
            issued_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            renewed_at TEXT,
            released_at TEXT,
            FOREIGN KEY (claim_id) REFERENCES resource_claims(id),
            FOREIGN KEY (node_id) REFERENCES nodes(id)
        );

        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_type TEXT NOT NULL,
            actor_id TEXT NOT NULL,
            action TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            decision TEXT NOT NULL,
            detail_json TEXT NOT NULL DEFAULT '{}',
            request_id TEXT,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()


def ensure_local_hub_node():
    """Create the Hub runtime node before its local heartbeat is collected."""
    node_id = os.environ.get("EYES_HUB_NODE_ID", "hub-local")
    now = _utc_now()
    hostname = os.uname().nodename
    display_name = os.environ.get("EYES_HUB_DISPLAY_NAME", "Eyes Hub")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO nodes (
            id, display_name, hostname, roles_json, labels_json, status,
            agent_version, protocol_version, enrolled_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            display_name = excluded.display_name,
            hostname = excluded.hostname,
            roles_json = excluded.roles_json,
            labels_json = excluded.labels_json,
            protocol_version = excluded.protocol_version,
            updated_at = excluded.updated_at
        """,
        (
            node_id,
            display_name,
            hostname,
            _json_dump(["hub"]),
            _json_dump({"eyes.io/role": "hub", "eyes.io/source": "hub-runtime"}),
            "enrolled",
            None,
            "eyes.node.v1",
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()
    return node_id


def enroll_node(node):
    """Enroll a new node and return its bearer credential."""
    node_id = str(node.get("node_id", "")).strip()
    hostname = str(node.get("hostname", "")).strip()
    if not node_id or len(node_id) > 128:
        raise ValueError("node_id is required and must be at most 128 characters")
    if not hostname or len(hostname) > 255:
        raise ValueError("hostname is required and must be at most 255 characters")

    display_name = str(node.get("display_name") or hostname).strip()[:255]
    roles = node.get("roles") if isinstance(node.get("roles"), list) else []
    labels = node.get("labels") if isinstance(node.get("labels"), dict) else {}
    requested_token = str(node.get("node_token", "")).strip()
    if requested_token and not 32 <= len(requested_token) <= 512:
        raise ValueError("node_token must be between 32 and 512 characters")
    token = requested_token or secrets.token_urlsafe(32)
    now = _utc_now()

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    cursor.execute(
        """
        SELECT c.token_hash
        FROM nodes n
        LEFT JOIN node_credentials c ON c.node_id = n.id AND c.revoked_at IS NULL
        WHERE n.id = ?
        """,
        (node_id,),
    )
    existing = cursor.fetchone()
    if existing:
        conn.close()
        if requested_token and existing["token_hash"] and hmac.compare_digest(
            existing["token_hash"], _token_hash(requested_token)
        ):
            return requested_token
        raise ConflictError("node_id already exists")
    cursor.execute(
        """
        INSERT INTO nodes (
            id, display_name, hostname, roles_json, labels_json, status,
            agent_version, protocol_version, enrolled_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, 'enrolled', ?, ?, ?, ?)
        """,
        (
            node_id,
            display_name,
            hostname,
            _json_dump(roles),
            _json_dump(labels),
            str(node.get("agent_version", ""))[:64],
            str(node.get("protocol_version", "eyes.node.v1"))[:64],
            now,
            now,
        ),
    )
    cursor.execute(
        """
        INSERT INTO node_credentials (node_id, token_hash, created_at, revoked_at)
        VALUES (?, ?, ?, NULL)
        """,
        (node_id, _token_hash(token), now),
    )
    _insert_audit(
        cursor,
        actor_type="bootstrap",
        actor_id="enrollment-token",
        action="node.enroll",
        target_type="node",
        target_id=node_id,
        decision="allow",
        detail={"hostname": hostname},
    )
    conn.commit()
    conn.close()
    return token


def authenticate_node(node_id, token):
    if not node_id or not token:
        return False
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT token_hash FROM node_credentials WHERE node_id = ? AND revoked_at IS NULL",
        (node_id,),
    )
    row = cursor.fetchone()
    conn.close()
    return bool(row and hmac.compare_digest(row["token_hash"], _token_hash(token)))


def record_heartbeat(node_id, heartbeat):
    """Record an idempotent heartbeat, allowing sequence reset on reboot."""
    now = _utc_now()
    sequence = int(heartbeat.get("sequence", 0))
    boot_id = str(heartbeat.get("boot_id", ""))[:128]
    if sequence < 1:
        raise ValueError("heartbeat sequence must be at least 1")
    if not boot_id:
        raise ValueError("heartbeat boot_id is required")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    cursor.execute("SELECT boot_id, last_sequence FROM nodes WHERE id = ?", (node_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise NotFoundError("node not found")
    if row["boot_id"] == boot_id and sequence < row["last_sequence"]:
        conn.close()
        raise ConflictError("heartbeat sequence is stale")

    cursor.execute(
        """
        UPDATE nodes SET
            status = 'ready',
            boot_id = ?,
            last_sequence = ?,
            last_seen_at = ?,
            agent_version = COALESCE(?, agent_version),
            protocol_version = COALESCE(?, protocol_version),
            updated_at = ?
        WHERE id = ?
        """,
        (
            boot_id,
            sequence,
            now,
            heartbeat.get("agent_version"),
            heartbeat.get("protocol_version"),
            now,
            node_id,
        ),
    )
    conn.commit()
    conn.close()
    return now


def put_snapshot(node_id, kind, generation, payload, observed_at=None):
    if kind not in SNAPSHOT_KINDS:
        raise ValueError(f"unsupported snapshot kind: {kind}")
    generation = int(generation)
    if generation < 1:
        raise ValueError("generation must be at least 1")
    if not isinstance(payload, (dict, list)):
        raise ValueError("snapshot payload must be an object or array")

    payload_json = _json_dump(payload)
    content_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    now = _utc_now()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    cursor.execute(
        "SELECT generation, content_hash FROM node_snapshots WHERE node_id = ? AND kind = ?",
        (node_id, kind),
    )
    existing = cursor.fetchone()
    if existing:
        if generation < existing["generation"]:
            conn.close()
            raise ConflictError("snapshot generation is stale")
        if generation == existing["generation"]:
            conn.close()
            if hmac.compare_digest(content_hash, existing["content_hash"]):
                return {"accepted": True, "generation": generation, "unchanged": True}
            raise ConflictError("snapshot generation already has different content")

    cursor.execute(
        """
        INSERT INTO node_snapshots (
            node_id, kind, generation, content_hash, payload_json, observed_at, received_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(node_id, kind) DO UPDATE SET
            generation = excluded.generation,
            content_hash = excluded.content_hash,
            payload_json = excluded.payload_json,
            observed_at = excluded.observed_at,
            received_at = excluded.received_at
        """,
        (node_id, kind, generation, content_hash, payload_json, observed_at, now),
    )
    cursor.execute("UPDATE nodes SET updated_at = ? WHERE id = ?", (now, node_id))
    conn.commit()
    conn.close()
    return {"accepted": True, "generation": generation, "unchanged": False}


def list_nodes():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT n.*,
               (SELECT COUNT(*) FROM node_snapshots s WHERE s.node_id = n.id) AS snapshot_count
        FROM nodes n
        ORDER BY n.display_name, n.id
        """
    )
    rows = cursor.fetchall()
    conn.close()
    return [_node_from_row(row) for row in rows]


def get_fleet_summary():
    """Aggregate the latest resource capacity of currently connected nodes."""
    nodes = list_nodes()
    node_by_id = {node["id"]: node for node in nodes}
    summary = {
        "scope": "online_nodes",
        "node_count": len(nodes),
        "connection_counts": {"online": 0, "stale": 0, "offline": 0, "unknown": 0},
        "resource_node_count": 0,
        "resources": {
            "cpu_capacity_millis": 0,
            "cpu_allocatable_millis": 0,
            "memory_capacity_bytes": 0,
            "memory_allocatable_bytes": 0,
            "memory_available_bytes": 0,
            "filesystem_capacity_bytes": 0,
            "filesystem_available_bytes": 0,
        },
        "capabilities": {},
        "generated_at": _utc_now(),
    }
    for node in nodes:
        state = node["connection_status"]
        summary["connection_counts"][state] += 1

    online_ids = {
        node_id for node_id, node in node_by_id.items() if node["connection_status"] == "online"
    }
    if not online_ids:
        return summary

    conn = get_db()
    cursor = conn.cursor()
    placeholders = ",".join("?" for _ in online_ids)
    cursor.execute(
        f"SELECT node_id, kind, payload_json FROM node_snapshots "
        f"WHERE node_id IN ({placeholders}) AND kind IN ('inventory', 'resources')",
        tuple(online_ids),
    )
    rows = cursor.fetchall()
    conn.close()

    resource_nodes = set()
    for row in rows:
        payload = _json_load(row["payload_json"], {})
        if not isinstance(payload, dict):
            continue
        if row["kind"] == "resources":
            resource_nodes.add(row["node_id"])
            cpu = payload.get("cpu") if isinstance(payload.get("cpu"), dict) else {}
            memory = payload.get("memory") if isinstance(payload.get("memory"), dict) else {}
            filesystem = payload.get("filesystem") if isinstance(payload.get("filesystem"), dict) else {}
            root = filesystem.get("root") if isinstance(filesystem.get("root"), dict) else {}
            values = summary["resources"]
            values["cpu_capacity_millis"] += _non_negative_int(cpu.get("capacity_millis"))
            values["cpu_allocatable_millis"] += _non_negative_int(cpu.get("allocatable_millis"))
            values["memory_capacity_bytes"] += _non_negative_int(memory.get("capacity_bytes"))
            values["memory_allocatable_bytes"] += _non_negative_int(memory.get("allocatable_bytes"))
            values["memory_available_bytes"] += _non_negative_int(memory.get("available_bytes"))
            values["filesystem_capacity_bytes"] += _non_negative_int(root.get("capacity_bytes"))
            values["filesystem_available_bytes"] += _non_negative_int(root.get("available_bytes"))
        elif row["kind"] == "inventory":
            capabilities = payload.get("capabilities")
            if not isinstance(capabilities, list):
                continue
            for capability in capabilities:
                if not isinstance(capability, dict) or capability.get("health") != "ready":
                    continue
                name = str(capability.get("name", "")).strip()
                if name:
                    summary["capabilities"][name] = summary["capabilities"].get(name, 0) + 1
    summary["resource_node_count"] = len(resource_nodes)
    return summary


def get_node(node_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM nodes WHERE id = ?", (node_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise NotFoundError("node not found")
    node = _node_from_row(row)
    cursor.execute(
        "SELECT kind, generation, content_hash, payload_json, observed_at, received_at FROM node_snapshots WHERE node_id = ?",
        (node_id,),
    )
    node["snapshots"] = {
        snapshot["kind"]: {
            "generation": snapshot["generation"],
            "content_hash": snapshot["content_hash"],
            "payload": _json_load(snapshot["payload_json"], {}),
            "observed_at": snapshot["observed_at"],
            "received_at": snapshot["received_at"],
        }
        for snapshot in cursor.fetchall()
    }
    conn.close()
    return node


def enqueue_command(node_id, kind, payload, expires_at=None, idempotency_key=None):
    command_id = f"cmd_{uuid.uuid4().hex}"
    now = _utc_now()
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO node_commands (
                id, node_id, kind, payload_json, expires_at, idempotency_key, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (command_id, node_id, kind, _json_dump(payload), expires_at, idempotency_key, now),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return command_id


def get_commands(node_id, after_sequence=0, limit=50):
    now = _utc_now()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT sequence, id, kind, payload_json, expires_at, idempotency_key, created_at
        FROM node_commands
        WHERE node_id = ?
          AND status = 'pending'
          AND sequence > ?
          AND (expires_at IS NULL OR expires_at > ?)
        ORDER BY sequence
        LIMIT ?
        """,
        (node_id, int(after_sequence), now, min(max(int(limit), 1), 100)),
    )
    rows = cursor.fetchall()
    conn.close()
    commands = [
        {
            "sequence": row["sequence"],
            "command_id": row["id"],
            "kind": row["kind"],
            "payload": _json_load(row["payload_json"], {}),
            "expires_at": row["expires_at"],
            "idempotency_key": row["idempotency_key"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]
    cursor_value = commands[-1]["sequence"] if commands else int(after_sequence)
    return {"commands": commands, "cursor": cursor_value}


def acknowledge_command(node_id, command_id, status, result=None):
    if status not in {"accepted", "succeeded", "failed", "rejected"}:
        raise ValueError("unsupported command status")
    now = _utc_now()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    cursor.execute(
        "SELECT status FROM node_commands WHERE id = ? AND node_id = ?",
        (command_id, node_id),
    )
    current = cursor.fetchone()
    if not current:
        conn.close()
        raise NotFoundError("command not found")
    current_status = current["status"]
    if current_status == status:
        conn.close()
        return
    if current_status in TERMINAL_COMMAND_STATES:
        conn.close()
        raise ConflictError(f"command is already {current_status}")
    cursor.execute(
        """
        UPDATE node_commands SET status = ?, result_json = ?, acknowledged_at = ?
        WHERE id = ? AND node_id = ?
        """,
        (status, _json_dump(result or {}), now, command_id, node_id),
    )
    conn.commit()
    conn.close()


def create_workload(name, spec, actor_id, priority=0):
    if not isinstance(spec, dict):
        raise ValueError("workload spec must be an object")
    name = str(name or "").strip()
    if not name:
        raise ValueError("workload name is required")
    workload_id = f"workload_{uuid.uuid4().hex}"
    now = _utc_now()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO workloads (id, name, actor_id, spec_json, status, priority, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)
        """,
        (workload_id, name[:255], actor_id[:255], _json_dump(spec), int(priority), now, now),
    )
    _insert_audit(
        cursor,
        actor_type="user",
        actor_id=actor_id,
        action="workload.submit",
        target_type="workload",
        target_id=workload_id,
        decision="allow",
        detail={"name": name, "priority": int(priority)},
    )
    conn.commit()
    conn.close()
    return workload_id


def list_workloads():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM workloads ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "actor_id": row["actor_id"],
            "spec": _json_load(row["spec_json"], {}),
            "status": row["status"],
            "priority": row["priority"],
            "selected_node_id": row["selected_node_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


def _node_from_row(row):
    data = dict(row)
    data["roles"] = _json_load(data.pop("roles_json", None), [])
    data["labels"] = _json_load(data.pop("labels_json", None), {})
    connection_status, age_seconds = _connection_status(data.get("last_seen_at"))
    data["connection_status"] = connection_status
    data["heartbeat_age_seconds"] = age_seconds
    return data


def _connection_status(last_seen_at):
    if not last_seen_at:
        return "unknown", None
    try:
        last_seen = datetime.fromisoformat(str(last_seen_at).replace("Z", "+00:00"))
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        age_seconds = max(0, int((datetime.now(timezone.utc) - last_seen).total_seconds()))
    except (TypeError, ValueError):
        return "unknown", None
    if age_seconds <= NODE_ONLINE_AFTER_SECONDS:
        return "online", age_seconds
    if age_seconds <= NODE_OFFLINE_AFTER_SECONDS:
        return "stale", age_seconds
    return "offline", age_seconds


def _non_negative_int(value):
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _insert_audit(
    cursor,
    actor_type,
    actor_id,
    action,
    target_type,
    target_id,
    decision,
    detail=None,
    request_id=None,
):
    cursor.execute(
        """
        INSERT INTO audit_events (
            actor_type, actor_id, action, target_type, target_id,
            decision, detail_json, request_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            actor_type,
            actor_id,
            action,
            target_type,
            target_id,
            decision,
            _json_dump(detail or {}),
            request_id,
            _utc_now(),
        ),
    )
