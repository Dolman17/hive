from datetime import datetime
from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import ConsultantProfile, User


directory_enquiries_bp = Blueprint("directory_enquiries", __name__)


class DirectoryEnquiry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    consultant_profile_id = db.Column(db.Integer, db.ForeignKey("consultant_profile.id"), nullable=False)
    assigned_consultant_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    company_name = db.Column(db.String(255), nullable=False)
    contact_name = db.Column(db.String(255), nullable=False)
    contact_email = db.Column(db.String(255), nullable=False)
    contact_phone = db.Column(db.String(100))
    support_needed = db.Column(db.Text)
    urgency = db.Column(db.String(50), default="medium", nullable=False)
    status = db.Column(db.String(50), default="new", nullable=False)
    admin_notes = db.Column(db.Text)
    consultant_notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    consultant_profile = db.relationship("ConsultantProfile", backref="directory_enquiries")
    assigned_consultant = db.relationship("User", foreign_keys=[assigned_consultant_id])


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


def get_public_profile_or_404(profile_id):
    return (
        ConsultantProfile.query
        .join(User, ConsultantProfile.user_id == User.id)
        .filter(ConsultantProfile.id == profile_id)
        .filter(ConsultantProfile.is_public == True)
        .filter(User.role == "consultant")
        .filter(User.is_active == True)
        .first_or_404()
    )


@directory_enquiries_bp.route("/directory/<int:profile_id>/enquire", methods=["GET", "POST"])
def public_directory_enquiry(profile_id):
    profile = get_public_profile_or_404(profile_id)

    if request.method == "POST":
        enquiry = DirectoryEnquiry(
            consultant_profile_id=profile.id,
            assigned_consultant_id=profile.user_id,
            company_name=request.form.get("company_name", "").strip(),
            contact_name=request.form.get("contact_name", "").strip(),
            contact_email=request.form.get("contact_email", "").strip(),
            contact_phone=request.form.get("contact_phone", "").strip() or None,
            support_needed=request.form.get("support_needed", "").strip() or None,
            urgency=request.form.get("urgency", "medium"),
            status="new",
        )

        if not enquiry.company_name or not enquiry.contact_name or not enquiry.contact_email:
            flash("Please complete company name, contact name and contact email.", "danger")
            return render_template("directory_enquiries/public_form.html", profile=profile)

        db.session.add(enquiry)
        db.session.commit()
        return redirect(url_for("directory_enquiries.public_directory_enquiry_thanks", enquiry_id=enquiry.id))

    return render_template("directory_enquiries/public_form.html", profile=profile)


@directory_enquiries_bp.route("/directory/enquiry/<int:enquiry_id>/thanks")
def public_directory_enquiry_thanks(enquiry_id):
    enquiry = DirectoryEnquiry.query.get_or_404(enquiry_id)
    return render_template("directory_enquiries/thanks.html", enquiry=enquiry)


@directory_enquiries_bp.route("/admin/directory-enquiries")
@login_required
@admin_required
def admin_directory_enquiries():
    status = request.args.get("status", "").strip()
    query = DirectoryEnquiry.query
    if status:
        query = query.filter(DirectoryEnquiry.status == status)
    enquiries = query.order_by(DirectoryEnquiry.created_at.desc()).all()
    consultants = User.query.filter_by(role="consultant", is_active=True).order_by(User.name.asc()).all()
    return render_template("directory_enquiries/admin_list.html", enquiries=enquiries, consultants=consultants, selected_status=status)


@directory_enquiries_bp.route("/admin/directory-enquiries/<int:enquiry_id>", methods=["GET", "POST"])
@login_required
@admin_required
def admin_directory_enquiry_detail(enquiry_id):
    enquiry = DirectoryEnquiry.query.get_or_404(enquiry_id)
    consultants = User.query.filter_by(role="consultant", is_active=True).order_by(User.name.asc()).all()

    if request.method == "POST":
        assigned_id = request.form.get("assigned_consultant_id", "").strip()
        enquiry.assigned_consultant_id = int(assigned_id) if assigned_id else None
        enquiry.status = request.form.get("status", "new")
        enquiry.admin_notes = request.form.get("admin_notes", "").strip() or None
        db.session.commit()
        flash("Directory enquiry updated.", "success")
        return redirect(url_for("directory_enquiries.admin_directory_enquiry_detail", enquiry_id=enquiry.id))

    return render_template("directory_enquiries/admin_detail.html", enquiry=enquiry, consultants=consultants)


@directory_enquiries_bp.route("/directory-enquiries")
@login_required
@consultant_required
def consultant_directory_enquiries():
    enquiries = DirectoryEnquiry.query.filter_by(assigned_consultant_id=current_user.id).order_by(DirectoryEnquiry.created_at.desc()).all()
    return render_template("directory_enquiries/consultant_list.html", enquiries=enquiries)


@directory_enquiries_bp.route("/directory-enquiries/<int:enquiry_id>", methods=["GET", "POST"])
@login_required
@consultant_required
def consultant_directory_enquiry_detail(enquiry_id):
    enquiry = DirectoryEnquiry.query.filter_by(id=enquiry_id, assigned_consultant_id=current_user.id).first_or_404()

    if request.method == "POST":
        enquiry.status = request.form.get("status", enquiry.status)
        enquiry.consultant_notes = request.form.get("consultant_notes", "").strip() or None
        db.session.commit()
        flash("Enquiry updated.", "success")
        return redirect(url_for("directory_enquiries.consultant_directory_enquiry_detail", enquiry_id=enquiry.id))

    return render_template("directory_enquiries/consultant_detail.html", enquiry=enquiry)
