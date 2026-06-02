import re
from datetime import datetime
from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from extensions import db
from models import ConsultantAccessRequest, ConsultantProfile, Subscription, TenantSettings, User

try:
    from notification_routes import notify_admins
except ImportError:
    notify_admins = None


public_directory_bp = Blueprint("public_directory", __name__)


ROLE_OPTIONS = [
    ("admin", "Admin"),
    ("consultant", "Consultant"),
]


TIER_OPTIONS = [
    ("free", "Free"),
    ("starter", "Starter"),
    ("professional", "Professional"),
    ("covered", "Covered"),
    ("boutique", "Boutique"),
    ("admin", "Admin"),
]


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


def slugify(value):
    value = (value or "consultant").lower().strip()
    value = re.sub(r"[^a-z0-9\s-]", "", value)
    value = re.sub(r"[\s-]+", "-", value)
    value = value.strip("-")
    return value or "consultant"


def unique_tenant_slug(base_value):
    base_slug = slugify(base_value)
    slug = base_slug
    counter = 2

    while TenantSettings.query.filter_by(tenant_slug=slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1

    return slug


def remote_flag_from_request(value):
    return value in ["Yes - remote and in-person", "Yes - remote only"]


def ensure_consultant_setup(user, business_name=None, tier="boutique"):
    if user.role != "consultant":
        return

    if not user.consultant_profile:
        profile = ConsultantProfile(
            user_id=user.id,
            business_name=business_name or user.name,
            remote_available=True,
            is_public=False,
            insurance_verified=False,
            qualifications_verified=False,
        )
        db.session.add(profile)

    if not user.tenant_settings:
        tenant_settings = TenantSettings(
            user_id=user.id,
            tenant_slug=unique_tenant_slug(business_name or user.name),
            business_name=business_name or user.name,
            strapline="Independent HR and people support.",
            primary_colour="#0D1B2A",
            accent_colour="#D4A017",
            text_colour="#1f2937",
            contact_email=user.email,
            is_published=False,
        )
        db.session.add(tenant_settings)

    if not user.subscription:
        subscription = Subscription(
            user_id=user.id,
            tier=tier or "boutique",
            status="active",
            notes="Created via admin user management.",
        )
        db.session.add(subscription)


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
        contact_email = request.form.get("contact_email", "").strip().lower()
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

        access_request = ConsultantAccessRequest(
            contact_name=contact_name,
            consultancy_name=consultancy_name,
            contact_email=contact_email,
            contact_phone=contact_phone or None,
            specialisms=specialisms or None,
            location=location or None,
            remote_work=remote_work or None,
            interested_in=", ".join(interested_in) if interested_in else None,
            notes=notes or None,
            status="new",
        )

        db.session.add(access_request)
        db.session.commit()

        if notify_admins:
            notify_admins(
                title="New consultant access request",
                message=f"{contact_name} from {consultancy_name} requested access to The Hive.",
                category="consultant_access_request",
                link_url=url_for("public_directory.admin_access_request_detail", request_id=access_request.id),
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


@public_directory_bp.route("/admin/users")
@login_required
@admin_required
def admin_users():
    role = request.args.get("role", "").strip()
    status = request.args.get("status", "").strip()
    q = request.args.get("q", "").strip()

    query = User.query

    if role:
        query = query.filter(User.role == role)

    if status == "active":
        query = query.filter(User.is_active == True)
    elif status == "inactive":
        query = query.filter(User.is_active == False)

    if q:
        like_term = f"%{q}%"
        query = query.filter(or_(User.name.ilike(like_term), User.email.ilike(like_term)))

    users = query.order_by(User.created_at.desc(), User.name.asc()).all()

    return render_template(
        "admin/users.html",
        users=users,
        selected_role=role,
        selected_status=status,
        q=q,
    )


@public_directory_bp.route("/admin/users/new", methods=["GET", "POST"])
@login_required
@admin_required
def admin_user_new():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        role = request.form.get("role", "consultant").strip()
        access_key = request.form.get("access_key", "").strip()
        is_active = request.form.get("is_active") == "on"
        business_name = request.form.get("business_name", "").strip()
        tier = request.form.get("tier", "boutique").strip()

        if role not in [option[0] for option in ROLE_OPTIONS]:
            role = "consultant"

        if not name or not email or not access_key:
            flash("Name, email and access key are required.", "danger")
            return render_template(
                "admin/user_form.html",
                user=None,
                role_options=ROLE_OPTIONS,
                tier_options=TIER_OPTIONS,
                form_data=request.form,
            )

        existing_user = User.query.filter_by(email=email).first()

        if existing_user:
            flash("A user with this email address already exists.", "danger")
            return render_template(
                "admin/user_form.html",
                user=None,
                role_options=ROLE_OPTIONS,
                tier_options=TIER_OPTIONS,
                form_data=request.form,
            )

        user = User(
            name=name,
            email=email,
            role=role,
            is_active=is_active,
        )
        user.set_password(access_key)
        db.session.add(user)
        db.session.flush()

        if role == "admin":
            subscription = Subscription(
                user_id=user.id,
                tier="admin",
                status="active",
                notes="Created via admin user management.",
            )
            db.session.add(subscription)
        else:
            ensure_consultant_setup(user, business_name=business_name or name, tier=tier)

        db.session.commit()

        flash(f"User created: {user.email}", "success")
        return redirect(url_for("public_directory.admin_users"))

    return render_template(
        "admin/user_form.html",
        user=None,
        role_options=ROLE_OPTIONS,
        tier_options=TIER_OPTIONS,
        form_data={},
    )


@public_directory_bp.route("/admin/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def admin_user_edit(user_id):
    user = User.query.get_or_404(user_id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        role = request.form.get("role", user.role).strip()
        access_key = request.form.get("access_key", "").strip()
        is_active = request.form.get("is_active") == "on"
        business_name = request.form.get("business_name", "").strip()
        tier = request.form.get("tier", "boutique").strip()

        if role not in [option[0] for option in ROLE_OPTIONS]:
            role = user.role

        if not name or not email:
            flash("Name and email are required.", "danger")
            return redirect(url_for("public_directory.admin_user_edit", user_id=user.id))

        existing_user = User.query.filter(User.email == email, User.id != user.id).first()

        if existing_user:
            flash("Another user already has that email address.", "danger")
            return redirect(url_for("public_directory.admin_user_edit", user_id=user.id))

        if user.id == current_user.id:
            role = "admin"
            is_active = True

        user.name = name
        user.email = email
        user.role = role
        user.is_active = is_active

        if access_key:
            user.set_password(access_key)

        if role == "consultant":
            ensure_consultant_setup(user, business_name=business_name or name, tier=tier)

            if user.consultant_profile and business_name:
                user.consultant_profile.business_name = business_name

            if user.subscription:
                user.subscription.tier = tier or user.subscription.tier
                user.subscription.status = "active"
        elif user.subscription:
            user.subscription.tier = "admin"
            user.subscription.status = "active"

        db.session.commit()

        flash(f"User updated: {user.email}", "success")
        return redirect(url_for("public_directory.admin_users"))

    return render_template(
        "admin/user_form.html",
        user=user,
        role_options=ROLE_OPTIONS,
        tier_options=TIER_OPTIONS,
        form_data={},
    )


@public_directory_bp.route("/admin/access-requests")
@login_required
@admin_required
def admin_access_requests():
    status = request.args.get("status", "").strip()

    query = ConsultantAccessRequest.query

    if status:
        query = query.filter(ConsultantAccessRequest.status == status)

    access_requests = query.order_by(ConsultantAccessRequest.created_at.desc()).all()

    return render_template(
        "admin/access_requests.html",
        access_requests=access_requests,
        selected_status=status,
    )


@public_directory_bp.route("/admin/access-requests/<int:request_id>", methods=["GET", "POST"])
@login_required
@admin_required
def admin_access_request_detail(request_id):
    access_request = ConsultantAccessRequest.query.get_or_404(request_id)

    if request.method == "POST":
        action = request.form.get("action", "save")
        access_request.admin_notes = request.form.get("admin_notes", "").strip() or None

        if action == "mark_reviewing" and access_request.status == "new":
            access_request.status = "reviewing"
            flash("Access request marked as reviewing.", "success")

        elif action == "reject":
            access_request.status = "rejected"
            access_request.rejected_at = datetime.utcnow()
            flash("Access request rejected.", "success")

        elif action == "approve":
            if access_request.created_user_id:
                flash("This access request has already been approved.", "warning")
                db.session.commit()
                return redirect(url_for("public_directory.admin_access_request_detail", request_id=access_request.id))

            temp_password = request.form.get("temp_password", "").strip()

            if not temp_password:
                flash("Please enter a temporary password before approving access.", "danger")
                return redirect(url_for("public_directory.admin_access_request_detail", request_id=access_request.id))

            existing_user = User.query.filter_by(email=access_request.contact_email).first()

            if existing_user:
                flash("A user with this email address already exists. Link manually or use a different email.", "danger")
                return redirect(url_for("public_directory.admin_access_request_detail", request_id=access_request.id))

            user = User(
                email=access_request.contact_email,
                name=access_request.contact_name,
                role="consultant",
                is_active=True,
            )
            user.set_password(temp_password)
            db.session.add(user)
            db.session.flush()

            profile = ConsultantProfile(
                user_id=user.id,
                business_name=access_request.consultancy_name,
                bio=access_request.notes,
                specialisms=access_request.specialisms,
                location=access_request.location,
                remote_available=remote_flag_from_request(access_request.remote_work),
                is_public=False,
                insurance_verified=False,
                qualifications_verified=False,
            )
            db.session.add(profile)

            tenant_settings = TenantSettings(
                user_id=user.id,
                tenant_slug=unique_tenant_slug(access_request.consultancy_name or access_request.contact_name),
                business_name=access_request.consultancy_name,
                strapline="Independent HR and people support.",
                primary_colour="#0D1B2A",
                accent_colour="#D4A017",
                text_colour="#1f2937",
                website_intro="Independent HR consultancy support tailored to your organisation.",
                about_text=access_request.notes or "Add a short introduction about your consultancy, your experience and how you help clients.",
                services_text=access_request.specialisms or "HR consultancy support\nRecruitment support\nEmployee relations advice",
                sectors_text="",
                contact_email=access_request.contact_email,
                contact_phone=access_request.contact_phone,
                cta_label="Book a discovery call",
                cta_url="",
                is_published=False,
            )
            db.session.add(tenant_settings)

            subscription = Subscription(
                user_id=user.id,
                tier="boutique",
                status="active",
                notes="Created automatically when consultant access request was approved.",
            )
            db.session.add(subscription)

            access_request.status = "approved"
            access_request.approved_at = datetime.utcnow()
            access_request.created_user_id = user.id

            flash("Access approved and consultant account created.", "success")

        else:
            flash("Access request notes updated.", "success")

        db.session.commit()
        return redirect(url_for("public_directory.admin_access_request_detail", request_id=access_request.id))

    return render_template("admin/access_request_detail.html", access_request=access_request)


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
