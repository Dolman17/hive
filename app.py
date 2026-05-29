import os
import re
from datetime import datetime
from functools import wraps
from uuid import uuid4

from flask import (
    Flask,
    render_template,
    redirect,
    url_for,
    flash,
    request,
    current_app,
    send_from_directory
)
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename

from config import Config
from billing_routes import billing_bp
from consultant_profile_routes import consultant_profiles_bp
from public_directory_routes import public_directory_bp
from directory_enquiry_routes import directory_enquiries_bp

from extensions import db, migrate, login_manager, csrf
from forms import (
    LoginForm,
    TenantSettingsForm,
    ResourceForm,
    CoverRequestForm,
    CoverClientForm,
    AdminCoverStatusForm,
    PeopleSignalLeadForm,
    AdminLeadForm,
    ConsultantLeadNotesForm,
    ExpertRequestForm,
    AdminExpertRequestForm,
    SubscriptionForm
)
from models import (
    User,
    TenantSettings,
    AppModule,
    ConsultantAppAccess,
    Resource,
    CoverRequest,
    CoverClient,
    Lead,
    ExpertRequest,
    Subscription
)


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(os.path.join(app.config["UPLOAD_FOLDER"], "logos"), exist_ok=True)
    os.makedirs(os.path.join(app.config["UPLOAD_FOLDER"], "resources"), exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    app.register_blueprint(billing_bp)
    app.register_blueprint(consultant_profiles_bp)
    app.register_blueprint(public_directory_bp)
    app.register_blueprint(directory_enquiries_bp)

    register_routes(app)

    return app


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


TIER_RANKS = {
    "free": 0,
    "starter": 10,
    "professional": 20,
    "covered": 30,
    "boutique": 40,
    "admin": 100,
}

TIER_LABELS = {
    "free": "Free",
    "starter": "Starter",
    "professional": "Professional",
    "covered": "Covered",
    "boutique": "Boutique",
    "admin": "Admin",
}

FEATURE_TIER_LABELS = {
    "starter": "Starter",
    "professional": "Professional",
    "covered": "Covered",
    "boutique": "Boutique",
}


def get_or_create_subscription(user):
    subscription = Subscription.query.filter_by(user_id=user.id).first()

    if subscription:
        return subscription

    default_tier = "admin" if user.role == "admin" else "boutique"

    subscription = Subscription(
        user_id=user.id,
        tier=default_tier,
        status="active",
        notes="Auto-created by HIVE internal subscription system."
    )

    db.session.add(subscription)
    db.session.commit()

    return subscription


def user_has_tier(user, required_tier):
    if not user.is_authenticated:
        return False

    if user.role == "admin":
        return True

    subscription = get_or_create_subscription(user)

    if subscription.status not in ["active", "trial"]:
        return False

    user_rank = TIER_RANKS.get(subscription.tier, 0)
    required_rank = TIER_RANKS.get(required_tier, 0)

    return user_rank >= required_rank


def subscription_required(required_tier):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("login"))

            if current_user.role == "admin":
                return view_func(*args, **kwargs)

            if user_has_tier(current_user, required_tier):
                return view_func(*args, **kwargs)

            subscription = get_or_create_subscription(current_user)

            return render_template(
                "billing/upgrade_required.html",
                required_tier=required_tier,
                required_tier_label=FEATURE_TIER_LABELS.get(required_tier, required_tier.title()),
                current_tier=subscription.tier,
                current_tier_label=TIER_LABELS.get(subscription.tier, subscription.tier.title()),
                subscription=subscription
            )

        return wrapped_view

    return decorator


def slugify(value):
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9\s-]", "", value)
    value = re.sub(r"[\s-]+", "-", value)
    value = value.strip("-")
    return value or "consultant"


