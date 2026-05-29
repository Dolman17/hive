from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import ConsultantProfile, User


consultant_profiles_bp = Blueprint("consultant_profiles", __name__)


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


def get_or_create_consultant_profile(user):
    profile = ConsultantProfile.query.filter_by(user_id=user.id).first()
    if profile:
        return profile

    profile = ConsultantProfile(
        user_id=user.id,
        business_name=user.name,
        remote_available=True,
        is_public=False,
    )
    db.session.add(profile)
    db.session.commit()
    return profile


def update_profile_from_request(profile):
    profile.business_name = request.form.get("business_name", "").strip() or None
    profile.bio = request.form.get("bio", "").strip() or None
    profile.specialisms = request.form.get("specialisms", "").strip() or None
    profile.sectors = request.form.get("sectors", "").strip() or None
    profile.location = request.form.get("location", "").strip() or None
    profile.remote_available = request.form.get("remote_available") == "on"
    profile.is_public = request.form.get("is_public") == "on"


def update_admin_verification_from_request(profile):
    profile.insurance_verified = request.form.get("insurance_verified") == "on"
    profile.qualifications_verified = request.form.get("qualifications_verified") == "on"
    profile.is_public = request.form.get("is_public") == "on"


@consultant_profiles_bp.route("/profile")
@login_required
@consultant_required
def profile_detail():
    profile = get_or_create_consultant_profile(current_user)
    return render_template("profile/detail.html", profile=profile)


@consultant_profiles_bp.route("/profile/edit", methods=["GET", "POST"])
@login_required
@consultant_required
def profile_edit():
    profile = get_or_create_consultant_profile(current_user)

    if request.method == "POST":
        update_profile_from_request(profile)
        db.session.commit()
        flash("Consultant profile updated.", "success")
        return redirect(url_for("consultant_profiles.profile_detail"))

    return render_template("profile/edit.html", profile=profile)


@consultant_profiles_bp.route("/admin/consultants")
@login_required
@admin_required
def admin_consultants():
    consultants = User.query.filter_by(role="consultant").order_by(User.name.asc()).all()
    rows = []

    for consultant in consultants:
        profile = get_or_create_consultant_profile(consultant)
        rows.append({"consultant": consultant, "profile": profile})

    return render_template("admin/consultants.html", rows=rows)


@consultant_profiles_bp.route("/admin/consultants/<int:consultant_id>")
@login_required
@admin_required
def admin_consultant_detail(consultant_id):
    consultant = User.query.filter_by(id=consultant_id, role="consultant").first_or_404()
    profile = get_or_create_consultant_profile(consultant)
    return render_template("admin/consultant_detail.html", consultant=consultant, profile=profile)


@consultant_profiles_bp.route("/admin/consultants/<int:consultant_id>/profile", methods=["GET", "POST"])
@login_required
@admin_required
def admin_consultant_profile_edit(consultant_id):
    consultant = User.query.filter_by(id=consultant_id, role="consultant").first_or_404()
    profile = get_or_create_consultant_profile(consultant)

    if request.method == "POST":
        update_profile_from_request(profile)
        update_admin_verification_from_request(profile)
        db.session.commit()
        flash("Consultant profile and verification settings updated.", "success")
        return redirect(url_for("consultant_profiles.admin_consultant_detail", consultant_id=consultant.id))

    return render_template("admin/consultant_profile_form.html", consultant=consultant, profile=profile)
