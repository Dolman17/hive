from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from extensions import db, login_manager


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)

    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(255), nullable=False)

    role = db.Column(db.String(50), default="consultant", nullable=False)
    is_active = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    consultant_profile = db.relationship(
        "ConsultantProfile",
        backref="user",
        uselist=False,
        cascade="all, delete-orphan"
    )

    tenant_settings = db.relationship(
        "TenantSettings",
        backref="user",
        uselist=False,
        cascade="all, delete-orphan"
    )

    app_access = db.relationship(
        "ConsultantAppAccess",
        backref="consultant",
        cascade="all, delete-orphan",
        foreign_keys="ConsultantAppAccess.consultant_id"
    )

    resources_created = db.relationship(
        "Resource",
        backref="created_by",
        foreign_keys="Resource.created_by_id"
    )

    cover_requests = db.relationship(
        "CoverRequest",
        backref="consultant",
        cascade="all, delete-orphan",
        foreign_keys="CoverRequest.consultant_id"
    )

    assigned_cover_requests = db.relationship(
        "CoverRequest",
        backref="assigned_advisor",
        foreign_keys="CoverRequest.assigned_advisor_id"
    )

    assigned_leads = db.relationship(
        "Lead",
        backref="assigned_consultant",
        foreign_keys="Lead.assigned_consultant_id"
    )

    expert_requests = db.relationship(
        "ExpertRequest",
        backref="consultant",
        cascade="all, delete-orphan",
        foreign_keys="ExpertRequest.consultant_id"
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == "admin"

    @property
    def is_consultant(self):
        return self.role == "consultant"


class ConsultantProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
        unique=True
    )

    business_name = db.Column(db.String(255))
    bio = db.Column(db.Text)
    specialisms = db.Column(db.Text)
    sectors = db.Column(db.Text)
    location = db.Column(db.String(255))
    remote_available = db.Column(db.Boolean, default=True)

    insurance_verified = db.Column(db.Boolean, default=False)
    qualifications_verified = db.Column(db.Boolean, default=False)
    is_public = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class TenantSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
        unique=True
    )

    tenant_slug = db.Column(db.String(120), unique=True, nullable=False)
    business_name = db.Column(db.String(255), nullable=False)

    strapline = db.Column(db.String(255))
    logo_path = db.Column(db.String(500))

    primary_colour = db.Column(db.String(20), default="#005b5a")
    accent_colour = db.Column(db.String(20), default="#f5b041")
    text_colour = db.Column(db.String(20), default="#1f2937")

    website_intro = db.Column(db.Text)
    about_text = db.Column(db.Text)
    services_text = db.Column(db.Text)
    sectors_text = db.Column(db.Text)

    contact_email = db.Column(db.String(255))
    contact_phone = db.Column(db.String(100))
    linkedin_url = db.Column(db.String(500))

    cta_label = db.Column(db.String(100), default="Book a discovery call")
    cta_url = db.Column(db.String(500))

    is_published = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )


class AppModule(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)

    description = db.Column(db.Text)
    required_tier = db.Column(db.String(50), default="professional")

    icon = db.Column(db.String(100))
    launch_url = db.Column(db.String(500))

    is_active = db.Column(db.Boolean, default=True)
    is_core = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    access_records = db.relationship(
        "ConsultantAppAccess",
        backref="app_module",
        cascade="all, delete-orphan"
    )


class ConsultantAppAccess(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    consultant_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False
    )

    app_module_id = db.Column(
        db.Integer,
        db.ForeignKey("app_module.id"),
        nullable=False
    )

    status = db.Column(db.String(50), default="inactive")
    access_level = db.Column(db.String(50), default="standard")

    activated_at = db.Column(db.DateTime)
    expires_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint(
            "consultant_id",
            "app_module_id",
            name="uq_consultant_app_access"
        ),
    )


class Resource(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    title = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(100))
    description = db.Column(db.Text)

    file_path = db.Column(db.String(500))
    original_filename = db.Column(db.String(255))

    required_tier = db.Column(db.String(50), default="starter")

    consultant_notes = db.Column(db.Text)
    risk_flags = db.Column(db.Text)
    escalation_points = db.Column(db.Text)

    is_active = db.Column(db.Boolean, default=True)

    created_by_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True
    )

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )


class CoverRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    consultant_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False
    )

    assigned_advisor_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True
    )

    cover_type = db.Column(db.String(50), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)

    summary = db.Column(db.Text)
    status = db.Column(db.String(50), default="draft", nullable=False)

    admin_notes = db.Column(db.Text)

    submitted_at = db.Column(db.DateTime)
    approved_at = db.Column(db.DateTime)
    activated_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    clients = db.relationship(
        "CoverClient",
        backref="cover_request",
        cascade="all, delete-orphan"
    )


class CoverClient(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    cover_request_id = db.Column(
        db.Integer,
        db.ForeignKey("cover_request.id"),
        nullable=False
    )

    client_name = db.Column(db.String(255), nullable=False)
    contact_name = db.Column(db.String(255))
    contact_email = db.Column(db.String(255))
    contact_phone = db.Column(db.String(100))

    retainer_scope = db.Column(db.Text)
    authority_limits = db.Column(db.Text)
    escalation_rules = db.Column(db.Text)
    open_issues = db.Column(db.Text)
    risk_notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Lead(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    source = db.Column(db.String(100), default="people_signal", nullable=False)
    source_reference = db.Column(db.String(255))

    company_name = db.Column(db.String(255), nullable=False)
    contact_name = db.Column(db.String(255))
    contact_email = db.Column(db.String(255))
    contact_phone = db.Column(db.String(100))

    sector = db.Column(db.String(100))
    employee_count = db.Column(db.String(50))
    location = db.Column(db.String(255))

    signal_type = db.Column(db.String(100))
    signal_summary = db.Column(db.Text)
    support_needed = db.Column(db.Text)
    urgency = db.Column(db.String(50))

    people_signal_score = db.Column(db.Integer)
    risk_level = db.Column(db.String(50))

    assigned_consultant_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True
    )

    status = db.Column(db.String(50), default="new", nullable=False)

    admin_notes = db.Column(db.Text)
    consultant_notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

class ExpertRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    consultant_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False
    )

    category = db.Column(db.String(100), nullable=False)
    urgency = db.Column(db.String(50), default="routine", nullable=False)

    subject = db.Column(db.String(255), nullable=False)
    summary = db.Column(db.Text)
    desired_outcome = db.Column(db.Text)

    status = db.Column(db.String(50), default="new", nullable=False)

    admin_notes = db.Column(db.Text)
    response_summary = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    closed_at = db.Column(db.DateTime)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))