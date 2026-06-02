from datetime import datetime
from functools import wraps
import os
import re

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db, csrf
from models import AppModule, ConsultantAppAccess, Lead, Subscription, User


billing_bp = Blueprint("billing", __name__)


TIER_LABELS = {
    "free": "Free",
    "starter": "Starter",
    "professional": "Professional",
    "covered": "Covered",
    "boutique": "Boutique",
    "admin": "Admin",
}


TIER_CARDS = [
    {
        "tier": "starter",
        "label": "Starter",
        "strapline": "Website and basic toolkit access.",
        "features": ["Consultant website", "Toolkit resources", "Public profile page"],
    },
    {
        "tier": "professional",
        "label": "Professional",
        "strapline": "Core consultant operating tools.",
        "features": ["Everything in Starter", "App marketplace", "PeopleSignal leads", "RecruitFlow AI access path"],
    },
    {
        "tier": "covered",
        "label": "Covered",
        "strapline": "Continuity and client cover support.",
        "features": ["Everything in Professional", "HIVE Covered requests", "Holiday and sickness cover workflow"],
    },
    {
        "tier": "boutique",
        "label": "Boutique",
        "strapline": "Full HIVE support layer.",
        "features": ["Everything in Covered", "Expert Help", "Escalation support", "Premium consultant support workflow"],
    },
]


APP_TIER_OPTIONS = [
    ("free", "Free"),
    ("starter", "Starter"),
    ("professional", "Professional"),
    ("covered", "Covered"),
    ("boutique", "Boutique"),
    ("admin", "Admin"),
]


class BillingProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey("subscription.id"), nullable=False, unique=True)
    billing_email = db.Column(db.String(255))
    stripe_customer_id = db.Column(db.String(255))
    stripe_subscription_id = db.Column(db.String(255))
    stripe_price_id = db.Column(db.String(255))
    stripe_checkout_session_id = db.Column(db.String(255))
    current_period_end = db.Column(db.DateTime)
    cancel_at_period_end = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    subscription = db.relationship("Subscription", backref=db.backref("billing_profile", uselist=False))


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


def get_or_create_subscription(user):
    subscription = Subscription.query.filter_by(user_id=user.id).first()
    if subscription:
        return subscription

    subscription = Subscription(
        user_id=user.id,
        tier="admin" if user.role == "admin" else "boutique",
        status="active",
        notes="Auto-created by HIVE billing shell."
    )
    db.session.add(subscription)
    db.session.commit()
    return subscription


def get_or_create_billing_profile(subscription):
    profile = BillingProfile.query.filter_by(subscription_id=subscription.id).first()
    if profile:
        return profile

    profile = BillingProfile(subscription_id=subscription.id)
    if subscription.user:
        profile.billing_email = subscription.user.email
    db.session.add(profile)
    db.session.commit()
    return profile


