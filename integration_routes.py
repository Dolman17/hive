from __future__ import annotations

from datetime import datetime
import hmac
import os
from urllib.parse import quote
from uuid import uuid4

from flask import current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from itsdangerous import URLSafeTimedSerializer
from sqlalchemy import and_, or_

from extensions import csrf, db
from integration_models import AppIntegration, HiveIdentity, IntegrationEvent
from models import AppModule, ConsultantAppAccess, TenantSettings, User


VALID_PRIORITIES = {"low", "normal", "medium", "high", "urgent"}


def _get_bearer_token() -> str:
    auth_header = request.headers.get("Authorization", "").strip()
    if not auth_header.lower().startswith("bearer "):
        return ""
    return auth_header.split(" ", 1)[1].strip()


def _admin_allowed() -> bool:
    return bool(current_user.is_authenticated and current_user.role == "admin")


def _consultant_allowed() -> bool:
    return bool(current_user.is_authenticated and current_user.role == "consultant")


def get_or_create_hive_identity(user: User) -> HiveIdentity:
    identity = HiveIdentity.query.filter_by(user_id=user.id).first()
    if identity:
        if not identity.tenant_settings_id:
            tenant_settings = TenantSettings.query.filter_by(user_id=user.id).first()
            if tenant_settings:
                identity.tenant_settings_id = tenant_settings.id
                db.session.commit()
        return identity

    tenant_settings = TenantSettings.query.filter_by(user_id=user.id).first()
    identity = HiveIdentity(
        user_id=user.id,
        tenant_settings_id=tenant_settings.id if tenant_settings else None,
    )
    db.session.add(identity)
    db.session.commit()
    return identity


def _normalise_base_url(value: str) -> str:
    return (value or "").strip().rstrip("/")


def _normalise_path(value: str, default: str) -> str:
    path = (value or default).strip()
    if not path.startswith("/"):
        path = "/" + path
    return path


def _integration_token_env_name(integration: AppIntegration) -> str:
    if integration.event_token_env:
        return integration.event_token_env
    service_key = integration.service_key.upper().replace("-", "_")
    return f"HIVE_{service_key}_EVENT_TOKEN"


def _event_visible_to_user(event: IntegrationEvent, identity: HiveIdentity):
    return or_(
        IntegrationEvent.consultant_id == current_user.id,
        and_(
            IntegrationEvent.consultant_id.is_(None),
            IntegrationEvent.hive_tenant_id == identity.hive_tenant_id,
        ),
    )


def _parse_event_datetime(value):
    if not value:
        return datetime.utcnow()
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        return datetime.utcnow()


