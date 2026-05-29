from datetime import datetime
from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import Subscription, User


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
