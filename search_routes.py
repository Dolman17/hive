from __future__ import annotations

from flask import jsonify, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from models import (
    AppModule,
    ConsultantAppAccess,
    CoverRequest,
    ExpertRequest,
    Lead,
    Resource,
    Subscription,
)


TIER_RANKS = {
    "free": 0,
    "starter": 10,
    "professional": 20,
    "covered": 30,
    "boutique": 40,
    "admin": 100,
}


def _clean_query(value: str) -> str:
    return " ".join((value or "").strip().split())[:80]


def _like_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _result(kind: str, title: str, subtitle: str, url: str, key: str):
    return {
        "kind": kind,
        "title": title,
        "subtitle": subtitle,
        "url": url,
        "key": key,
    }


def _resource_rank_for_user() -> int:
    subscription = Subscription.query.filter_by(user_id=current_user.id).first()
    if not subscription or subscription.status not in {"active", "trial"}:
        return TIER_RANKS["free"]
    return TIER_RANKS.get(subscription.tier, TIER_RANKS["free"])


def register_search_routes(bp):
    @bp.get("/api/search")
    @login_required
    def global_search_api():
        if current_user.role != "consultant":
            return jsonify({"ok": False, "error": "Forbidden.", "results": []}), 403

        query = _clean_query(request.args.get("q", ""))
        if len(query) < 2:
            return jsonify({"ok": True, "query": query, "results": []})

        pattern = _like_pattern(query)
        results = []

        leads = (
            Lead.query
            .filter(Lead.assigned_consultant_id == current_user.id)
            .filter(or_(
                Lead.company_name.ilike(pattern, escape="\\"),
                Lead.contact_name.ilike(pattern, escape="\\"),
                Lead.contact_email.ilike(pattern, escape="\\"),
                Lead.sector.ilike(pattern, escape="\\"),
                Lead.signal_type.ilike(pattern, escape="\\"),
                Lead.signal_summary.ilike(pattern, escape="\\"),
                Lead.support_needed.ilike(pattern, escape="\\"),
            ))
            .order_by(Lead.updated_at.desc())
            .limit(6)
            .all()
        )
        for lead in leads:
            status = (lead.status or "new").replace("_", " ").title()
            context = lead.contact_name or lead.location or lead.sector or "PeopleSignal"
            results.append(_result(
                "opportunity",
                lead.company_name,
                f"Opportunity · {status} · {context}",
                url_for("lead_detail", lead_id=lead.id),
                f"lead:{lead.id}",
            ))

        # Directory enquiries live in their route module rather than models.py.
        # Import lazily at request time to avoid the existing notification/enquiry import cycle.
        from directory_enquiry_routes import DirectoryEnquiry

        enquiries = (
            DirectoryEnquiry.query
            .filter(DirectoryEnquiry.assigned_consultant_id == current_user.id)
            .filter(or_(
                DirectoryEnquiry.company_name.ilike(pattern, escape="\\"),
                DirectoryEnquiry.contact_name.ilike(pattern, escape="\\"),
                DirectoryEnquiry.contact_email.ilike(pattern, escape="\\"),
                DirectoryEnquiry.support_needed.ilike(pattern, escape="\\"),
            ))
            .order_by(DirectoryEnquiry.updated_at.desc())
            .limit(6)
            .all()
        )
        for enquiry in enquiries:
            status = (enquiry.status or "new").replace("_", " ").title()
            results.append(_result(
                "opportunity",
                enquiry.company_name,
                f"Directory enquiry · {status} · {enquiry.contact_name}",
                url_for(
                    "directory_enquiries.consultant_directory_enquiry_detail",
                    enquiry_id=enquiry.id,
                ),
                f"directory-enquiry:{enquiry.id}",
            ))

        covers = (
            CoverRequest.query
            .filter(CoverRequest.consultant_id == current_user.id)
            .filter(or_(
                CoverRequest.cover_type.ilike(pattern, escape="\\"),
                CoverRequest.summary.ilike(pattern, escape="\\"),
                CoverRequest.status.ilike(pattern, escape="\\"),
            ))
            .order_by(CoverRequest.updated_at.desc())
            .limit(5)
            .all()
        )
        for cover in covers:
            cover_type = (cover.cover_type or "cover").replace("_", " ").title()
            status = (cover.status or "draft").replace("_", " ").title()
            date_range = f"{cover.start_date:%d %b %Y} to {cover.end_date:%d %b %Y}"
            results.append(_result(
                "cover",
                cover_type,
                f"HIVE Covered · {status} · {date_range}",
                url_for("cover_detail", cover_id=cover.id),
                f"cover:{cover.id}",
            ))

        expert_requests = (
            ExpertRequest.query
            .filter(ExpertRequest.consultant_id == current_user.id)
            .filter(or_(
                ExpertRequest.subject.ilike(pattern, escape="\\"),
                ExpertRequest.category.ilike(pattern, escape="\\"),
                ExpertRequest.summary.ilike(pattern, escape="\\"),
                ExpertRequest.desired_outcome.ilike(pattern, escape="\\"),
                ExpertRequest.status.ilike(pattern, escape="\\"),
            ))
            .order_by(ExpertRequest.updated_at.desc())
            .limit(5)
            .all()
        )
        for expert in expert_requests:
            category = (expert.category or "Expert Help").replace("_", " ").title()
            status = (expert.status or "new").replace("_", " ").title()
            results.append(_result(
                "expert",
                expert.subject,
                f"Expert Help · {category} · {status}",
                url_for("expert_help_detail", request_id=expert.id),
                f"expert:{expert.id}",
            ))

        resource_rank = _resource_rank_for_user()
        resources = (
            Resource.query
            .filter(Resource.is_active.is_(True))
            .filter(or_(
                Resource.title.ilike(pattern, escape="\\"),
                Resource.category.ilike(pattern, escape="\\"),
                Resource.description.ilike(pattern, escape="\\"),
            ))
            .order_by(Resource.updated_at.desc())
            .limit(12)
            .all()
        )
        visible_resources = [
            resource for resource in resources
            if TIER_RANKS.get(resource.required_tier or "starter", TIER_RANKS["starter"]) <= resource_rank
        ][:5]
        for resource in visible_resources:
            category = resource.category or "Resource"
            results.append(_result(
                "resource",
                resource.title,
                f"Toolkit · {category}",
                url_for("resource_detail", resource_id=resource.id),
                f"resource:{resource.id}",
            ))

        app_accesses = (
            ConsultantAppAccess.query
            .join(AppModule, ConsultantAppAccess.app_module_id == AppModule.id)
            .filter(
                ConsultantAppAccess.consultant_id == current_user.id,
                ConsultantAppAccess.status == "active",
                AppModule.is_active.is_(True),
                or_(
                    AppModule.name.ilike(pattern, escape="\\"),
                    AppModule.description.ilike(pattern, escape="\\"),
                ),
            )
            .order_by(AppModule.name.asc())
            .limit(5)
            .all()
        )
        for access in app_accesses:
            app = access.app_module
            results.append(_result(
                "app",
                app.name,
                "Connected app · Active access",
                url_for("launch_app", app_slug=app.slug),
                f"app:{app.id}",
            ))

        return jsonify({
            "ok": True,
            "query": query,
            "results": results[:24],
        })