def register_integration_routes(bp):
    @bp.route("/integrations/action-centre")
    @login_required
    def integration_action_centre():
        if not _consultant_allowed():
            flash("You do not have permission to access that page.", "danger")
            return redirect(url_for("home"))

        identity = get_or_create_hive_identity(current_user)
        events = (
            IntegrationEvent.query
            .filter(_event_visible_to_user(IntegrationEvent, identity))
            .filter(IntegrationEvent.status == "open")
            .order_by(IntegrationEvent.occurred_at.desc())
            .limit(100)
            .all()
        )

        return render_template(
            "integrations/action_centre.html",
            events=events,
            identity=identity,
        )

    @bp.route("/integrations/actions/<int:event_id>/resolve", methods=["POST"])
    @login_required
    def integration_action_resolve(event_id):
        if not _consultant_allowed():
            flash("You do not have permission to perform that action.", "danger")
            return redirect(url_for("home"))

        identity = get_or_create_hive_identity(current_user)
        event = (
            IntegrationEvent.query
            .filter(IntegrationEvent.id == event_id)
            .filter(_event_visible_to_user(IntegrationEvent, identity))
            .first_or_404()
        )
        event.status = "resolved"
        event.resolved_at = datetime.utcnow()
        db.session.commit()
        flash("Action marked as resolved.", "success")
        return redirect(url_for("billing.integration_action_centre"))

    @bp.route("/integrations/apps/<app_slug>/launch")
    @login_required
    def integration_sso_launch(app_slug):
        if not _consultant_allowed():
            flash("You do not have permission to launch consultant apps.", "danger")
            return redirect(url_for("home"))

        app_module = AppModule.query.filter_by(slug=app_slug, is_active=True).first_or_404()
        access = ConsultantAppAccess.query.filter_by(
            consultant_id=current_user.id,
            app_module_id=app_module.id,
            status="active",
        ).first()
        if not access:
            flash(f"You do not currently have access to {app_module.name}.", "danger")
            return redirect(url_for("apps_index"))

        integration = AppIntegration.query.filter_by(
            app_module_id=app_module.id,
            is_enabled=True,
        ).first()
        if not integration:
            flash(f"{app_module.name} is not connected to HIVE SSO yet.", "warning")
            return redirect(url_for("apps_index"))

        signing_secret = os.getenv("HIVE_SSO_SIGNING_SECRET", "").strip()
        if not signing_secret:
            current_app.logger.error("HIVE_SSO_SIGNING_SECRET is not configured")
            flash("HIVE SSO is not configured yet. Please contact the HIVE administrator.", "danger")
            return redirect(url_for("apps_index"))

        identity = get_or_create_hive_identity(current_user)
        serializer = URLSafeTimedSerializer(
            signing_secret,
            salt="hive-product-sso-v1",
        )
        payload = {
            "sub": identity.hive_user_id,
            "tenant": identity.hive_tenant_id,
            "email": current_user.email,
            "name": current_user.name,
            "role": current_user.role,
            "app": integration.service_key,
            "aud": integration.sso_audience or integration.service_key,
            "jti": uuid4().hex,
            "iat": datetime.utcnow().isoformat() + "Z",
        }
        token = serializer.dumps(payload)
        target = f"{_normalise_base_url(integration.base_url)}{_normalise_path(integration.sso_path, '/auth/hive-sso')}?token={quote(token)}"
        return redirect(target)

    @bp.route("/api/integrations/v1/actions")
    @login_required
    def integration_actions_api():
        if not _consultant_allowed():
            return jsonify({"ok": False, "error": "Forbidden."}), 403

        identity = get_or_create_hive_identity(current_user)
        events = (
            IntegrationEvent.query
            .filter(_event_visible_to_user(IntegrationEvent, identity))
            .filter(IntegrationEvent.status == "open")
            .order_by(IntegrationEvent.occurred_at.desc())
            .limit(100)
            .all()
        )
        return jsonify({
            "ok": True,
            "count": len(events),
            "actions": [
                {
                    "id": event.id,
                    "app": event.app_integration.service_key,
                    "event_type": event.event_type,
                    "title": event.title,
                    "description": event.description,
                    "priority": event.priority,
                    "target_url": event.target_url,
                    "occurred_at": event.occurred_at.isoformat() + "Z",
                }
                for event in events
            ],
        })

    @bp.route("/api/integrations/v1/events", methods=["POST"])
    @csrf.exempt
    def integration_event_ingest():
        payload = request.get_json(silent=True) or {}
        service_key = (payload.get("app") or payload.get("service_key") or "").strip().lower()
        if not service_key:
            return jsonify({"ok": False, "error": "app is required."}), 400

        integration = AppIntegration.query.filter_by(service_key=service_key, is_enabled=True).first()
        if not integration:
            return jsonify({"ok": False, "error": "Unknown or disabled integration."}), 404

        expected_token = os.getenv(_integration_token_env_name(integration), "").strip()
        supplied_token = _get_bearer_token()
        if not expected_token:
            current_app.logger.error("No event token configured for integration %s", service_key)
            return jsonify({"ok": False, "error": "Integration token is not configured."}), 503
        if not supplied_token or not hmac.compare_digest(supplied_token, expected_token):
            return jsonify({"ok": False, "error": "Unauthorized."}), 401

        external_event_id = str(payload.get("external_event_id") or payload.get("event_id") or "").strip()
        event_type = str(payload.get("event_type") or "").strip()
        title = str(payload.get("title") or "").strip()
        if not external_event_id or not event_type or not title:
            return jsonify({"ok": False, "error": "external_event_id, event_type and title are required."}), 400

        existing = IntegrationEvent.query.filter_by(
            app_integration_id=integration.id,
            external_event_id=external_event_id,
        ).first()
        if existing:
            return jsonify({"ok": True, "created": False, "event_id": existing.id}), 200

        consultant_id = None
        hive_user_id = str(payload.get("hive_user_id") or "").strip()
        if hive_user_id:
            identity = HiveIdentity.query.filter_by(hive_user_id=hive_user_id).first()
            if identity:
                consultant_id = identity.user_id

        priority = str(payload.get("priority") or "normal").strip().lower()
        if priority not in VALID_PRIORITIES:
            priority = "normal"

        event = IntegrationEvent(
            app_integration_id=integration.id,
            consultant_id=consultant_id,
            hive_tenant_id=(str(payload.get("hive_tenant_id") or "").strip() or None),
            external_event_id=external_event_id,
            event_type=event_type[:150],
            title=title[:255],
            description=payload.get("description") or payload.get("summary"),
            priority=priority,
            target_url=(str(payload.get("target_url") or "").strip() or None),
            status="open",
            occurred_at=_parse_event_datetime(payload.get("occurred_at")),
        )
        db.session.add(event)
        db.session.commit()
        return jsonify({"ok": True, "created": True, "event_id": event.id}), 201

    @bp.route("/admin/integrations", methods=["GET", "POST"])
    @login_required
    def admin_integrations():
        if not _admin_allowed():
            flash("You do not have permission to access that page.", "danger")
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            app_module_id = request.form.get("app_module_id", type=int)
            app_module = AppModule.query.get_or_404(app_module_id)
            integration = AppIntegration.query.filter_by(app_module_id=app_module.id).first()
            if not integration:
                integration = AppIntegration(
                    app_module_id=app_module.id,
                    service_key=app_module.slug,
                    base_url="",
                )
                db.session.add(integration)

            service_key = (request.form.get("service_key") or app_module.slug).strip().lower()
            base_url = _normalise_base_url(request.form.get("base_url") or "")
            if not service_key or not base_url:
                flash("Service key and base URL are required.", "danger")
                return redirect(url_for("billing.admin_integrations"))

            integration.service_key = service_key
            integration.base_url = base_url
            integration.sso_path = _normalise_path(request.form.get("sso_path"), "/auth/hive-sso")
            integration.sso_audience = (request.form.get("sso_audience") or service_key).strip()
            integration.event_token_env = (request.form.get("event_token_env") or "").strip() or None
            integration.summary_path = _normalise_path(request.form.get("summary_path"), "/api/v1/summary")
            integration.health_path = _normalise_path(request.form.get("health_path"), "/api/v1/health")
            integration.is_enabled = request.form.get("is_enabled") == "on"
            db.session.commit()

            flash(f"Integration settings saved for {app_module.name}.", "success")
            return redirect(url_for("billing.admin_integrations"))

        app_modules = AppModule.query.order_by(AppModule.name.asc()).all()
        integrations = AppIntegration.query.all()
        integration_map = {item.app_module_id: item for item in integrations}
        return render_template(
            "admin/integrations.html",
            app_modules=app_modules,
            integration_map=integration_map,
        )
