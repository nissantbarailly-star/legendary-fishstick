import os
import secrets
from functools import wraps

from authlib.integrations.flask_client import OAuth
from flask import Flask, jsonify, redirect, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select

from storage import StorageNotConfigured, get_storage_provider


db = SQLAlchemy()
oauth = OAuth()


class Department(db.Model):
    id = db.Column(db.String(80), primary_key=True)
    name = db.Column(db.String(160), nullable=False, unique=True)
    category = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    owner_role = db.Column(db.String(120), nullable=False, default="Unassigned")
    active = db.Column(db.Boolean, nullable=False, default=True)
    templates = db.relationship("Template", back_populates="department_ref", cascade="all, delete-orphan")


class Template(db.Model):
    id = db.Column(db.String(80), primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    department_id = db.Column(db.String(80), db.ForeignKey("department.id"), nullable=False)
    file_type = db.Column(db.String(40), nullable=False, default="Document")
    description = db.Column(db.Text, nullable=False, default="")
    storage_key = db.Column(db.String(500), nullable=True)  # Opaque provider key, never sent to client.
    active = db.Column(db.Boolean, nullable=False, default=True)
    department_ref = db.relationship("Department", back_populates="templates")


class ChangeRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    department_id = db.Column(db.String(80), db.ForeignKey("department.id"), nullable=False)
    request_type = db.Column(db.String(80), nullable=False)
    details = db.Column(db.Text, nullable=False)
    requester_subject = db.Column(db.String(255), nullable=False)
    requester_email = db.Column(db.String(320))
    status = db.Column(db.String(30), nullable=False, default="submitted")
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())


class RolloutTask(db.Model):
    id = db.Column(db.String(100), primary_key=True)
    phase = db.Column(db.String(100), nullable=False)
    title = db.Column(db.String(250), nullable=False)
    owner_role = db.Column(db.String(160), nullable=False)
    complete = db.Column(db.Boolean, nullable=False, default=False)
    updated_by = db.Column(db.String(255))
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now(), onupdate=db.func.now())


class TemplateCopy(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.String(80), db.ForeignKey("template.id"), nullable=False)
    user_subject = db.Column(db.String(255), nullable=False)
    user_email = db.Column(db.String(320))
    copied_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    destination_id = db.Column(db.String(500), nullable=False)


