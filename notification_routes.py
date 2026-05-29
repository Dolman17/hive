from datetime import datetime
from functools import wraps

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from extensions import db
from models import User


notifications_bp = Blueprint("notifications", __name__)


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    recipient_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text)
    category = db.Column(db.String(100), default="general", nullable=False)
    link_url = db.Column(db.String(500))
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read_at = db.Column(db.DateTime)

    recipient = db.relationship("User", foreign_keys=[recipient_user_id])


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


def create_notification(recipient_user_id, title, message=None, category="general", link_url=None, commit=False):
    notification = Notification(
        recipient_user_id=recipient_user_id,
        title=title,
        message=message,
        category=category,
        link_url=link_url,
    )
    db.session.add(notification)
    if commit:
        db.session.commit()
    return notification


def notify_admins(title, message=None, category="admin", link_url=None, commit=False):
    admins = User.query.filter_by(role="admin", is_active=True).all()
    notifications = []
    for admin in admins:
        notifications.append(
            create_notification(
                recipient_user_id=admin.id,
                title=title,
                message=message,
                category=category,
                link_url=link_url,
                commit=False,
            )
        )
    if commit:
        db.session.commit()
    return notifications


def unread_notification_count(user):
    if not user or not user.is_authenticated:
        return 0
    return Notification.query.filter_by(recipient_user_id=user.id, is_read=False).count()


@notifications_bp.app_context_processor
def inject_notification_count():
    return {"unread_notification_count": unread_notification_count(current_user)}


@notifications_bp.route("/notifications")
@login_required
def notification_list():
    notifications = Notification.query.filter_by(
        recipient_user_id=current_user.id
    ).order_by(Notification.created_at.desc()).all()
    return render_template("notifications/list.html", notifications=notifications)


@notifications_bp.route("/notifications/<int:notification_id>/read", methods=["POST"])
@login_required
def mark_notification_read(notification_id):
    notification = Notification.query.filter_by(
        id=notification_id,
        recipient_user_id=current_user.id,
    ).first_or_404()

    notification.is_read = True
    notification.read_at = datetime.utcnow()
    db.session.commit()

    if notification.link_url:
        return redirect(notification.link_url)

    return redirect(url_for("notifications.notification_list"))


@notifications_bp.route("/notifications/mark-all-read", methods=["POST"])
@login_required
def mark_all_notifications_read():
    notifications = Notification.query.filter_by(
        recipient_user_id=current_user.id,
        is_read=False,
    ).all()

    for notification in notifications:
        notification.is_read = True
        notification.read_at = datetime.utcnow()

    db.session.commit()
    flash("Notifications marked as read.", "success")
    return redirect(url_for("notifications.notification_list"))


@notifications_bp.route("/admin/notifications")
@login_required
@admin_required
def admin_notifications():
    notifications = Notification.query.order_by(Notification.created_at.desc()).limit(200).all()
    return render_template("notifications/admin_list.html", notifications=notifications)
