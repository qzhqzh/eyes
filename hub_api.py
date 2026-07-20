#!/usr/bin/env python3
"""Versioned Hub APIs for node and workload control-plane traffic."""

import os
import secrets
from functools import wraps

from flask import Blueprint, jsonify, request, session

from fleet import (
    ConflictError,
    NotFoundError,
    acknowledge_command,
    authenticate_node,
    create_workload,
    enroll_node,
    get_commands,
    get_fleet_summary,
    get_node,
    list_nodes,
    list_workloads,
    put_snapshot,
    record_heartbeat,
)


hub_api = Blueprint("hub_api", __name__, url_prefix="/api/v1")
MAX_CONTROL_PAYLOAD_BYTES = 2 * 1024 * 1024


def _error(message, status):
    return jsonify({"error": message}), status


def _admin_required(handler):
    @wraps(handler)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return _error("authentication required", 401)
        return handler(*args, **kwargs)

    return decorated


def _expected_enroll_token():
    return os.environ.get("EYES_HUB_ENROLL_TOKEN", "")


def _bearer_token():
    authorization = request.headers.get("Authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if separator and scheme.lower() == "bearer":
        return token.strip()
    return ""


def _authenticated_node():
    node_id = request.headers.get("X-Eyes-Node-ID", "").strip()
    token = _bearer_token()
    if not authenticate_node(node_id, token):
        return None
    return node_id


def _payload_too_large():
    return bool(
        request.content_length is not None
        and request.content_length > MAX_CONTROL_PAYLOAD_BYTES
    )


@hub_api.route("/enroll", methods=["POST"])
def enroll():
    if _payload_too_large():
        return _error("request payload is too large", 413)
    expected_token = _expected_enroll_token()
    supplied_token = request.headers.get("X-Eyes-Enroll-Token", "")
    if not expected_token:
        return _error("node enrollment is disabled", 503)
    if not supplied_token or not secrets.compare_digest(expected_token, supplied_token):
        return _error("invalid enrollment token", 403)

    data = request.get_json(silent=True) or {}
    try:
        node_token = enroll_node(data)
    except ValueError as exc:
        return _error(str(exc), 400)
    except ConflictError as exc:
        return _error(str(exc), 409)
    return (
        jsonify(
            {
                "node_id": data.get("node_id"),
                "node_token": node_token,
                "protocol_version": "eyes.node.v1",
                "heartbeat_interval_seconds": 30,
                "snapshot_interval_seconds": 300,
            }
        ),
        201,
    )


@hub_api.route("/node/heartbeat", methods=["POST"])
def heartbeat():
    if _payload_too_large():
        return _error("request payload is too large", 413)
    node_id = _authenticated_node()
    if not node_id:
        return _error("invalid node credential", 401)
    data = request.get_json(silent=True) or {}
    try:
        accepted_at = record_heartbeat(node_id, data)
    except (TypeError, ValueError) as exc:
        return _error(str(exc), 400)
    except ConflictError as exc:
        return _error(str(exc), 409)
    except NotFoundError as exc:
        return _error(str(exc), 404)
    return jsonify({"accepted": True, "accepted_at": accepted_at})


@hub_api.route("/node/<kind>", methods=["PUT"])
def snapshot(kind):
    if _payload_too_large():
        return _error("request payload is too large", 413)
    node_id = _authenticated_node()
    if not node_id:
        return _error("invalid node credential", 401)
    data = request.get_json(silent=True) or {}
    try:
        result = put_snapshot(
            node_id=node_id,
            kind=kind,
            generation=data.get("generation"),
            payload=data.get("payload"),
            observed_at=data.get("observed_at"),
        )
    except (TypeError, ValueError) as exc:
        return _error(str(exc), 400)
    except ConflictError as exc:
        return _error(str(exc), 409)
    return jsonify(result)


@hub_api.route("/node/commands", methods=["GET"])
def commands():
    node_id = _authenticated_node()
    if not node_id:
        return _error("invalid node credential", 401)
    try:
        cursor = request.args.get("cursor", 0, type=int)
        limit = request.args.get("limit", 50, type=int)
        result = get_commands(node_id, cursor, limit)
    except ValueError as exc:
        return _error(str(exc), 400)
    return jsonify(result)


@hub_api.route("/node/commands/<command_id>/ack", methods=["POST"])
def command_ack(command_id):
    if _payload_too_large():
        return _error("request payload is too large", 413)
    node_id = _authenticated_node()
    if not node_id:
        return _error("invalid node credential", 401)
    data = request.get_json(silent=True) or {}
    try:
        acknowledge_command(node_id, command_id, data.get("status"), data.get("result"))
    except ValueError as exc:
        return _error(str(exc), 400)
    except ConflictError as exc:
        return _error(str(exc), 409)
    except NotFoundError as exc:
        return _error(str(exc), 404)
    return jsonify({"accepted": True})


@hub_api.route("/nodes", methods=["GET"])
@_admin_required
def nodes():
    return jsonify(list_nodes())


@hub_api.route("/fleet/summary", methods=["GET"])
@_admin_required
def fleet_summary():
    return jsonify(get_fleet_summary())


@hub_api.route("/nodes/<node_id>", methods=["GET"])
@_admin_required
def node_detail(node_id):
    try:
        return jsonify(get_node(node_id))
    except NotFoundError as exc:
        return _error(str(exc), 404)


@hub_api.route("/workloads", methods=["GET"])
@_admin_required
def workloads():
    return jsonify(list_workloads())


@hub_api.route("/workloads", methods=["POST"])
@_admin_required
def submit_workload():
    if _payload_too_large():
        return _error("request payload is too large", 413)
    data = request.get_json(silent=True) or {}
    try:
        workload_id = create_workload(
            name=data.get("name"),
            spec=data.get("spec"),
            actor_id="web-admin",
            priority=data.get("priority", 0),
        )
    except (TypeError, ValueError) as exc:
        return _error(str(exc), 400)
    return jsonify({"id": workload_id, "status": "pending"}), 202
