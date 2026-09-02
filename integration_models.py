from datetime import datetime
from uuid import uuid4

from extensions import db


class HiveTenant(db.Model):
    __tablename__ = "hive_tenant"

    id = db.Column(db.Integer, primary_key=True)
    tenant_settings_id = db.Column(
        db.Integer,
        db.ForeignKey("tenant_settings.id"),
        nullable=True,
        unique=True,
        index=True,
    )
    hive_tenant_id = db.Column(
        db.String(64),
        nullable=False,
        unique=True,
        index=True,
        default=lambda: f"hv_tenant_{uuid4().hex}",
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    tenant_settings = db.relationship(
        "TenantSettings",
        backref=db.backref("hive_tenant", uselist=False),
    )


class HiveIdentity(db.Model):
    __tablename__ = "hive_identity"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("hive_tenant.id"),
        nullable=False,
        index=True,
    )
    hive_user_id = db.Column(
        db.String(64),
        nullable=False,
        unique=True,
        index=True,
        default=lambda: f"hv_user_{uuid4().hex}",
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    user = db.relationship("User", backref=db.backref("hive_identity", uselist=False))
    tenant = db.relationship(
        "HiveTenant",
        backref=db.backref("identities", lazy="dynamic"),
    )

    @property
    def hive_tenant_id(self):
        return self.tenant.hive_tenant_id if self.tenant else None


class AppIntegration(db.Model):
    __tablename__ = "app_integration"

    id = db.Column(db.Integer, primary_key=True)
    app_module_id = db.Column(
        db.Integer,
        db.ForeignKey("app_module.id"),
        nullable=False,
        unique=True,
        index=True,
    )

    service_key = db.Column(db.String(100), nullable=False, unique=True, index=True)
    base_url = db.Column(db.String(500), nullable=False)
    sso_path = db.Column(db.String(255), default="/auth/hive-sso", nullable=False)
    sso_audience = db.Column(db.String(150))
    event_token_env = db.Column(db.String(150))
    summary_path = db.Column(db.String(255), default="/api/v1/summary")
    health_path = db.Column(db.String(255), default="/api/v1/health")

    is_enabled = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    app_module = db.relationship(
        "AppModule",
        backref=db.backref(
            "integration",
            uselist=False,
            cascade="all, delete-orphan",
        ),
    )


class IntegrationEvent(db.Model):
    __tablename__ = "integration_event"

    id = db.Column(db.Integer, primary_key=True)
    app_integration_id = db.Column(
        db.Integer,
        db.ForeignKey("app_integration.id"),
        nullable=False,
        index=True,
    )
    consultant_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
        index=True,
    )

    hive_tenant_id = db.Column(db.String(64), index=True)
    external_event_id = db.Column(db.String(255), nullable=False)
    event_type = db.Column(db.String(150), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    priority = db.Column(db.String(30), default="normal", nullable=False, index=True)
    target_url = db.Column(db.String(1000))
    status = db.Column(db.String(30), default="open", nullable=False, index=True)

    occurred_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    resolved_at = db.Column(db.DateTime)

    app_integration = db.relationship(
        "AppIntegration",
        backref=db.backref("events", lazy="dynamic", cascade="all, delete-orphan"),
    )
    consultant = db.relationship(
        "User",
        backref=db.backref("integration_events", lazy="dynamic"),
    )

    __table_args__ = (
        db.UniqueConstraint(
            "app_integration_id",
            "external_event_id",
            name="uq_integration_event_external_id",
        ),
    )
