from .app import App
from .foundation import AppSettings, AppState, deprecated
from .auth import (
    AccountManager,
    AccountRecord,
    AuthBackend,
    Identity,
    InMemoryAuthBackend,
    PasswordHasher,
    PasswordResetManager,
    authenticate_with,
    create_token,
    has_permission,
    has_role,
    normalize_identity,
    verify_token,
)
from .authorization import (
    AuthorizationPolicy,
    PolicyRegistry,
    authorize,
    build_permission,
    evaluate_policy,
    has_resource_permission,
    require_auth,
    require_permission,
    require_policy,
    require_resource_permission,
    require_role,
)
from .admin import AdminModelConfig, AdminPanel
from .cache import cache, cache_get, cache_set, cache_delete
from .middleware import auth_middleware, cors_middleware, security_headers_middleware
from .orm import Model
from .http import Request, Response, JSONResponse, BackgroundTasks, WebSocket, UploadedFile
from .rate_limit import rate_limit
from .db import Base, engine, SessionLocal, init_db, get_db_session
from .exceptions import HTTPException, WebSocketException
from .plugins import Plugin
from .sessions import (
    session_middleware,
    set_session_value,
    get_session_value,
    clear_session,
    set_session_user,
    get_session_user,
    login_user,
    logout_user,
    rotate_session,
    get_csrf_token,
    validate_csrf,
    csrf_middleware,
    SessionStore,
    InMemorySessionStore,
)
from .templating import JinjaTemplateEngine, TemplateEngine
from .static import mount_static
from .pagination import paginate, get_pagination_params
from .testing import TestClient
from .versioning import VersionedAPI
from .graphql import GraphQL
from .frontend import mount_spa
from .jobs import (
    DispatchedJob,
    DistributedJobQueue,
    InMemoryJobStore,
    JobQueue,
    JobRecord,
    JobStore,
    JobWorker,
    SQLiteJobStore,
)
from .services import ServiceClient
from .stability import API_COMPAT_VERSION, DEPRECATION_POLICY, PUBLIC_API

__version__ = "0.1.0a1"

__all__ = list(PUBLIC_API)