def get_or_create_tenant_settings(user):
    settings = TenantSettings.query.filter_by(user_id=user.id).first()

    if settings:
        return settings

    base_slug = slugify(user.name)
    slug = base_slug
    counter = 2

    while TenantSettings.query.filter_by(tenant_slug=slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1

    settings = TenantSettings(
        user_id=user.id,
        tenant_slug=slug,
        business_name=user.name,
        strapline="Practical HR and people support for growing organisations.",
        primary_colour="#005b5a",
        accent_colour="#f5b041",
        text_colour="#1f2937",
        website_intro="Independent HR consultancy support tailored to your organisation.",
        about_text="Add a short introduction about your consultancy, your experience and how you help clients.",
        services_text="Retained HR support\nEmployee relations advice\nRecruitment support\nPolicy and handbook support\nManager coaching",
        sectors_text="SMEs\nCare sector\nCharities\nProfessional services",
        contact_email=user.email,
        cta_label="Book a discovery call",
        cta_url="https://www.linkedin.com"
    )

    db.session.add(settings)
    db.session.commit()

    return settings


def save_logo_upload(file_storage):
    if not file_storage or not file_storage.filename:
        return None

    filename = secure_filename(file_storage.filename)
    _, extension = os.path.splitext(filename)

    unique_filename = f"{uuid4().hex}{extension.lower()}"
    relative_path = os.path.join("logos", unique_filename)
    full_path = os.path.join(current_app.config["UPLOAD_FOLDER"], relative_path)

    file_storage.save(full_path)

    return relative_path.replace("\\", "/")


def save_resource_upload(file_storage):
    if not file_storage or not file_storage.filename:
        return None, None

    original_filename = secure_filename(file_storage.filename)
    _, extension = os.path.splitext(original_filename)

    unique_filename = f"{uuid4().hex}{extension.lower()}"
    relative_path = os.path.join("resources", unique_filename)
    full_path = os.path.join(current_app.config["UPLOAD_FOLDER"], relative_path)

    file_storage.save(full_path)

    return relative_path.replace("\\", "/"), original_filename


def get_consultant_app_access_map(consultant_id):
    access_records = ConsultantAppAccess.query.filter_by(
        consultant_id=consultant_id
    ).all()

    return {
        access.app_module_id: access
        for access in access_records
    }


def get_or_create_app_access(consultant_id, app_module_id):
    access = ConsultantAppAccess.query.filter_by(
        consultant_id=consultant_id,
        app_module_id=app_module_id
    ).first()

    if access:
        return access

    access = ConsultantAppAccess(
        consultant_id=consultant_id,
        app_module_id=app_module_id,
        status="inactive"
    )

    db.session.add(access)
    db.session.commit()

    return access


def get_consultant_cover_or_404(cover_id):
    return CoverRequest.query.filter_by(
        id=cover_id,
        consultant_id=current_user.id
    ).first_or_404()


def get_consultant_lead_or_404(lead_id):
    return Lead.query.filter_by(
        id=lead_id,
        assigned_consultant_id=current_user.id
    ).first_or_404()


def get_consultant_expert_request_or_404(request_id):
    return ExpertRequest.query.filter_by(
        id=request_id,
        consultant_id=current_user.id
    ).first_or_404()


def update_cover_status(cover_request, status):
    cover_request.status = status

    if status == "submitted":
        cover_request.submitted_at = datetime.utcnow()
    elif status == "approved":
        cover_request.approved_at = datetime.utcnow()
    elif status == "active":
        cover_request.activated_at = datetime.utcnow()
    elif status == "completed":
        cover_request.completed_at = datetime.utcnow()

    db.session.commit()


def register_routes(app):

    @app.route("/")
    def home():
        if current_user.is_authenticated:
            if current_user.role == "admin":
                return redirect(url_for("admin_dashboard"))

            return redirect(url_for("dashboard"))

        return redirect(url_for("login"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            if current_user.role == "admin":
                return redirect(url_for("admin_dashboard"))

            return redirect(url_for("dashboard"))

        form = LoginForm()

        if form.validate_on_submit():
            email = form.email.data.lower().strip()
            user = User.query.filter_by(email=email).first()

            if not user or not user.check_password(form.password.data):
                flash("Invalid email or password.", "danger")
                return render_template("auth/login.html", form=form)

            if not user.is_active:
                flash("This account is inactive.", "danger")
                return render_template("auth/login.html", form=form)

            login_user(user)

            next_page = request.args.get("next")
            if next_page:
                return redirect(next_page)

            if user.role == "admin":
                return redirect(url_for("admin_dashboard"))

            return redirect(url_for("dashboard"))

        return render_template("auth/login.html", form=form)

    @app.route("/logout", methods=["POST"])
    @login_required
    def logout():
        logout_user()
        flash("You have been logged out.", "success")
        return redirect(url_for("login"))

    @app.route("/dashboard")
    @login_required
    @consultant_required
    def dashboard():
        settings = get_or_create_tenant_settings(current_user)
        subscription = get_or_create_subscription(current_user)

        active_apps_count = ConsultantAppAccess.query.filter_by(
            consultant_id=current_user.id,
            status="active"
        ).count()

        requested_apps_count = ConsultantAppAccess.query.filter_by(
            consultant_id=current_user.id,
            status="requested"
        ).count()

        active_resources_count = Resource.query.filter_by(is_active=True).count()

        cover_requests_count = CoverRequest.query.filter_by(
            consultant_id=current_user.id
        ).count()

        submitted_cover_count = CoverRequest.query.filter(
            CoverRequest.consultant_id == current_user.id,
            CoverRequest.status.in_(["submitted", "approved", "active"])
        ).count()

        assigned_leads_count = Lead.query.filter_by(
            assigned_consultant_id=current_user.id
        ).count()

        active_leads_count = Lead.query.filter(
            Lead.assigned_consultant_id == current_user.id,
            Lead.status.in_(["assigned", "accepted"])
        ).count()

        expert_requests_count = ExpertRequest.query.filter_by(
            consultant_id=current_user.id
        ).count()

        open_expert_requests_count = ExpertRequest.query.filter(
            ExpertRequest.consultant_id == current_user.id,
            ExpertRequest.status.in_(["new", "reviewing", "assigned", "responded"])
        ).count()

        return render_template(
            "member/dashboard.html",
            settings=settings,
            active_apps_count=active_apps_count,
            requested_apps_count=requested_apps_count,
            active_resources_count=active_resources_count,
            cover_requests_count=cover_requests_count,
            submitted_cover_count=submitted_cover_count,
            assigned_leads_count=assigned_leads_count,
            active_leads_count=active_leads_count,
            expert_requests_count=expert_requests_count,
            open_expert_requests_count=open_expert_requests_count,
            subscription=subscription,
            tier_label=TIER_LABELS.get(subscription.tier, subscription.tier.title())
        )

    @app.route("/website/settings", methods=["GET", "POST"])
    @login_required
    @consultant_required
    @subscription_required("starter")
    def website_settings():
        settings = get_or_create_tenant_settings(current_user)
        form = TenantSettingsForm(obj=settings)

        if form.validate_on_submit():
            requested_slug = form.tenant_slug.data.lower().strip()

            existing_slug = TenantSettings.query.filter(
                TenantSettings.tenant_slug == requested_slug,
                TenantSettings.user_id != current_user.id
            ).first()

            if existing_slug:
                flash("That website slug is already in use. Please choose another.", "danger")
                return render_template(
                    "member/website_settings.html",
                    form=form,
                    settings=settings
                )

            settings.tenant_slug = requested_slug
            settings.business_name = form.business_name.data.strip()
            settings.strapline = form.strapline.data
            settings.primary_colour = form.primary_colour.data
            settings.accent_colour = form.accent_colour.data
            settings.text_colour = form.text_colour.data
            settings.website_intro = form.website_intro.data
            settings.about_text = form.about_text.data
            settings.services_text = form.services_text.data
            settings.sectors_text = form.sectors_text.data
            settings.contact_email = form.contact_email.data
            settings.contact_phone = form.contact_phone.data
            settings.linkedin_url = form.linkedin_url.data
            settings.cta_label = form.cta_label.data or "Book a discovery call"
            settings.cta_url = form.cta_url.data
            settings.is_published = form.is_published.data

            logo_path = save_logo_upload(form.logo.data)
            if logo_path:
                settings.logo_path = logo_path

            db.session.commit()

            flash("Website settings saved.", "success")
            return redirect(url_for("website_settings"))

        return render_template(
            "member/website_settings.html",
            form=form,
            settings=settings
        )

    @app.route("/website/preview")
    @login_required
    @consultant_required
    @subscription_required("starter")
    def website_preview():
        settings = get_or_create_tenant_settings(current_user)
        return render_template("member/website_preview.html", settings=settings)

    @app.route("/consultants/<tenant_slug>")
    def consultant_site(tenant_slug):
        settings = TenantSettings.query.filter_by(tenant_slug=tenant_slug).first_or_404()

        if not settings.is_published:
            if not current_user.is_authenticated:
                flash("This consultant website is not currently published.", "warning")
                return redirect(url_for("login"))

            if current_user.role != "admin" and current_user.id != settings.user_id:
                flash("This consultant website is not currently published.", "warning")
                return redirect(url_for("dashboard"))

        return render_template("public/consultant_site.html", settings=settings)

    @app.route("/uploads/<path:filename>")
    def uploaded_file(filename):
        return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)

    @app.route("/apps")
    @login_required
    @consultant_required
    @subscription_required("professional")
    def apps_index():
        app_modules = AppModule.query.filter_by(is_active=True).order_by(AppModule.name.asc()).all()
        access_map = get_consultant_app_access_map(current_user.id)

        return render_template(
            "apps/index.html",
            app_modules=app_modules,
            access_map=access_map
        )

    @app.route("/apps/<app_slug>/request-access", methods=["POST"])
    @login_required
    @consultant_required
    @subscription_required("professional")
    def request_app_access(app_slug):
        app_module = AppModule.query.filter_by(slug=app_slug, is_active=True).first_or_404()
        access = get_or_create_app_access(current_user.id, app_module.id)

        if access.status == "active":
            flash(f"You already have access to {app_module.name}.", "success")
            return redirect(url_for("apps_index"))

        access.status = "requested"
        db.session.commit()

        flash(f"Access requested for {app_module.name}.", "success")
        return redirect(url_for("apps_index"))

    @app.route("/apps/<app_slug>/launch")
    @login_required
    @consultant_required
    @subscription_required("professional")
    def launch_app(app_slug):
        app_module = AppModule.query.filter_by(slug=app_slug, is_active=True).first_or_404()
        access = ConsultantAppAccess.query.filter_by(
            consultant_id=current_user.id,
            app_module_id=app_module.id,
            status="active"
        ).first()

        if not access:
            flash(f"You do not currently have access to {app_module.name}.", "danger")
            return redirect(url_for("apps_index"))

        if app_module.launch_url:
            return redirect(app_module.launch_url)

        flash(f"{app_module.name} is active, but no launch URL has been configured yet.", "warning")
        return redirect(url_for("apps_index"))

    @app.route("/resources")
    @login_required
    @consultant_required
    @subscription_required("starter")
    def resources_list():
        category = request.args.get("category", "").strip()

        query = Resource.query.filter_by(is_active=True)

        if category:
            query = query.filter(Resource.category == category)

        resources = query.order_by(Resource.created_at.desc()).all()

        categories = [
            row[0]
            for row in db.session.query(Resource.category)
            .filter(Resource.is_active == True)
            .distinct()
            .order_by(Resource.category.asc())
            .all()
            if row[0]
        ]

        return render_template(
            "resources/list.html",
            resources=resources,
            categories=categories,
            selected_category=category
        )

    @app.route("/resources/<int:resource_id>")
    @login_required
    @consultant_required
    @subscription_required("starter")
    def resource_detail(resource_id):
        resource = Resource.query.filter_by(
            id=resource_id,
            is_active=True
        ).first_or_404()

        return render_template("resources/detail.html", resource=resource)

    @app.route("/resources/<int:resource_id>/download")
    @login_required
    @consultant_required
    @subscription_required("starter")
    def resource_download(resource_id):
        resource = Resource.query.filter_by(
            id=resource_id,
            is_active=True
        ).first_or_404()

        if not resource.file_path:
            flash("No file is attached to this resource.", "warning")
            return redirect(url_for("resource_detail", resource_id=resource.id))

        directory = current_app.config["UPLOAD_FOLDER"]

        return send_from_directory(
            directory,
            resource.file_path,
            as_attachment=True,
            download_name=resource.original_filename or os.path.basename(resource.file_path)
        )

    @app.route("/cover")
    @login_required
    @consultant_required
    @subscription_required("covered")
    def cover_list():
        cover_requests = CoverRequest.query.filter_by(
            consultant_id=current_user.id
        ).order_by(CoverRequest.created_at.desc()).all()

        return render_template(
            "cover/list.html",
            cover_requests=cover_requests
        )

    @app.route("/cover/new", methods=["GET", "POST"])
    @login_required
    @consultant_required
    @subscription_required("covered")
    def cover_new():
        form = CoverRequestForm()

        if form.validate_on_submit():
            if form.end_date.data < form.start_date.data:
                flash("End date cannot be before start date.", "danger")
                return render_template("cover/new.html", form=form, cover_request=None)

            cover_request = CoverRequest(
                consultant_id=current_user.id,
                cover_type=form.cover_type.data,
                start_date=form.start_date.data,
                end_date=form.end_date.data,
                summary=form.summary.data,
                status="draft"
            )

            db.session.add(cover_request)
            db.session.commit()

            flash("Cover request created. Add at least one covered client before submitting.", "success")
            return redirect(url_for("cover_detail", cover_id=cover_request.id))

        return render_template("cover/new.html", form=form, cover_request=None)

    @app.route("/cover/<int:cover_id>")
    @login_required
    @consultant_required
    @subscription_required("covered")
    def cover_detail(cover_id):
        cover_request = get_consultant_cover_or_404(cover_id)

        return render_template(
            "cover/detail.html",
            cover_request=cover_request
        )

    @app.route("/cover/<int:cover_id>/clients/new", methods=["GET", "POST"])
    @login_required
    @consultant_required
    @subscription_required("covered")
    def cover_add_client(cover_id):
        cover_request = get_consultant_cover_or_404(cover_id)

        if cover_request.status not in ["draft"]:
            flash("You can only add clients while the cover request is in draft.", "warning")
            return redirect(url_for("cover_detail", cover_id=cover_request.id))

        form = CoverClientForm()

        if form.validate_on_submit():
            client = CoverClient(
                cover_request_id=cover_request.id,
                client_name=form.client_name.data.strip(),
                contact_name=form.contact_name.data,
                contact_email=form.contact_email.data,
                contact_phone=form.contact_phone.data,
                retainer_scope=form.retainer_scope.data,
                authority_limits=form.authority_limits.data,
                escalation_rules=form.escalation_rules.data,
                open_issues=form.open_issues.data,
                risk_notes=form.risk_notes.data
            )

            db.session.add(client)
            db.session.commit()

            flash("Covered client added.", "success")
            return redirect(url_for("cover_detail", cover_id=cover_request.id))

        return render_template(
            "cover/client_form.html",
            form=form,
            cover_request=cover_request
        )

    @app.route("/cover/<int:cover_id>/submit", methods=["POST"])
    @login_required
    @consultant_required
    @subscription_required("covered")
    def cover_submit(cover_id):
        cover_request = get_consultant_cover_or_404(cover_id)

        if cover_request.status != "draft":
            flash("Only draft cover requests can be submitted.", "warning")
            return redirect(url_for("cover_detail", cover_id=cover_request.id))

        if not cover_request.clients:
            flash("Add at least one covered client before submitting.", "danger")
            return redirect(url_for("cover_detail", cover_id=cover_request.id))

        update_cover_status(cover_request, "submitted")

        flash("Cover request submitted to HIVE admin.", "success")
        return redirect(url_for("cover_detail", cover_id=cover_request.id))

    @app.route("/people-signal/lead/new", methods=["GET", "POST"])
    @login_required
    @admin_required
    def people_signal_lead_new():
        form = PeopleSignalLeadForm()

        if form.validate_on_submit():
            lead = Lead(
                source="people_signal",
                source_reference=form.source_reference.data,
                company_name=form.company_name.data.strip(),
                contact_name=form.contact_name.data,
                contact_email=form.contact_email.data,
                contact_phone=form.contact_phone.data,
                sector=form.sector.data,
                employee_count=form.employee_count.data,
                location=form.location.data,
                signal_type=form.signal_type.data,
                signal_summary=form.signal_summary.data,
                support_needed=form.support_needed.data,
                urgency=form.urgency.data,
                people_signal_score=form.people_signal_score.data,
                risk_level=form.risk_level.data,
                status="new"
            )

            db.session.add(lead)
            db.session.commit()

            flash("PeopleSignal lead created.", "success")
            return redirect(url_for("admin_lead_detail", lead_id=lead.id))

        return render_template("people_signal/lead_form.html", form=form)

    @app.route("/leads")
    @login_required
    @consultant_required
    @subscription_required("professional")
    def leads_list():
        leads = Lead.query.filter_by(
            assigned_consultant_id=current_user.id
        ).order_by(Lead.created_at.desc()).all()

        return render_template("leads/list.html", leads=leads)

    @app.route("/leads/<int:lead_id>", methods=["GET", "POST"])
    @login_required
    @consultant_required
    @subscription_required("professional")
    def lead_detail(lead_id):
        lead = get_consultant_lead_or_404(lead_id)
        form = ConsultantLeadNotesForm(obj=lead)

        if form.validate_on_submit():
            lead.consultant_notes = form.consultant_notes.data
            db.session.commit()

            flash("Lead notes saved.", "success")
            return redirect(url_for("lead_detail", lead_id=lead.id))

        return render_template("leads/detail.html", lead=lead, form=form)

    @app.route("/leads/<int:lead_id>/status/<status>", methods=["POST"])
    @login_required
    @consultant_required
    @subscription_required("professional")
    def lead_update_status(lead_id, status):
        allowed_statuses = ["accepted", "declined", "won", "lost", "closed"]

        if status not in allowed_statuses:
            flash("Invalid lead status.", "danger")
            return redirect(url_for("lead_detail", lead_id=lead_id))

        lead = get_consultant_lead_or_404(lead_id)
        lead.status = status
        db.session.commit()

        flash(f"Lead status updated to {status}.", "success")
        return redirect(url_for("lead_detail", lead_id=lead.id))

    @app.route("/expert-help")
    @login_required
    @consultant_required
    @subscription_required("boutique")
    def expert_help_list():
        expert_requests = ExpertRequest.query.filter_by(
            consultant_id=current_user.id
        ).order_by(ExpertRequest.created_at.desc()).all()

        return render_template(
            "expert/list.html",
            expert_requests=expert_requests
        )

    @app.route("/expert-help/new", methods=["GET", "POST"])
    @login_required
    @consultant_required
    @subscription_required("boutique")
    def expert_help_new():
        form = ExpertRequestForm()

        if form.validate_on_submit():
            expert_request = ExpertRequest(
                consultant_id=current_user.id,
                category=form.category.data,
                urgency=form.urgency.data,
                subject=form.subject.data.strip(),
                summary=form.summary.data,
                desired_outcome=form.desired_outcome.data,
                status="new"
            )

            db.session.add(expert_request)
            db.session.commit()

            flash("Expert help request submitted.", "success")
            return redirect(url_for("expert_help_detail", request_id=expert_request.id))

        return render_template(
            "expert/form.html",
            form=form
        )

    @app.route("/expert-help/<int:request_id>")
    @login_required
    @consultant_required
    @subscription_required("boutique")
    def expert_help_detail(request_id):
        expert_request = get_consultant_expert_request_or_404(request_id)

        return render_template(
            "expert/detail.html",
            expert_request=expert_request
        )

    @app.route("/admin")
    @login_required
    @admin_required
    def admin_dashboard():
        total_users = User.query.count()
        total_consultants = User.query.filter_by(role="consultant").count()
        total_tenant_sites = TenantSettings.query.count()
        published_tenant_sites = TenantSettings.query.filter_by(is_published=True).count()
        total_app_modules = AppModule.query.count()
        requested_app_access = ConsultantAppAccess.query.filter_by(status="requested").count()
        total_resources = Resource.query.count()
        active_resources = Resource.query.filter_by(is_active=True).count()
        total_cover_requests = CoverRequest.query.count()
        submitted_cover_requests = CoverRequest.query.filter(
            CoverRequest.status.in_(["submitted", "approved", "active"])
        ).count()
        total_leads = Lead.query.count()
        new_leads = Lead.query.filter_by(status="new").count()
        assigned_leads = Lead.query.filter_by(status="assigned").count()
        won_leads = Lead.query.filter_by(status="won").count()
        total_expert_requests = ExpertRequest.query.count()
        open_expert_requests = ExpertRequest.query.filter(
            ExpertRequest.status.in_(["new", "reviewing", "assigned", "responded"])
        ).count()
        total_subscriptions = Subscription.query.count()
        active_subscriptions = Subscription.query.filter(
            Subscription.status.in_(["active", "trial"])
        ).count()

        return render_template(
            "admin/dashboard.html",
            total_users=total_users,
            total_consultants=total_consultants,
            total_tenant_sites=total_tenant_sites,
            published_tenant_sites=published_tenant_sites,
            total_app_modules=total_app_modules,
            requested_app_access=requested_app_access,
            total_resources=total_resources,
            active_resources=active_resources,
            total_cover_requests=total_cover_requests,
            submitted_cover_requests=submitted_cover_requests,
            total_leads=total_leads,
            new_leads=new_leads,
            assigned_leads=assigned_leads,
            won_leads=won_leads,
            total_expert_requests=total_expert_requests,
            open_expert_requests=open_expert_requests,
            total_subscriptions=total_subscriptions,
            active_subscriptions=active_subscriptions
        )

    @app.route("/admin/apps")
    @login_required
    @admin_required
    def admin_apps():
        app_modules = AppModule.query.order_by(AppModule.name.asc()).all()
        requested_access = ConsultantAppAccess.query.filter_by(status="requested").all()

        return render_template(
            "admin/apps.html",
            app_modules=app_modules,
            requested_access=requested_access
        )

    @app.route("/admin/consultants/<int:consultant_id>/apps")
    @login_required
    @admin_required
    def admin_consultant_apps(consultant_id):
        consultant = User.query.filter_by(id=consultant_id, role="consultant").first_or_404()
        app_modules = AppModule.query.order_by(AppModule.name.asc()).all()
        access_map = get_consultant_app_access_map(consultant.id)

        return render_template(
            "admin/consultant_apps.html",
            consultant=consultant,
            app_modules=app_modules,
            access_map=access_map
        )

    @app.route("/admin/consultants/<int:consultant_id>/apps/<int:app_id>/enable", methods=["POST"])
    @login_required
    @admin_required
    def admin_enable_app_access(consultant_id, app_id):
        consultant = User.query.filter_by(id=consultant_id, role="consultant").first_or_404()
        app_module = AppModule.query.get_or_404(app_id)
        access = get_or_create_app_access(consultant.id, app_module.id)

        access.status = "active"
        access.activated_at = datetime.utcnow()
        db.session.commit()

        flash(f"{app_module.name} enabled for {consultant.name}.", "success")
        return redirect(url_for("admin_consultant_apps", consultant_id=consultant.id))

    @app.route("/admin/consultants/<int:consultant_id>/apps/<int:app_id>/disable", methods=["POST"])
    @login_required
    @admin_required
    def admin_disable_app_access(consultant_id, app_id):
        consultant = User.query.filter_by(id=consultant_id, role="consultant").first_or_404()
        app_module = AppModule.query.get_or_404(app_id)
        access = get_or_create_app_access(consultant.id, app_module.id)

        access.status = "inactive"
        db.session.commit()

        flash(f"{app_module.name} disabled for {consultant.name}.", "success")
        return redirect(url_for("admin_consultant_apps", consultant_id=consultant.id))

    @app.route("/admin/resources")
    @login_required
    @admin_required
    def admin_resources():
        resources = Resource.query.order_by(Resource.created_at.desc()).all()

        return render_template(
            "admin/resources.html",
            resources=resources
        )

    @app.route("/admin/resources/new", methods=["GET", "POST"])
    @login_required
    @admin_required
    def admin_new_resource():
        form = ResourceForm()
        form.is_active.data = True if request.method == "GET" else form.is_active.data

        if form.validate_on_submit():
            file_path, original_filename = save_resource_upload(form.resource_file.data)

            resource = Resource(
                title=form.title.data.strip(),
                category=form.category.data,
                description=form.description.data,
                file_path=file_path,
                original_filename=original_filename,
                required_tier=form.required_tier.data,
                consultant_notes=form.consultant_notes.data,
                risk_flags=form.risk_flags.data,
                escalation_points=form.escalation_points.data,
                is_active=form.is_active.data,
                created_by_id=current_user.id
            )

            db.session.add(resource)
            db.session.commit()

            flash("Resource created.", "success")
            return redirect(url_for("admin_resources"))

        return render_template(
            "admin/resource_form.html",
            form=form,
            resource=None,
            page_title="New Resource"
        )

    @app.route("/admin/resources/<int:resource_id>/edit", methods=["GET", "POST"])
    @login_required
    @admin_required
    def admin_edit_resource(resource_id):
        resource = Resource.query.get_or_404(resource_id)
        form = ResourceForm(obj=resource)

        if form.validate_on_submit():
            resource.title = form.title.data.strip()
            resource.category = form.category.data
            resource.description = form.description.data
            resource.required_tier = form.required_tier.data
            resource.consultant_notes = form.consultant_notes.data
            resource.risk_flags = form.risk_flags.data
            resource.escalation_points = form.escalation_points.data
            resource.is_active = form.is_active.data

            file_path, original_filename = save_resource_upload(form.resource_file.data)
            if file_path:
                resource.file_path = file_path
                resource.original_filename = original_filename

            db.session.commit()

            flash("Resource updated.", "success")
            return redirect(url_for("admin_resources"))

        return render_template(
            "admin/resource_form.html",
            form=form,
            resource=resource,
            page_title="Edit Resource"
        )

    @app.route("/admin/resources/<int:resource_id>/delete", methods=["POST"])
    @login_required
    @admin_required
    def admin_delete_resource(resource_id):
        resource = Resource.query.get_or_404(resource_id)

        db.session.delete(resource)
        db.session.commit()

        flash("Resource deleted.", "success")
        return redirect(url_for("admin_resources"))

    @app.route("/admin/cover")
    @login_required
    @admin_required
    def admin_cover():
        status = request.args.get("status", "").strip()

        query = CoverRequest.query

        if status:
            query = query.filter(CoverRequest.status == status)

        cover_requests = query.order_by(CoverRequest.created_at.desc()).all()

        return render_template(
            "admin/cover.html",
            cover_requests=cover_requests,
            selected_status=status
        )

    @app.route("/admin/cover/<int:cover_id>", methods=["GET", "POST"])
    @login_required
    @admin_required
    def admin_cover_detail(cover_id):
        cover_request = CoverRequest.query.get_or_404(cover_id)
        form = AdminCoverStatusForm(obj=cover_request)

        if form.validate_on_submit():
            cover_request.admin_notes = form.admin_notes.data
            db.session.commit()

            flash("Admin notes saved.", "success")
            return redirect(url_for("admin_cover_detail", cover_id=cover_request.id))

        return render_template(
            "admin/cover_detail.html",
            cover_request=cover_request,
            form=form
        )

    @app.route("/admin/cover/<int:cover_id>/status/<status>", methods=["POST"])
    @login_required
    @admin_required
    def admin_cover_update_status(cover_id, status):
        allowed_statuses = [
            "draft",
            "submitted",
            "approved",
            "active",
            "completed",
            "declined",
            "cancelled"
        ]

        if status not in allowed_statuses:
            flash("Invalid cover status.", "danger")
            return redirect(url_for("admin_cover_detail", cover_id=cover_id))

        cover_request = CoverRequest.query.get_or_404(cover_id)
        update_cover_status(cover_request, status)

        flash(f"Cover request status updated to {status}.", "success")
        return redirect(url_for("admin_cover_detail", cover_id=cover_request.id))

    @app.route("/admin/leads")
    @login_required
    @admin_required
    def admin_leads():
        status = request.args.get("status", "").strip()

        query = Lead.query

        if status:
            query = query.filter(Lead.status == status)

        leads = query.order_by(Lead.created_at.desc()).all()

        return render_template(
            "admin/leads.html",
            leads=leads,
            selected_status=status
        )

    @app.route("/admin/leads/<int:lead_id>", methods=["GET", "POST"])
    @login_required
    @admin_required
    def admin_lead_detail(lead_id):
        lead = Lead.query.get_or_404(lead_id)
        form = AdminLeadForm(obj=lead)

        consultants = User.query.filter_by(role="consultant", is_active=True).order_by(User.name.asc()).all()
        form.assigned_consultant_id.choices = [(0, "Unassigned")] + [
            (consultant.id, consultant.name)
            for consultant in consultants
        ]

        if request.method == "GET":
            form.assigned_consultant_id.data = lead.assigned_consultant_id or 0

        if form.validate_on_submit():
            assigned_id = form.assigned_consultant_id.data

            lead.assigned_consultant_id = assigned_id if assigned_id else None
            lead.status = form.status.data
            lead.admin_notes = form.admin_notes.data

            if lead.assigned_consultant_id and lead.status in ["new", "qualified"]:
                lead.status = "assigned"

            db.session.commit()

            flash("Lead updated.", "success")
            return redirect(url_for("admin_lead_detail", lead_id=lead.id))

        return render_template(
            "admin/lead_detail.html",
            lead=lead,
            form=form
        )

    @app.route("/admin/expert-requests")
    @login_required
    @admin_required
    def admin_expert_requests():
        status = request.args.get("status", "").strip()

        query = ExpertRequest.query

        if status:
            query = query.filter(ExpertRequest.status == status)

        expert_requests = query.order_by(ExpertRequest.created_at.desc()).all()

        return render_template(
            "admin/expert_requests.html",
            expert_requests=expert_requests,
            selected_status=status
        )

    @app.route("/admin/expert-requests/<int:request_id>", methods=["GET", "POST"])
    @login_required
    @admin_required
    def admin_expert_request_detail(request_id):
        expert_request = ExpertRequest.query.get_or_404(request_id)
        form = AdminExpertRequestForm(obj=expert_request)

        if form.validate_on_submit():
            previous_status = expert_request.status

            expert_request.status = form.status.data
            expert_request.admin_notes = form.admin_notes.data
            expert_request.response_summary = form.response_summary.data

            if form.status.data == "closed" and previous_status != "closed":
                expert_request.closed_at = datetime.utcnow()

            db.session.commit()

            flash("Expert request updated.", "success")
            return redirect(url_for("admin_expert_request_detail", request_id=expert_request.id))

        return render_template(
            "admin/expert_request_detail.html",
            expert_request=expert_request,
            form=form
        )

    @app.route("/admin/subscriptions")
    @login_required
    @admin_required
    def admin_subscriptions():
        consultants = User.query.filter_by(role="consultant").order_by(User.name.asc()).all()

        subscription_rows = []

        for consultant in consultants:
            subscription = get_or_create_subscription(consultant)
            subscription_rows.append({
                "consultant": consultant,
                "subscription": subscription
            })

        return render_template(
            "admin/subscriptions.html",
            subscription_rows=subscription_rows,
            tier_labels=TIER_LABELS
        )

    @app.route("/admin/consultants/<int:consultant_id>/subscription", methods=["GET", "POST"])
    @login_required
    @admin_required
    def admin_consultant_subscription(consultant_id):
        consultant = User.query.filter_by(id=consultant_id, role="consultant").first_or_404()
        subscription = get_or_create_subscription(consultant)
        form = SubscriptionForm(obj=subscription)

        if form.validate_on_submit():
            subscription.tier = form.tier.data
            subscription.status = form.status.data
            subscription.notes = form.notes.data

            db.session.commit()

            flash(f"Subscription updated for {consultant.name}.", "success")
            return redirect(url_for("admin_subscriptions"))

        return render_template(
            "admin/consultant_subscription.html",
            consultant=consultant,
            subscription=subscription,
            form=form,
            tier_labels=TIER_LABELS
        )

    @app.cli.command("seed-users")
    def seed_users():
        existing_admin = User.query.filter_by(email="admin@example.com").first()
        existing_consultant = User.query.filter_by(email="consultant@example.com").first()

        if not existing_admin:
            admin = User(
                email="admin@example.com",
                name="HIVE Admin",
                role="admin"
            )
            admin.set_password("password123")
            db.session.add(admin)

        if not existing_consultant:
            consultant = User(
                email="consultant@example.com",
                name="Demo Consultant",
                role="consultant"
            )
            consultant.set_password("password123")
            db.session.add(consultant)

        db.session.commit()

        print("Seed users created:")
        print("Admin: admin@example.com / password123")
        print("Consultant: consultant@example.com / password123")

    @app.cli.command("seed-apps")
    def seed_apps():
        default_apps = [
            {
                "name": "PayScope",
                "slug": "payscope",
                "description": "Pay benchmarking, salary intelligence, pay maps and recruitment market insight.",
                "required_tier": "professional",
                "icon": "ChartBar",
                "launch_url": ""
            },
            {
                "name": "RecruitFlow AI",
                "slug": "recruitflow-ai",
                "description": "Applicant tracking, candidate management and AI-assisted recruitment workflows.",
                "required_tier": "professional",
                "icon": "Briefcase",
                "launch_url": ""
            },
            {
                "name": "ResolvHR",
                "slug": "resolvhr",
                "description": "Employee relations case management for disciplinary, grievance, absence and performance cases.",
                "required_tier": "professional",
                "icon": "ShieldCheck",
                "launch_url": ""
            },
            {
                "name": "People Signal",
                "slug": "people-signal",
                "description": "Pulse surveys, employee feedback, engagement checks and people insight reporting.",
                "required_tier": "professional",
                "icon": "Signal",
                "launch_url": ""
            },
            {
                "name": "LMS / E-Learning",
                "slug": "lms",
                "description": "Basic course hosting, learning modules, training records and consultant-led client training.",
                "required_tier": "professional",
                "icon": "GraduationCap",
                "launch_url": ""
            }
        ]

        for app_data in default_apps:
            existing_app = AppModule.query.filter_by(slug=app_data["slug"]).first()

            if existing_app:
                existing_app.name = app_data["name"]
                existing_app.description = app_data["description"]
                existing_app.required_tier = app_data["required_tier"]
                existing_app.icon = app_data["icon"]
                existing_app.launch_url = app_data["launch_url"]
                existing_app.is_active = True
            else:
                app_module = AppModule(**app_data)
                db.session.add(app_module)

        db.session.commit()

        print("Default HIVE app modules seeded:")
        print("- PayScope")
        print("- RecruitFlow AI")
        print("- ResolvHR")
        print("- People Signal")
        print("- LMS / E-Learning")


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
