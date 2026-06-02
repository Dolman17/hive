from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import ConsultantProfile, Subscription, TenantSettings, User


admin_users_bp = Blueprint("admin_users", __name__)


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
    cleaned = []
    previous_dash = False

    for char in value:
        if char.isalnum():
            cleaned.append(char)
            previous_dash = False
        elif not previous_dash:
            cleaned.append("-")
            previous_dash = True

    slug = "".join(cleaned).strip("-")
    return slug or "consultant"


def unique_tenant_slug(base_value):
    base_slug = slugify(base_value)
    candidate = base_slug
    counter = 2

    while TenantSettings.query.filter_by(tenant_slug=candidate).first():
        candidate = f"{base_slug}-{counter}"
        counter += 1

    return candidate


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


@admin_users_bp.route("/admin/users")
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
        query = query.filter((User.name.ilike(like_term)) | (User.email.ilike(like_term)))

    users = query.order_by(User.created_at.desc(), User.name.asc()).all()

    return render_template(
        "admin/users.html",
        users=users,
        selected_role=role,
        selected_status=status,
        q=q,
    )


@admin_users_bp.route("/admin/users/new", methods=["GET", "POST"])
@login_required
@admin_required
def admin_user_new():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        role = request.form.get("role", "consultant").strip()
        password = request.form.get("password", "").strip()
        is_active = request.form.get("is_active") == "on"
        business_name = request.form.get("business_name", "").strip()
        tier = request.form.get("tier", "boutique").strip()

        if role not in [option[0] for option in ROLE_OPTIONS]:
            role = "consultant"

        if not name or not email or not password:
            flash("Name, email and password are required.", "danger")
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
        user.set_password(password)
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
        return redirect(url_for("admin_users.admin_users"))

    return render_template(
        "admin/user_form.html",
        user=None,
        role_options=ROLE_OPTIONS,
        tier_options=TIER_OPTIONS,
        form_data={},
    )


@admin_users_bp.route("/admin/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def admin_user_edit(user_id):
    user = User.query.get_or_404(user_id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        role = request.form.get("role", user.role).strip()
        password = request.form.get("password", "").strip()
        is_active = request.form.get("is_active") == "on"
        business_name = request.form.get("business_name", "").strip()
        tier = request.form.get("tier", "boutique").strip()

        if role not in [option[0] for option in ROLE_OPTIONS]:
            role = user.role

        if not name or not email:
            flash("Name and email are required.", "danger")
            return redirect(url_for("admin_users.admin_user_edit", user_id=user.id))

        existing_user = User.query.filter(User.email == email, User.id != user.id).first()

        if existing_user:
            flash("Another user already has that email address.", "danger")
            return redirect(url_for("admin_users.admin_user_edit", user_id=user.id))

        if user.id == current_user.id:
            role = "admin"
            is_active = True

        user.name = name
        user.email = email
        user.role = role
        user.is_active = is_active

        if password:
            user.set_password(password)

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
        return redirect(url_for("admin_users.admin_users"))

    return render_template(
        "admin/user_form.html",
        user=user,
        role_options=ROLE_OPTIONS,
        tier_options=TIER_OPTIONS,
        form_data={},
    )
