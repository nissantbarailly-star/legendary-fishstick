import os
from functools import wraps
from urllib.parse import urlparse

from authlib.integrations.flask_client import OAuth
from flask import Flask, jsonify, redirect, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select

from storage import StorageNotConfigured, get_storage_provider


db = SQLAlchemy()
oauth = OAuth()


class Template(db.Model):
    id = db.Column(db.String(80), primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    department = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(120), nullable=False, default="Uncategorized")
    owner_role = db.Column(db.String(120), nullable=False, default="Unassigned")
    file_type = db.Column(db.String(40), nullable=False, default="Document")
    description = db.Column(db.Text, nullable=False, default="")
    # Opaque key understood only by the configured server-side storage adapter.
    storage_key = db.Column(db.String(500), nullable=True)
    active = db.Column(db.Boolean, nullable=False, default=True)


class TemplateCopy(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.String(80), db.ForeignKey("template.id"), nullable=False)
    user_subject = db.Column(db.String(255), nullable=False)
    user_email = db.Column(db.String(320), nullable=True)
    copied_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    destination_id = db.Column(db.String(500), nullable=False)


def create_app():
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY", "local-development-only-change-me"),
        SQLALCHEMY_DATABASE_URI=os.getenv(
            "DATABASE_URL", "sqlite:///office_desk.db"
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true",
    )
    if os.getenv("APP_ENV") == "production" and app.config["SECRET_KEY"] == "local-development-only-change-me":
        raise RuntimeError("Set a strong SECRET_KEY in production.")

    db.init_app(app)
    oauth.init_app(app)

    issuer = os.getenv("OIDC_ISSUER", "").rstrip("/")
    client_id = os.getenv("OIDC_CLIENT_ID")
    client_secret = os.getenv("OIDC_CLIENT_SECRET")
    if issuer and client_id and client_secret:
        metadata_url = issuer + "/.well-known/openid-configuration"
        oauth.register(
            name="company",
            client_id=client_id,
            client_secret=client_secret,
            server_metadata_url=metadata_url,
            client_kwargs={"scope": "openid email profile"},
        )

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    def authenticated(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not session.get("user"):
                return jsonify(error="authentication_required"), 401
            return view(*args, **kwargs)
        return wrapped

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
        subject = userinfo.get("sub")
        if not subject:
            return jsonify(error="identity_missing_subject"), 401
        session.clear()
        session["user"] = {
            "sub": subject,
            "name": userinfo.get("name") or userinfo.get("preferred_username") or "Company user",
            "email": userinfo.get("email"),
        }
        return redirect(os.getenv("FRONTEND_URL", "http://localhost:5173"), code=302)

    @app.post("/auth/logout")
    def logout():
        session.clear()
        return jsonify(ok=True)

    @app.get("/api/me")
    def me():
        user = session.get("user")
        return jsonify(user=user) if user else (jsonify(user=None), 401)

    @app.get("/api/templates")
    @authenticated
    def templates():
        rows = db.session.execute(
            select(Template).where(Template.active.is_(True)).order_by(Template.department, Template.name)
        ).scalars()
        return jsonify(templates=[{
            "id": row.id,
            "name": row.name,
            "department": row.department,
            "category": row.category,
            "ownerRole": row.owner_role,
            "type": row.file_type,
            "description": row.description,
        } for row in rows])

    @app.post("/api/templates/<string:template_id>/copy")
    @authenticated
    def copy_template(template_id):
        row = db.session.get(Template, template_id)
        if row is None or not row.active:
            return jsonify(error="template_not_found"), 404
        if not row.storage_key:
            return jsonify(error="template_source_not_configured"), 409

        payload = request.get_json(silent=True) or {}
        copy_name = payload.get("name")
        if copy_name is not None and (not isinstance(copy_name, str) or not copy_name.strip() or len(copy_name) > 200):
            return jsonify(error="invalid_copy_name"), 400
        copy_name = (copy_name or row.name).strip()
        user = session["user"]
        try:
            result = get_storage_provider().create_copy(
                source_key=row.storage_key,
                copy_name=copy_name,
                requested_by=user["sub"],
            )
        except StorageNotConfigured:
            return jsonify(error="storage_not_configured"), 503

        db.session.add(TemplateCopy(
            template_id=row.id,
            user_subject=user["sub"],
            user_email=user.get("email"),
            destination_id=result["destination_id"],
        ))
        db.session.commit()
        return jsonify(copy={"name": copy_name, "url": result["url"]}), 201

    with app.app_context():
        db.create_all()
        if db.session.execute(select(Template.id).limit(1)).first() is None:
            db.session.add_all([
                Template(id="hr-leave-request", name="Leave Request", department="Human Resources", category="People & Culture", owner_role="HR Director", file_type="Form", description="Starter catalog example; connect an approved source in storage."),
                Template(id="finance-expense-report", name="Expense Report", department="Finance", category="Finance & Risk", owner_role="Finance Controller", file_type="Spreadsheet", description="Starter catalog example; connect an approved source in storage."),
                Template(id="operations-sop", name="SOP Template", department="Operations", category="Operations & Workplace", owner_role="Chief Operating Officer", file_type="Document", description="Starter catalog example; connect an approved source in storage."),
            ])
            db.session.commit()

    return app


app = create_app()
