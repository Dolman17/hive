from flask import Blueprint, render_template, request
from sqlalchemy import or_

from models import ConsultantProfile, User


public_directory_bp = Blueprint("public_directory", __name__)


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
