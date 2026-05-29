from datetime import datetime
from functools import wraps

from flask import Blueprint, flash, redirect, render_template, url_for
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
        tier_label=TIER_LABELS.get(subscription.tier, subscription.tier.title())
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