def parse_date_or_none(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None


def app_slug_from_name(value):
    value = (value or "app").lower().strip()
    value = re.sub(r"[^a-z0-9\s-]", "", value)
    value = re.sub(r"[\s-]+", "-", value)
    value = value.strip("-")
    return value or "app"


def get_people_signal_token_from_header():
    auth_header = request.headers.get("Authorization", "").strip()

    if not auth_header.lower().startswith("bearer "):
        return ""

    return auth_header.split(" ", 1)[1].strip()


def build_people_signal_notes(payload):
    parts = []

    fields = [
        ("Title", payload.get("title")),
        ("PeopleSignal source", payload.get("signal_source") or payload.get("source")),
        ("Signal type", payload.get("signal_type")),
        ("Likely HR need", payload.get("likely_hr_need")),
        ("Outreach angle", payload.get("outreach_angle")),
        ("Source URL", payload.get("source_url")),
        ("Detected at", payload.get("detected_at")),
    ]

    for label, value in fields:
        if value:
            parts.append(f"{label}: {value}")

    summary = payload.get("summary")
    if summary:
        parts.append("")
        parts.append("Summary:")
        parts.append(str(summary))

    raw_text = payload.get("raw_text")
    if raw_text:
        parts.append("")
        parts.append("Raw PeopleSignal text:")
        parts.append(str(raw_text)[:4000])

    return "\n".join(parts).strip()


def normalise_urgency(value):
    if value is None or value == "":
        return "medium"

    try:
        score = float(value)
    except (TypeError, ValueError):
        lowered = str(value).strip().lower()
        if lowered in ["low", "medium", "high", "urgent"]:
            return lowered
        return "medium"

    if score >= 8:
        return "urgent"
    if score >= 6:
        return "high"
    if score >= 3:
        return "medium"
    return "low"


def normalise_score(value):
    if value is None or value == "":
        return None

    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


@billing_bp.route("/api/people-signal/leads", methods=["POST"])
@csrf.exempt
def import_people_signal_lead():
    expected_token = os.getenv("PEOPLE_SIGNAL_IMPORT_TOKEN", "").strip()

    if not expected_token:
        return jsonify({"ok": False, "error": "PeopleSignal import token is not configured."}), 500

    supplied_token = get_people_signal_token_from_header()

    if supplied_token != expected_token:
        return jsonify({"ok": False, "error": "Unauthorized."}), 401

    payload = request.get_json(silent=True) or {}

    external_signal_id = payload.get("external_signal_id") or payload.get("signal_id")
    company_name = (payload.get("company_name") or "").strip()

    if not external_signal_id:
        return jsonify({"ok": False, "error": "external_signal_id is required."}), 400

    if not company_name:
        return jsonify({"ok": False, "error": "company_name is required."}), 400

    source_reference = f"people_signal:{external_signal_id}"

    existing_lead = Lead.query.filter_by(
        source="people_signal",
        source_reference=source_reference,
    ).first()

    if existing_lead:
        return jsonify(
            {
                "ok": True,
                "created": False,
                "lead_id": existing_lead.id,
                "message": "Lead already exists.",
            }
        ), 200

    lead = Lead(
        source="people_signal",
        source_reference=source_reference,
        company_name=company_name[:255],
        contact_name=(payload.get("contact_name") or None),
        contact_email=(payload.get("contact_email") or None),
        contact_phone=(payload.get("contact_phone") or None),
        sector=(payload.get("sector") or None),
        employee_count=(payload.get("employee_count") or None),
        location=(payload.get("location") or None),
        signal_type=(payload.get("signal_type") or payload.get("signal_source") or None),
        signal_summary=(payload.get("summary") or payload.get("title") or None),
        support_needed=(payload.get("likely_hr_need") or None),
        urgency=normalise_urgency(payload.get("urgency_score") or payload.get("urgency")),
        people_signal_score=normalise_score(payload.get("confidence_score")),
        risk_level=payload.get("risk_level") or None,
        status="new",
        admin_notes=build_people_signal_notes(payload),
    )

    db.session.add(lead)
    db.session.commit()

    return jsonify(
        {
            "ok": True,
            "created": True,
            "lead_id": lead.id,
            "message": "Lead imported successfully.",
        }
    ), 201


@billing_bp.route("/admin/apps/new", methods=["GET", "POST"])
@login_required
@admin_required
def admin_app_new():
    if request.method == "POST":
        app_module = AppModule()
        populate_app_module_from_form(app_module)

        if not app_module.name:
            flash("App name is required.", "danger")
            return render_template("admin/app_form.html", app_module=app_module, tier_options=APP_TIER_OPTIONS, page_title="Add App")

        existing_slug = AppModule.query.filter_by(slug=app_module.slug).first()
        if existing_slug:
            flash("That app slug is already in use. Please choose another.", "danger")
            return render_template("admin/app_form.html", app_module=app_module, tier_options=APP_TIER_OPTIONS, page_title="Add App")

        db.session.add(app_module)
        db.session.commit()
        flash("App module created.", "success")
        return redirect(url_for("admin_apps"))

    app_module = AppModule(required_tier="professional", is_active=True, is_core=False)
    return render_template("admin/app_form.html", app_module=app_module, tier_options=APP_TIER_OPTIONS, page_title="Add App")


@billing_bp.route("/admin/apps/<int:app_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def admin_app_edit(app_id):
    app_module = AppModule.query.get_or_404(app_id)

    if request.method == "POST":
        old_slug = app_module.slug
        populate_app_module_from_form(app_module)

        if not app_module.name:
            flash("App name is required.", "danger")
            app_module.slug = old_slug
            return render_template("admin/app_form.html", app_module=app_module, tier_options=APP_TIER_OPTIONS, page_title="Edit App")

        existing_slug = AppModule.query.filter(AppModule.slug == app_module.slug, AppModule.id != app_module.id).first()
        if existing_slug:
            flash("That app slug is already in use. Please choose another.", "danger")
            app_module.slug = old_slug
            return render_template("admin/app_form.html", app_module=app_module, tier_options=APP_TIER_OPTIONS, page_title="Edit App")

        db.session.commit()
        flash("App module updated.", "success")
        return redirect(url_for("admin_apps"))

    return render_template("admin/app_form.html", app_module=app_module, tier_options=APP_TIER_OPTIONS, page_title="Edit App")


@billing_bp.route("/admin/apps/<int:app_id>/toggle", methods=["POST"])
@login_required
@admin_required
def admin_app_toggle(app_id):
    app_module = AppModule.query.get_or_404(app_id)
    app_module.is_active = not app_module.is_active
    db.session.commit()
    flash(f"{app_module.name} is now {'active' if app_module.is_active else 'inactive'}.", "success")
    return redirect(url_for("admin_apps"))


@billing_bp.route("/admin/apps/<int:app_id>/delete", methods=["POST"])
@login_required
@admin_required
def admin_app_delete(app_id):
    app_module = AppModule.query.get_or_404(app_id)

    access_count = ConsultantAppAccess.query.filter_by(app_module_id=app_module.id).count()
    if access_count > 0:
        flash("This app has consultant access records, so it has been marked inactive instead of deleted.", "warning")
        app_module.is_active = False
        db.session.commit()
        return redirect(url_for("admin_apps"))

    db.session.delete(app_module)
    db.session.commit()
    flash("App module deleted.", "success")
    return redirect(url_for("admin_apps"))


@billing_bp.route("/billing")
@login_required
@consultant_required
def billing_home():
    subscription = get_or_create_subscription(current_user)
    billing_profile = get_or_create_billing_profile(subscription)
    return render_template(
        "billing/index.html",
        subscription=subscription,
        billing_profile=billing_profile,
        tier_label=TIER_LABELS.get(subscription.tier, subscription.tier.title()),
        tier_cards=TIER_CARDS
    )


@billing_bp.route("/billing/pricing")
@login_required
@consultant_required
def billing_pricing():
    subscription = get_or_create_subscription(current_user)
    return render_template(
        "billing/pricing.html",
        subscription=subscription,
        tier_label=TIER_LABELS.get(subscription.tier, subscription.tier.title()),
        tier_cards=TIER_CARDS
    )


@billing_bp.route("/billing/checkout/<tier>")
@login_required
@consultant_required
def billing_checkout_placeholder(tier):
    subscription = get_or_create_subscription(current_user)
    billing_profile = get_or_create_billing_profile(subscription)
    return render_template(
        "billing/checkout_placeholder.html",
        requested_tier=tier,
        requested_tier_label=TIER_LABELS.get(tier, tier.title()),
        subscription=subscription,
        billing_profile=billing_profile
    )


@billing_bp.route("/billing/portal")
@login_required
@consultant_required
def billing_portal_placeholder():
    subscription = get_or_create_subscription(current_user)
    billing_profile = get_or_create_billing_profile(subscription)
    return render_template(
        "billing/portal_placeholder.html",
        subscription=subscription,
        billing_profile=billing_profile,
        tier_label=TIER_LABELS.get(subscription.tier, subscription.tier.title())
    )


@billing_bp.route("/admin/billing")
@login_required
@admin_required
def admin_billing():
    consultants = User.query.filter_by(role="consultant").order_by(User.name.asc()).all()
    rows = []
    for consultant in consultants:
        subscription = get_or_create_subscription(consultant)
        profile = get_or_create_billing_profile(subscription)
        rows.append({"consultant": consultant, "subscription": subscription, "billing_profile": profile})

    return render_template("admin/billing.html", rows=rows, tier_labels=TIER_LABELS)


@billing_bp.route("/admin/billing/<int:consultant_id>", methods=["GET", "POST"])
@login_required
@admin_required
def admin_billing_detail(consultant_id):
    consultant = User.query.filter_by(id=consultant_id, role="consultant").first_or_404()
    subscription = get_or_create_subscription(consultant)
    billing_profile = get_or_create_billing_profile(subscription)

    if request.method == "POST":
        billing_profile.billing_email = request.form.get("billing_email", "").strip() or None
        billing_profile.stripe_customer_id = request.form.get("stripe_customer_id", "").strip() or None
        billing_profile.stripe_subscription_id = request.form.get("stripe_subscription_id", "").strip() or None
        billing_profile.stripe_price_id = request.form.get("stripe_price_id", "").strip() or None
        billing_profile.stripe_checkout_session_id = request.form.get("stripe_checkout_session_id", "").strip() or None
        billing_profile.current_period_end = parse_date_or_none(request.form.get("current_period_end", "").strip())
        billing_profile.cancel_at_period_end = request.form.get("cancel_at_period_end") == "on"

        db.session.commit()
        flash("Billing metadata updated.", "success")
        return redirect(url_for("billing.admin_billing_detail", consultant_id=consultant.id))

    return render_template(
        "admin/billing_detail.html",
        consultant=consultant,
        subscription=subscription,
        billing_profile=billing_profile,
        tier_label=TIER_LABELS.get(subscription.tier, subscription.tier.title())
    )
