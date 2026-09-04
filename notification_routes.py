from datetime import datetime
from functools import wraps
import os
from urllib.parse import urlencode

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from itsdangerous import URLSafeTimedSerializer
from sqlalchemy import and_, or_

from extensions import db
from integration_models import HiveIdentity, IntegrationEvent
from models import AppModule, ConsultantAppAccess, Lead, User


notifications_bp = Blueprint("notifications", __name__)


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    recipient_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text)
    category = db.Column(db.String(100), default="general", nullable=False)
    link_url = db.Column(db.String(500))
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read_at = db.Column(db.DateTime)

    recipient = db.relationship("User", foreign_keys=[recipient_user_id])


SSO_APP_CONFIG = {
    "payscope": {
        "label": "PayScope",
        "audience": "payscope",
        "secret_env": "HIVE_SSO_PAYSCOPE_SECRET",
        "base_url_env": "PAYSCOPE_BASE_URL",
        "callback_path": "/auth/hive/callback",
    }
}


def admin_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("login"))
        if current_user.role != "admin":
            flash("You do not have permission to access that page.", "danger")
            return redirect(url_for("dashboard"))
        return view_func(*args, **kwargs)
    return wrapped_view


def consultant_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("login"))
        if current_user.role != "consultant":
            flash("You do not have permission to access that page.", "danger")
            return redirect(url_for("home"))
        return view_func(*args, **kwargs)
    return wrapped_view


def create_notification(recipient_user_id, title, message=None, category="general", link_url=None, commit=False):
    notification = Notification(
        recipient_user_id=recipient_user_id,
        title=title,
        message=message,
        category=category,
        link_url=link_url,
    )
    db.session.add(notification)
    if commit:
        db.session.commit()
    return notification


def notify_admins(title, message=None, category="admin", link_url=None, commit=False):
    admins = User.query.filter_by(role="admin", is_active=True).all()
    notifications = []
    for admin in admins:
        notifications.append(
            create_notification(
                recipient_user_id=admin.id,
                title=title,
                message=message,
                category=category,
                link_url=link_url,
                commit=False,
            )
        )
    if commit:
        db.session.commit()
    return notifications


def unread_notification_count(user):
    if not user or not user.is_authenticated:
        return 0
    return Notification.query.filter_by(recipient_user_id=user.id, is_read=False).count()


def _consultant_today_context(user):
    context = {
        "hive_open_action_count": 0,
        "hive_overdue_action_count": 0,
        "hive_dashboard_actions": [],
        "opportunity_count": 0,
    }

    if not user or not user.is_authenticated or user.role != "consultant":
        return context

    context["opportunity_count"] = Lead.query.filter(
        Lead.assigned_consultant_id == user.id,
        Lead.status.in_(["assigned", "accepted"]),
    ).count()

    identity = HiveIdentity.query.filter_by(user_id=user.id).first()
    if not identity:
        return context

    visibility = or_(
        IntegrationEvent.consultant_id == user.id,
        and_(
            IntegrationEvent.consultant_id.is_(None),
            IntegrationEvent.hive_tenant_id == identity.hive_tenant_id,
        ),
    )
    open_query = IntegrationEvent.query.filter(
        visibility,
        IntegrationEvent.status == "open",
    )

    context["hive_open_action_count"] = open_query.count()
    context["hive_overdue_action_count"] = open_query.filter(
        IntegrationEvent.event_type.ilike("%overdue%")
    ).count()
    context["hive_dashboard_actions"] = (
        open_query
        .order_by(IntegrationEvent.occurred_at.desc())
        .limit(5)
        .all()
    )
    return context


def _required_env(name):
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"{name} is not configured")
    return value


def _optional_env(name):
    return (os.getenv(name) or "").strip()


def _normalise_external_base_url(value):
    """
    External app base URLs must be app roots, not login pages.
    Strip common copied login paths defensively.
    """
    base_url = (value or "").strip().rstrip("/")
    for suffix in ("/login", "/auth/login"):
        if base_url.endswith(suffix):
            base_url = base_url[: -len(suffix)]
    return base_url.rstrip("/")


def _build_hive_sso_token(app_slug):
    app_config = SSO_APP_CONFIG.get(app_slug)
    if not app_config:
        raise RuntimeError("SSO launch is not configured for that app yet.")

    serializer = URLSafeTimedSerializer(
        secret_key=_required_env(app_config["secret_env"]),
        salt=os.getenv("HIVE_SSO_SALT", "hive-sso-launch"),
    )

    payload = {
        "iss": os.getenv("HIVE_SSO_ISSUER", "hive"),
        "aud": app_config["audience"],
        "hive_user_id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "role": current_user.role,
        "iat": int(datetime.utcnow().timestamp()),
    }

    return serializer.dumps(payload)


def _build_hive_sso_callback_url(app_slug):
    app_config = SSO_APP_CONFIG.get(app_slug)
    if not app_config:
        raise RuntimeError("SSO launch is not configured for that app yet.")

    base_url = _normalise_external_base_url(_required_env(app_config["base_url_env"]))
    return f"{base_url}{app_config['callback_path']}"


