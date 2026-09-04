from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import and_, or_

from extensions import db
from integration_models import (
    AppIntegration,
    ClientRecordLink,
    HiveIdentity,
    IntegrationEvent,
)
from models import ConsultantAppAccess, CoverRequest, Lead


SUPPORTED_LINK_TYPES = {"people_signal", "directory_enquiry", "cover_request"}


def _empty_state(state: str, message: str, integration=None):
    return {
        "state": state,
        "message": message,
        "clients": [],
        "integration": integration,
        "source_launch_url": None,
    }


def _ellipse_connection_context():
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

    return {
        "state": "available",
        "message": None,
        "clients": [],
        "integration": integration,
        "identity": identity,
        "api_token": api_token,
        "base_url": (integration.base_url or "").strip().rstrip("/"),
        "source_launch_url": url_for(
            "billing.integration_sso_launch",
            app_slug=integration.app_module.slug,
        ),
    }


def _ellipse_api_get(connection, path):
    identity = connection["identity"]
    query = urlencode({
        "hive_tenant_id": identity.hive_tenant_id,
        "hive_user_id": identity.hive_user_id,
    })
    api_request = Request(
        f"{connection['base_url']}{path}?{query}",
        headers={
            "Authorization": f"Bearer {connection['api_token']}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urlopen(api_request, timeout=3) as response:
            return json.loads(response.read().decode("utf-8")), None
    except HTTPError as exc:
        return None, exc.code
    except (URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        current_app.logger.warning("EllipseCRM client request failed: %s", exc)
        return None, "unavailable"


def _ellipse_clients_context():
    connection = _ellipse_connection_context()
    if connection["state"] != "available":
        return connection

    payload, error = _ellipse_api_get(connection, "/api/v1/clients")
    if error == 404:
        return _empty_state(
            "link_required",
            "Your HIVE account is not linked to an active EllipseCRM user yet.",
            connection["integration"],
        )
    if error or not isinstance(payload, dict):
        return _empty_state(
            "unavailable",
            "Client summaries are temporarily unavailable.",
            connection["integration"],
        )

    remote_clients = payload.get("clients") if payload.get("ok") else None
    if not isinstance(remote_clients, list):
        return _empty_state(
            "unavailable",
            "Client summaries are temporarily unavailable.",
            connection["integration"],
        )

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

    connection["clients"] = clients
    return connection


def _ellipse_client_detail_context(external_client_id):
    connection = _ellipse_connection_context()
    if connection["state"] != "available":
        return connection

    payload, error = _ellipse_api_get(connection, f"/api/v1/clients/{int(external_client_id)}")
    if error == 404:
        connection.update({
            "state": "not_found",
            "message": "This client is not available to your linked EllipseCRM account.",
            "client": None,
        })
        return connection
    if error or not isinstance(payload, dict) or not payload.get("ok"):
        connection.update({
            "state": "unavailable",
            "message": "Client 360 is temporarily unavailable.",
            "client": None,
        })
        return connection

    item = payload.get("client")
    if not isinstance(item, dict) or not str(item.get("name") or "").strip():
        connection.update({
            "state": "unavailable",
            "message": "Client 360 returned an invalid client summary.",
            "client": None,
        })
        return connection

    connection["client"] = {
        "external_id": str(item.get("id") or "").strip(),
        "name": str(item.get("name") or "").strip(),
        "account_status": str(item.get("account_status") or "unknown").strip().lower(),
        "service_arrangement": str(item.get("service_arrangement") or "").strip(),
        "town_city": str(item.get("town_city") or "").strip(),
        "county": str(item.get("county") or "").strip(),
        "postcode": str(item.get("postcode") or "").strip(),
        "main_contact_name": str(item.get("main_contact_name") or "").strip(),
        "main_contact_email": str(item.get("main_contact_email") or "").strip(),
        "main_contact_phone": str(item.get("main_contact_phone") or "").strip(),
        "employee_count": item.get("employee_count"),
        "location_count": item.get("location_count"),
        "agreement_status": str(item.get("agreement_status") or "not_set").strip().lower(),
        "agreement_status_label": str(item.get("agreement_status_label") or "Not set").strip(),
        "open_cases": int(item.get("open_cases") or 0),
        "urgent_cases": int(item.get("urgent_cases") or 0),
        "open_actions": int(item.get("open_actions") or 0),
        "latest_activity_at": item.get("latest_activity_at"),
    }
    return connection


def _source_record(source_type, source_record_id):
    if source_type == "people_signal":
        record = Lead.query.filter_by(
            id=source_record_id,
            assigned_consultant_id=current_user.id,
        ).first()
        if not record:
            return None
        return {
            "source_type": source_type,
            "record_id": record.id,
            "source_label": "PeopleSignal",
            "title": record.company_name,
            "meta": (record.status or "new").replace("_", " ").title(),
            "url": url_for("lead_detail", lead_id=record.id),
        }

    if source_type == "directory_enquiry":
        from directory_enquiry_routes import DirectoryEnquiry

        record = DirectoryEnquiry.query.filter_by(
            id=source_record_id,
            assigned_consultant_id=current_user.id,
        ).first()
        if not record:
            return None
        return {
            "source_type": source_type,
            "record_id": record.id,
            "source_label": "Directory enquiry",
            "title": record.company_name,
            "meta": (record.status or "new").replace("_", " ").title(),
            "url": url_for(
                "directory_enquiries.consultant_directory_enquiry_detail",
                enquiry_id=record.id,
            ),
        }

    if source_type == "cover_request":
        record = CoverRequest.query.filter_by(
            id=source_record_id,
            consultant_id=current_user.id,
        ).first()
        if not record:
            return None
        cover_type = (record.cover_type or "Cover").replace("_", " ").title()
        return {
            "source_type": source_type,
            "record_id": record.id,
            "source_label": "HIVE Covered",
            "title": cover_type,
            "meta": f"{record.start_date:%d %b %Y} to {record.end_date:%d %b %Y}",
            "url": url_for("cover_detail", cover_id=record.id),
        }

    return None


def _linked_records(external_client_id):
    links = (
        ClientRecordLink.query
        .filter_by(
            consultant_id=current_user.id,
            external_client_id=str(external_client_id),
        )
        .order_by(ClientRecordLink.created_at.desc())
        .all()
    )
    rows = []
    for link in links:
        source = _source_record(link.source_type, link.source_record_id)
        rows.append({
            "link": link,
            "source": source,
        })
    return rows


def _link_candidates():
    linked_keys = {
        (link.source_type, link.source_record_id)
        for link in ClientRecordLink.query.filter_by(consultant_id=current_user.id).all()
    }
    rows = []

    leads = (
        Lead.query
        .filter_by(assigned_consultant_id=current_user.id)
        .order_by(Lead.updated_at.desc())
        .limit(50)
        .all()
    )
    for lead in leads:
        if ("people_signal", lead.id) not in linked_keys:
            rows.append(_source_record("people_signal", lead.id))

    from directory_enquiry_routes import DirectoryEnquiry

    enquiries = (
        DirectoryEnquiry.query
        .filter_by(assigned_consultant_id=current_user.id)
        .order_by(DirectoryEnquiry.updated_at.desc())
        .limit(50)
        .all()
    )
    for enquiry in enquiries:
        if ("directory_enquiry", enquiry.id) not in linked_keys:
            rows.append(_source_record("directory_enquiry", enquiry.id))

    covers = (
        CoverRequest.query
        .filter_by(consultant_id=current_user.id)
        .order_by(CoverRequest.updated_at.desc())
        .limit(50)
        .all()
    )
    for cover in covers:
        if ("cover_request", cover.id) not in linked_keys:
            rows.append(_source_record("cover_request", cover.id))

    return [row for row in rows if row]


def _consultancy_action_context(identity):
    visibility = or_(
        IntegrationEvent.consultant_id == current_user.id,
        and_(
            IntegrationEvent.consultant_id.is_(None),
            IntegrationEvent.hive_tenant_id == identity.hive_tenant_id,
        ),
    )
    rows = []
    integrations = (
        AppIntegration.query
        .filter(AppIntegration.is_enabled.is_(True))
        .order_by(AppIntegration.service_key.asc())
        .all()
    )
    for integration in integrations:
        if integration.service_key == "ellipsecrm" or not integration.app_module or not integration.app_module.is_active:
            continue
        access = ConsultantAppAccess.query.filter_by(
            consultant_id=current_user.id,
            app_module_id=integration.app_module_id,
            status="active",
        ).first()
        if not access:
            continue
        open_query = IntegrationEvent.query.filter(
            visibility,
            IntegrationEvent.app_integration_id == integration.id,
            IntegrationEvent.status == "open",
        )
        rows.append({
            "name": integration.app_module.name,
            "service_key": integration.service_key,
            "open_actions": open_query.count(),
            "urgent_actions": open_query.filter(IntegrationEvent.priority == "urgent").count(),
            "launch_url": url_for(
                "billing.integration_sso_launch",
                app_slug=integration.app_module.slug,
            ),
        })
    return rows


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

    @bp.route("/clients/<int:external_client_id>")
    @login_required
    def client_detail(external_client_id):
        if current_user.role != "consultant":
            return render_template("clients/detail.html", source_state=_empty_state(
                "forbidden",
                "Client 360 is available from a consultant account.",
            )), 403

        source_state = _ellipse_client_detail_context(external_client_id)
        if source_state["state"] != "available":
            return render_template(
                "clients/detail.html",
                source_state=source_state,
                client=None,
                linked_records=[],
                link_candidates=[],
                consultancy_products=[],
            ), 404 if source_state["state"] == "not_found" else 200

        identity = source_state["identity"]
        return render_template(
            "clients/detail.html",
            source_state=source_state,
            client=source_state["client"],
            linked_records=_linked_records(external_client_id),
            link_candidates=_link_candidates(),
            consultancy_products=_consultancy_action_context(identity),
        )

    @bp.route("/clients/<int:external_client_id>/links", methods=["POST"])
    @login_required
    def client_link_record(external_client_id):
        if current_user.role != "consultant":
            return redirect(url_for("dashboard"))

        source_state = _ellipse_client_detail_context(external_client_id)
        if source_state["state"] != "available":
            flash("That client is not currently available to your EllipseCRM account.", "danger")
            return redirect(url_for("notifications.client_list"))

        record_key = (request.form.get("record_key") or "").strip()
        if ":" not in record_key:
            flash("Choose a HIVE record to link.", "warning")
            return redirect(url_for("notifications.client_detail", external_client_id=external_client_id))

        source_type, source_record_id_raw = record_key.split(":", 1)
        if source_type not in SUPPORTED_LINK_TYPES or not source_record_id_raw.isdigit():
            flash("That HIVE record cannot be linked.", "danger")
            return redirect(url_for("notifications.client_detail", external_client_id=external_client_id))

        source_record_id = int(source_record_id_raw)
        source = _source_record(source_type, source_record_id)
        if not source:
            flash("That HIVE record is not available to your account.", "danger")
            return redirect(url_for("notifications.client_detail", external_client_id=external_client_id))

        existing = ClientRecordLink.query.filter_by(
            consultant_id=current_user.id,
            source_type=source_type,
            source_record_id=source_record_id,
        ).first()
        if existing:
            if existing.external_client_id == str(external_client_id):
                flash("That record is already linked to this client.", "info")
            else:
                flash("That record is already linked to another client. Unlink it there first.", "warning")
            return redirect(url_for("notifications.client_detail", external_client_id=external_client_id))

        identity = source_state["identity"]
        link = ClientRecordLink(
            consultant_id=current_user.id,
            hive_tenant_id=identity.hive_tenant_id,
            external_client_id=str(external_client_id),
            source_type=source_type,
            source_record_id=source_record_id,
        )
        db.session.add(link)
        db.session.commit()
        flash(f"Linked {source['source_label']} record to {source_state['client']['name']}.", "success")
        return redirect(url_for("notifications.client_detail", external_client_id=external_client_id))

    @bp.route("/clients/<int:external_client_id>/links/<int:link_id>/remove", methods=["POST"])
    @login_required
    def client_unlink_record(external_client_id, link_id):
        if current_user.role != "consultant":
            return redirect(url_for("dashboard"))

        link = ClientRecordLink.query.filter_by(
            id=link_id,
            consultant_id=current_user.id,
            external_client_id=str(external_client_id),
        ).first_or_404()
        db.session.delete(link)
        db.session.commit()
        flash("Client link removed. The source record itself was not changed.", "success")
        return redirect(url_for("notifications.client_detail", external_client_id=external_client_id))
