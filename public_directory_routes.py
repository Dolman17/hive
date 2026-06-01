from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import or_

from extensions import db
from models import ConsultantProfile, Lead, User

try:
    from notification_routes import notify_admins
except ImportError:
    notify_admins = None


public_directory_bp = Blueprint("public_directory", __name__)


@public_directory_bp.route("/")
def landing():
    if current_user.is_authenticated:
        if current_user.role == "admin":
            return redirect(url_for("admin_dashboard"))

        return redirect(url_for("dashboard"))

    return render_template("public_landing.html")


@public_directory_bp.route("/join", methods=["GET", "POST"])
def join():
    if current_user.is_authenticated:
        if current_user.role == "admin":
            return redirect(url_for("admin_dashboard"))

        return redirect(url_for("dashboard"))

    if request.method == "POST":
        contact_name = request.form.get("contact_name", "").strip()
        consultancy_name = request.form.get("consultancy_name", "").strip()
        contact_email = request.form.get("contact_email", "").strip()
        contact_phone = request.form.get("contact_phone", "").strip()
        specialisms = request.form.get("specialisms", "").strip()
        location = request.form.get("location", "").strip()
        remote_work = request.form.get("remote_work", "").strip()
        interested_in = request.form.getlist("interested_in")
        notes = request.form.get("notes", "").strip()

        if not contact_name or not consultancy_name or not contact_email:
            flash("Please complete your name, consultancy name and email address.", "danger")
            return render_template(
                "consultant_join.html",
                form_data=request.form,
                selected_interests=interested_in,
            )

        support_needed = ", ".join(interested_in) if interested_in else "General Hive access"

        admin_notes_parts = [
            f"Remote work: {remote_work or 'Not specified'}",
        ]

        if notes:
            admin_notes_parts.append(f"Additional notes: {notes}")

        join_request = Lead(
            source="consultant_join_request",
            source_reference="Public join form",
            company_name=consultancy_name,
            contact_name=contact_name,
            contact_email=contact_email,
            contact_phone=contact_phone or None,
            sector=specialisms or None,
            location=location or None,
            signal_type="Consultant access request",
            signal_summary=(
                f"{contact_name} requested access to The Hive Consultant Portal. "
                f"Specialisms: {specialisms or 'Not specified'}. "
                f"Location: {location or 'Not specified'}."
            ),
            support_needed=support_needed,
            urgency="routine",
            status="new",
            admin_notes="\n".join(admin_notes_parts),
        )

        db.session.add(join_request)
        db.session.commit()

        if notify_admins:
            notify_admins(
                title="New consultant join request",
                message=f"{contact_name} from {consultancy_name} requested access to The Hive.",
                category="consultant_join_request",
                link_url=url_for("admin_lead_detail", lead_id=join_request.id),
            )

        return redirect(url_for("public_directory.join_thanks"))

    return render_template(
        "consultant_join.html",
        form_data={},
        selected_interests=[],
    )


@public_directory_bp.route("/join/thanks")
def join_thanks():
    return render_template("consultant_join_thanks.html")


@public_directory_bp.route("/directory")
def directory_index():
    q = request.args.get("q", "").strip()
    location = request.args.get("location", "").strip()
    remote = request.args.get("remote", "").strip()

    query = (
        ConsultantProfile.query
        .join(User, ConsultantProfile.user_id == User.id)
        .filter(User.role == "consultant")
        .filter(User.is_active == True)
        .filter(ConsultantProfile.is_public == True)
    )

    if q:
        like_term = f"%{q}%"
        query = query.filter(
            or_(
                ConsultantProfile.business_name.ilike(like_term),
                ConsultantProfile.bio.ilike(like_term),
                ConsultantProfile.specialisms.ilike(like_term),
                ConsultantProfile.sectors.ilike(like_term),
                User.name.ilike(like_term),
            )
        )

    if location:
        query = query.filter(ConsultantProfile.location.ilike(f"%{location}%"))

    if remote == "yes":
        query = query.filter(ConsultantProfile.remote_available == True)

    profiles = query.order_by(ConsultantProfile.business_name.asc(), User.name.asc()).all()

    return render_template(
        "public_directory/index.html",
        profiles=profiles,
        q=q,
        location=location,
        remote=remote,
    )


@public_directory_bp.route("/directory/<int:profile_id>")
def directory_profile(profile_id):
    profile = (
        ConsultantProfile.query
        .join(User, ConsultantProfile.user_id == User.id)
        .filter(ConsultantProfile.id == profile_id)
        .filter(User.role == "consultant")
        .filter(User.is_active == True)
        .filter(ConsultantProfile.is_public == True)
        .first_or_404()
    )

    return render_template("public_directory/profile.html", profile=profile)