def _build_connected_app_rows():
    app_modules = AppModule.query.order_by(AppModule.name.asc()).all()
    rows = []

    for app_module in app_modules:
        sso_config = SSO_APP_CONFIG.get(app_module.slug)
        status_counts = {
            "active": ConsultantAppAccess.query.filter_by(app_module_id=app_module.id, status="active").count(),
            "requested": ConsultantAppAccess.query.filter_by(app_module_id=app_module.id, status="requested").count(),
            "inactive": ConsultantAppAccess.query.filter_by(app_module_id=app_module.id, status="inactive").count(),
            "suspended": ConsultantAppAccess.query.filter_by(app_module_id=app_module.id, status="suspended").count(),
        }
        total_access = sum(status_counts.values())

        sso_enabled = bool(sso_config)
        secret_present = False
        base_url_present = False
        callback_url = None
        health_status = "Standard launch"
        health_tone = "slate"

        if sso_config:
            secret_present = bool(_optional_env(sso_config["secret_env"]))
            base_url_raw = _optional_env(sso_config["base_url_env"])
            base_url = _normalise_external_base_url(base_url_raw)
            base_url_present = bool(base_url)
            callback_url = f"{base_url}{sso_config['callback_path']}" if base_url else None

            if secret_present and base_url_present:
                health_status = "SSO ready"
                health_tone = "green"
            elif secret_present or base_url_present:
                health_status = "Partial config"
                health_tone = "amber"
            else:
                health_status = "Missing config"
                health_tone = "red"

        rows.append(
            {
                "app": app_module,
                "is_active": app_module.is_active,
                "sso_enabled": sso_enabled,
                "secret_present": secret_present,
                "base_url_present": base_url_present,
                "callback_url": callback_url,
                "health_status": health_status,
                "health_tone": health_tone,
                "status_counts": status_counts,
                "total_access": total_access,
            }
        )

    return rows


@notifications_bp.app_context_processor
def inject_notification_count():
    context = {"unread_notification_count": unread_notification_count(current_user)}
    context.update(_consultant_today_context(current_user))
    return context


@notifications_bp.route("/apps/<app_slug>/hive-sso-launch")
@login_required
@consultant_required
def hive_sso_launch(app_slug):
    app_module = AppModule.query.filter_by(slug=app_slug, is_active=True).first()
    if not app_module:
        flash("That app is not currently available.", "danger")
        return redirect(url_for("apps_index"))

    access = ConsultantAppAccess.query.filter_by(
        consultant_id=current_user.id,
        app_module_id=app_module.id,
        status="active",
    ).first()

    if not access:
        flash(f"You do not currently have access to {app_module.name}.", "danger")
        return redirect(url_for("apps_index"))

    try:
        token = _build_hive_sso_token(app_slug)
        callback_url = _build_hive_sso_callback_url(app_slug)
    except RuntimeError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("apps_index"))

    return redirect(f"{callback_url}?{urlencode({'token': token})}")


@notifications_bp.route("/admin/connected-apps")
@login_required
@admin_required
def admin_connected_apps():
    rows = _build_connected_app_rows()
    totals = {
        "apps": len(rows),
        "sso_ready": sum(1 for row in rows if row["health_status"] == "SSO ready"),
        "active_users": sum(row["status_counts"]["active"] for row in rows),
        "pending_requests": sum(row["status_counts"]["requested"] for row in rows),
    }
    return render_template("admin/connected_apps.html", rows=rows, totals=totals)


@notifications_bp.route("/notifications")
@login_required
def notification_list():
    notifications = Notification.query.filter_by(
        recipient_user_id=current_user.id
    ).order_by(Notification.created_at.desc()).all()
    return render_template("notifications/list.html", notifications=notifications)


@notifications_bp.route("/notifications/<int:notification_id>/read", methods=["POST"])
@login_required
def mark_notification_read(notification_id):
    notification = Notification.query.filter_by(
        id=notification_id,
        recipient_user_id=current_user.id,
    ).first_or_404()

    notification.is_read = True
    notification.read_at = datetime.utcnow()
    db.session.commit()

    if notification.link_url:
        return redirect(notification.link_url)

    return redirect(url_for("notifications.notification_list"))


@notifications_bp.route("/notifications/mark-all-read", methods=["POST"])
@login_required
def mark_all_notifications_read():
    notifications = Notification.query.filter_by(
        recipient_user_id=current_user.id,
        is_read=False,
    ).all()

    for notification in notifications:
        notification.is_read = True
        notification.read_at = datetime.utcnow()

    db.session.commit()
    flash("Notifications marked as read.", "success")
    return redirect(url_for("notifications.notification_list"))


@notifications_bp.route("/admin/notifications")
@login_required
@admin_required
def admin_notifications():
    notifications = Notification.query.order_by(Notification.created_at.desc()).limit(200).all()
    return render_template("notifications/admin_list.html", notifications=notifications)


from client_routes import register_client_routes

register_client_routes(notifications_bp)
