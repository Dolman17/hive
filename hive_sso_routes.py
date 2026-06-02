from __future__ import annotations

import os
from datetime import datetime
from functools import wraps
from urllib.parse import urlencode

from flask import Blueprint, flash, redirect, url_for
from flask_login import current_user, login_required
from itsdangerous import URLSafeTimedSerializer

from extensions import db
from models import AppModule, ConsultantAppAccess


hive_sso_bp = Blueprint("hive_sso", __name__)


APP_CONFIG = {
    "payscope": {
        "audience": "payscope",
        "base_url_env": "PAYSCOPE_BASE_URL",
        "secret_env": "HIVE_SSO_PAYSCOPE_SECRET",
        "callback_path": "/auth/hive/callback",
    },
}


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


def _required_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"{name} is not configured")
    return value


def _build_serializer(secret: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        secret_key=secret,
        salt=os.getenv("HIVE_SSO_SALT", "hive-sso-launch"),
    )


def _target_callback_url(app_slug: str) -> str:
    app_config = APP_CONFIG[app_slug]
    base_url = _required_env(app_config["base_url_env"]).rstrip("/")
    callback_path = app_config["callback_path"]
    if not callback_path.startswith("/"):
        callback_path = f"/{callback_path}"
    return f"{base_url}{callback_path}"


def _build_launch_token(app_slug: str) -> str:
    app_config = APP_CONFIG[app_slug]
    serializer = _build_serializer(_required_env(app_config["secret_env"]))

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


def _get_active_access_or_none(app_slug: str):
    app_module = AppModule.query.filter_by(slug=app_slug, is_active=True).first()
    if not app_module:
        return None, None

    access = ConsultantAppAccess.query.filter_by(
        consultant_id=current_user.id,
        app_module_id=app_module.id,
        status="active",
    ).first()

    return app_module, access


@hive_sso_bp.route("/apps/<app_slug>/hive-sso-launch")
@login_required
@consultant_required
def hive_sso_launch(app_slug):
    if app_slug not in APP_CONFIG:
        flash("SSO launch is not configured for that app yet.", "warning")
        return redirect(url_for("apps_index"))

    app_module, access = _get_active_access_or_none(app_slug)
    if not app_module or not access:
        flash("You do not currently have active access to that app.", "danger")
        return redirect(url_for("apps_index"))

    try:
        token = _build_launch_token(app_slug)
        callback_url = _target_callback_url(app_slug)
    except RuntimeError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("apps_index"))

    query_string = urlencode({"token": token})
    return redirect(f"{callback_url}?{query_string}")
