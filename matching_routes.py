from functools import wraps

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from models import ConsultantProfile, Subscription, User
from directory_enquiry_routes import DirectoryEnquiry


matching_bp = Blueprint("matching", __name__)


TIER_RANKS = {
    "free": 0,
    "starter": 10,
    "professional": 20,
    "covered": 30,
    "boutique": 40,
    "admin": 100,
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


def normalise_words(value):
    if not value:
        return set()
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in value)
    return {word for word in cleaned.split() if len(word) >= 3}


def contains_any(haystack, needles):
    if not haystack or not needles:
        return False
    haystack_words = normalise_words(haystack)
    return bool(haystack_words.intersection(needles))


def score_consultant(enquiry, consultant, profile, subscription):
    score = 0
    reasons = []

    enquiry_words = normalise_words(enquiry.support_needed)
    company_words = normalise_words(enquiry.company_name)
    all_words = enquiry_words.union(company_words)

    if contains_any(profile.specialisms, all_words):
        score += 35
        reasons.append("Specialism match")

    if contains_any(profile.sectors, all_words):
        score += 20
        reasons.append("Sector match")

    if profile.remote_available:
        score += 10
        reasons.append("Remote available")

    if profile.insurance_verified:
        score += 10
        reasons.append("Insurance verified")

    if profile.qualifications_verified:
        score += 10
        reasons.append("Qualifications verified")

    if profile.is_public:
        score += 5
        reasons.append("Public profile")

    if subscription and subscription.status in ["active", "trial"]:
        score += 5
        reasons.append("Active subscription")

        tier_rank = TIER_RANKS.get(subscription.tier, 0)
        if tier_rank >= TIER_RANKS["professional"]:
            score += 5
            reasons.append("Professional tier or above")
        if tier_rank >= TIER_RANKS["boutique"]:
            score += 5
            reasons.append("Boutique tier")

    if enquiry.assigned_consultant_id == consultant.id:
        score += 15
        reasons.append("Currently assigned")

    if not reasons:
        reasons.append("General availability")

    return min(score, 100), reasons


def build_matches(enquiry):
    consultants = User.query.filter_by(role="consultant", is_active=True).order_by(User.name.asc()).all()
    results = []

    for consultant in consultants:
        profile = ConsultantProfile.query.filter_by(user_id=consultant.id).first()
        if not profile:
            continue

        subscription = Subscription.query.filter_by(user_id=consultant.id).first()
        score, reasons = score_consultant(enquiry, consultant, profile, subscription)

        results.append({
            "consultant": consultant,
            "profile": profile,
            "subscription": subscription,
            "score": score,
            "reasons": reasons,
        })

    return sorted(results, key=lambda row: row["score"], reverse=True)


@matching_bp.route("/admin/directory-enquiries/<int:enquiry_id>/matches")
@login_required
@admin_required
def enquiry_matches(enquiry_id):
    enquiry = DirectoryEnquiry.query.get_or_404(enquiry_id)
    matches = build_matches(enquiry)
    return render_template("matching/enquiry_matches.html", enquiry=enquiry, matches=matches)


@matching_bp.route("/admin/directory-enquiries/<int:enquiry_id>/assign/<int:consultant_id>", methods=["POST"])
@login_required
@admin_required
def assign_match(enquiry_id, consultant_id):
    enquiry = DirectoryEnquiry.query.get_or_404(enquiry_id)
    consultant = User.query.filter_by(id=consultant_id, role="consultant", is_active=True).first_or_404()

    enquiry.assigned_consultant_id = consultant.id
    enquiry.status = "assigned"

    from extensions import db
    db.session.commit()

    flash(f"Enquiry assigned to {consultant.name}.", "success")
    return redirect(url_for("directory_enquiries.admin_directory_enquiry_detail", enquiry_id=enquiry.id))
