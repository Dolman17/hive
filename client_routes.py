from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import current_app, render_template, request, url_for
from flask_login import current_user, login_required

from integration_models import AppIntegration, HiveIdentity
from models import ConsultantAppAccess


def _empty_state(state: str, message: str, integration=None):
    return {
        "state": state,
        "message": message,
        "clients": [],
        "integration": integration,
        "source_launch_url": None,
    }


def _ellipse_clients_context():
    integration = AppIntegration.query.filter_by(
        service_key="ellipsecrm",
        is_enabled=True,
    ).first()
    if not integration or not integration.app_module or not integration.app_module.is_active:
        return _empty_state(
            "not_configured",
            "EllipseCRM is not currently connected to HIVE Clients.",
            integration,
        )

    access = ConsultantAppAccess.query.filter_by(
        consultant_id=current_user.id,
        app_module_id=integration.app_module_id,
        status="active",
    ).first()
    if not access:
        return _empty_state(
            "not_entitled",
            "You do not currently have active EllipseCRM access through HIVE.",
            integration,
        )

    identity = HiveIdentity.query.filter_by(user_id=current_user.id).first()
    if not identity:
        return _empty_state(
            "link_required",
            "Your HIVE integration identity is not ready yet. Open EllipseCRM from Apps once, then return here.",
            integration,
        )

    api_token = (os.getenv("HIVE_ELLIPSECRM_API_TOKEN") or "").strip()
    if not api_token:
        current_app.logger.warning("HIVE_ELLIPSECRM_API_TOKEN is not configured for Clients")
        return _empty_state(
            "unavailable",
            "Client summaries are temporarily unavailable.",
            integration,
        )

    base_url = (integration.base_url or "").strip().rstrip("/")
    clients_url = f"{base_url}/api/v1/clients?{urlencode({
        'hive_tenant_id': identity.hive_tenant_id,
        'hive_user_id': identity.hive_user_id,
    })}"
    api_request = Request(
        clients_url,
        headers={
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/json",
        },
        method="GET",
    )

    try:
        with urlopen(api_request, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 404:
            return _empty_state(
                "link_required",
                "Your HIVE account is not linked to an active EllipseCRM user yet.",
                integration,
            )
        current_app.logger.warning("Clients request returned HTTP %s", exc.code)
        return _empty_state("unavailable", "Client summaries are temporarily unavailable.", integration)
    except (URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        current_app.logger.warning("Clients request failed: %s", exc)
        return _empty_state("unavailable", "Client summaries are temporarily unavailable.", integration)

    remote_clients = payload.get("clients") if payload.get("ok") else None
    if not isinstance(remote_clients, list):
        return _empty_state("unavailable", "Client summaries are temporarily unavailable.", integration)

    clients = []
    for item in remote_clients[:100]:
        if not isinstance(item, dict) or not str(item.get("name") or "").strip():
            continue
        clients.append({
            "external_id": str(item.get("id") or "").strip(),
            "name": str(item.get("name") or "").strip(),
            "account_status": str(item.get("account_status") or "unknown").strip().lower(),
            "service_arrangement": str(item.get("service_arrangement") or "").strip(),
            "town_city": str(item.get("town_city") or "").strip(),
            "main_contact_name": str(item.get("main_contact_name") or "").strip(),
            "open_cases": int(item.get("open_cases") or 0),
            "urgent_cases": int(item.get("urgent_cases") or 0),
            "open_actions": int(item.get("open_actions") or 0),
            "latest_activity_at": item.get("latest_activity_at"),
            "needs_attention": bool(int(item.get("urgent_cases") or 0) or int(item.get("open_actions") or 0)),
        })

    return {
        "state": "available",
        "message": None,
        "clients": clients,
        "integration": integration,
        "source_launch_url": url_for(
            "billing.integration_sso_launch",
            app_slug=integration.app_module.slug,
        ),
    }


def register_client_routes(bp):
    @bp.route("/clients")
    @login_required
    def client_list():
        if current_user.role != "consultant":
            return render_template("clients/index.html", source_state=_empty_state(
                "forbidden",
                "Clients is available from a consultant account.",
            )), 403

        source_state = _ellipse_clients_context()
        clients = source_state["clients"]

        search_term = (request.args.get("q") or "").strip().lower()
        status = (request.args.get("status") or "").strip().lower()
        attention_only = (request.args.get("attention") or "") == "1"

        filtered = []
        for client in clients:
            haystack = " ".join([
                client["name"],
                client["town_city"],
                client["main_contact_name"],
                client["service_arrangement"],
            ]).lower()
            if search_term and search_term not in haystack:
                continue
            if status and client["account_status"] != status:
                continue
            if attention_only and not client["needs_attention"]:
                continue
            filtered.append(client)

        totals = {
            "total": len(clients),
            "active": sum(1 for client in clients if client["account_status"] == "active"),
            "attention": sum(1 for client in clients if client["needs_attention"]),
            "open_actions": sum(client["open_actions"] for client in clients),
        }

        return render_template(
            "clients/index.html",
            source_state=source_state,
            clients=filtered,
            totals=totals,
            search_term=request.args.get("q", ""),
            selected_status=status,
            attention_only=attention_only,
        )