def create_app():
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY", "local-development-only-change-me"),
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", "sqlite:///office_desk.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true",
        MAX_CONTENT_LENGTH=64 * 1024,
    )
    if os.getenv("APP_ENV") == "production" and app.config["SECRET_KEY"] == "local-development-only-change-me":
        raise RuntimeError("Set a strong SECRET_KEY in production.")

    db.init_app(app)
    oauth.init_app(app)
    issuer = os.getenv("OIDC_ISSUER", "").rstrip("/")
    client_id, client_secret = os.getenv("OIDC_CLIENT_ID"), os.getenv("OIDC_CLIENT_SECRET")
    if issuer and client_id and client_secret:
        oauth.register(name="company", client_id=client_id, client_secret=client_secret,
                       server_metadata_url=issuer + "/.well-known/openid-configuration",
                       client_kwargs={"scope": "openid email profile"})

    def authenticated(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not session.get("user"):
                return jsonify(error="authentication_required"), 401
            return view(*args, **kwargs)
        return wrapped

    def csrf_protected(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not secrets.compare_digest(request.headers.get("X-CSRF-Token", ""), session.get("csrf_token", "")):
                return jsonify(error="csrf_validation_failed"), 403
            return view(*args, **kwargs)
        return wrapped

    def admin_required(view):
        @wraps(view)
        @authenticated
        def wrapped(*args, **kwargs):
            admin_group = os.getenv("OIDC_ADMIN_GROUP_ID", "")
            groups = session["user"].get("groups", [])
            if not admin_group or admin_group not in groups:
                return jsonify(error="admin_access_required"), 403
            return view(*args, **kwargs)
        return wrapped

    def serialize_department(row):
        return {"id": row.id, "name": row.name, "category": row.category,
                "description": row.description, "ownerRole": row.owner_role,
                "templatesCount": sum(1 for t in row.templates if t.active)}

    def serialize_template(row):
        department = row.department_ref
        return {"id": row.id, "name": row.name, "department": department.name,
                "departmentId": department.id, "category": department.category,
                "ownerRole": department.owner_role, "type": row.file_type,
                "description": row.description, "copyAvailable": bool(row.storage_key)}

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    @app.get("/auth/login")
    def login():
        client = oauth.create_client("company")
        if client is None:
            return jsonify(error="oidc_not_configured"), 503
        redirect_uri = os.getenv("OIDC_REDIRECT_URI") or url_for("auth_callback", _external=True)
        return client.authorize_redirect(redirect_uri)

    @app.get("/auth/callback")
    def auth_callback():
        client = oauth.create_client("company")
        if client is None:
            return jsonify(error="oidc_not_configured"), 503
        token = client.authorize_access_token()
        userinfo = token.get("userinfo") or {}
        if not userinfo.get("sub"):
            return jsonify(error="identity_missing_subject"), 401
        session.clear()
        session["user"] = {"sub": userinfo["sub"], "name": userinfo.get("name") or userinfo.get("preferred_username") or "Company user",
                           "email": userinfo.get("email"), "groups": userinfo.get("groups", [])}
        session["csrf_token"] = secrets.token_urlsafe(32)
        return redirect(os.getenv("FRONTEND_URL", "http://localhost:5173"), code=302)

    @app.post("/auth/logout")
    @authenticated
    @csrf_protected
    def logout():
        session.clear()
        return jsonify(ok=True)

    @app.get("/api/me")
    def me():
        user = session.get("user")
        return (jsonify(user={k: v for k, v in user.items() if k != "groups"}), 200) if user else (jsonify(user=None), 401)

    @app.get("/api/csrf")
    @authenticated
    def csrf():
        return jsonify(token=session.setdefault("csrf_token", secrets.token_urlsafe(32)))

    @app.get("/api/departments")
    @authenticated
    def departments():
        rows = db.session.execute(select(Department).where(Department.active.is_(True)).order_by(Department.name)).scalars()
        return jsonify(departments=[serialize_department(row) for row in rows])

    @app.get("/api/templates")
    @authenticated
    def templates():
        rows = db.session.execute(select(Template).join(Department).where(Template.active.is_(True), Department.active.is_(True)).order_by(Department.name, Template.name)).scalars()
        return jsonify(templates=[serialize_template(row) for row in rows])

    @app.post("/api/templates/<string:template_id>/copy")
    @authenticated
    @csrf_protected
    def copy_template(template_id):
        row = db.session.get(Template, template_id)
        if row is None or not row.active:
            return jsonify(error="template_not_found"), 404
        if not row.storage_key:
            return jsonify(error="template_source_not_configured"), 409
        payload = request.get_json(silent=True) or {}
        copy_name = payload.get("name", row.name)
        if not isinstance(copy_name, str) or not copy_name.strip() or len(copy_name.strip()) > 200:
            return jsonify(error="invalid_copy_name"), 400
        user = session["user"]
        try:
            result = get_storage_provider().create_copy(source_key=row.storage_key, copy_name=copy_name.strip(), requested_by=user["sub"])
        except StorageNotConfigured:
            return jsonify(error="storage_not_configured"), 503
        except RuntimeError:
            app.logger.exception("Storage copy failed for template %s", row.id)
            return jsonify(error="storage_copy_failed"), 502
        db.session.add(TemplateCopy(template_id=row.id, user_subject=user["sub"], user_email=user.get("email"), destination_id=result["destination_id"]))
        db.session.commit()
        return jsonify(copy={"name": copy_name.strip(), "url": result["url"]}), 201

    @app.post("/api/requests")
    @authenticated
    @csrf_protected
    def create_request():
        payload = request.get_json(silent=True) or {}
        department_id, request_type, details = payload.get("departmentId"), payload.get("type"), payload.get("details")
        if not isinstance(request_type, str) or request_type not in {"New template", "Update existing template", "Retire template", "Report an issue"}:
            return jsonify(error="invalid_request_type"), 400
        if not isinstance(details, str) or not details.strip() or len(details) > 5000:
            return jsonify(error="invalid_details"), 400
        department = db.session.get(Department, department_id) if isinstance(department_id, str) else None
        if department is None or not department.active:
            return jsonify(error="department_not_found"), 404
        user = session["user"]
        row = ChangeRequest(department_id=department.id, request_type=request_type, details=details.strip(), requester_subject=user["sub"], requester_email=user.get("email"))
        db.session.add(row)
        db.session.commit()
        return jsonify(request={"id": row.id, "status": row.status}), 201

    @app.get("/api/requests")
    @admin_required
    def list_requests():
        rows = db.session.execute(select(ChangeRequest).order_by(ChangeRequest.created_at.desc()).limit(200)).scalars()
        return jsonify(requests=[{"id": r.id, "departmentId": r.department_id, "type": r.request_type, "details": r.details, "status": r.status, "createdAt": r.created_at.isoformat(), "requesterEmail": r.requester_email} for r in rows])

    @app.get("/api/rollout")
    @authenticated
    def rollout():
        rows = db.session.execute(select(RolloutTask).order_by(RolloutTask.phase, RolloutTask.id)).scalars()
        return jsonify(tasks=[{"id": r.id, "phase": r.phase, "title": r.title, "ownerRole": r.owner_role, "complete": r.complete} for r in rows])

    @app.patch("/api/rollout/<string:task_id>")
    @admin_required
    @csrf_protected
    def update_rollout(task_id):
        row = db.session.get(RolloutTask, task_id)
        if row is None:
            return jsonify(error="task_not_found"), 404
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload.get("complete"), bool):
            return jsonify(error="invalid_complete_value"), 400
        row.complete, row.updated_by = payload["complete"], session["user"]["sub"]
        db.session.commit()
        return jsonify(task={"id": row.id, "complete": row.complete})

    @app.post("/api/admin/departments")
    @admin_required
    @csrf_protected
    def create_department():
        data = request.get_json(silent=True) or {}
        fields = [data.get(k) for k in ("id", "name", "category", "ownerRole")]
        if not all(isinstance(v, str) and v.strip() for v in fields) or len(data.get("id", "")) > 80:
            return jsonify(error="invalid_department"), 400
        row = Department(id=data["id"].strip(), name=data["name"].strip(), category=data["category"].strip(), owner_role=data["ownerRole"].strip(), description=str(data.get("description", ""))[:2000])
        db.session.add(row)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            return jsonify(error="department_conflict"), 409
        return jsonify(department=serialize_department(row)), 201

    @app.post("/api/admin/templates")
    @admin_required
    @csrf_protected
    def create_template():
        data = request.get_json(silent=True) or {}
        required = ("id", "name", "departmentId", "type")
        if not all(isinstance(data.get(k), str) and data[k].strip() for k in required):
            return jsonify(error="invalid_template"), 400
        if len(data["id"]) > 80 or len(data["name"]) > 200:
            return jsonify(error="invalid_template"), 400
        if not db.session.get(Department, data["departmentId"]):
            return jsonify(error="department_not_found"), 404
        row = Template(id=data["id"].strip(), name=data["name"].strip(), department_id=data["departmentId"], file_type=data["type"].strip()[:40], description=str(data.get("description", ""))[:2000], storage_key=data.get("storageKey") or None)
        db.session.add(row)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            return jsonify(error="template_conflict"), 409
        return jsonify(template=serialize_template(row)), 201

    with app.app_context():
        if os.getenv("AUTO_CREATE_SCHEMA", "true").lower() == "true":
            db.create_all()  # Development bootstrap only; use migrations in production.
        if db.session.execute(select(Department.id).limit(1)).first() is None:
            db.session.add_all([
                Department(id="hr", name="Human Resources", category="People & Culture", owner_role="HR Director", description="Hiring, onboarding and employee lifecycle."),
                Department(id="finance", name="Finance", category="Finance & Risk", owner_role="Finance Controller", description="Expenses, purchasing and reporting."),
                Department(id="operations", name="Operations", category="Operations & Workplace", owner_role="Chief Operating Officer", description="Processes, incidents and schedules."),
            ])
            db.session.flush()
            db.session.add_all([
                Template(id="hr-leave-request", name="Leave Request", department_id="hr", file_type="Form", description="Employee leave request starting point."),
                Template(id="finance-expense-report", name="Expense Report", department_id="finance", file_type="Spreadsheet", description="Expense reporting starting point."),
                Template(id="operations-sop", name="SOP Template", department_id="operations", file_type="Document", description="Standard operating procedure starting point."),
            ])
            db.session.commit()
    return app


app = create_app()
