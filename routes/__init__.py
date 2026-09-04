"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Route handlers. Each class takes the FastAPI app and the services it needs, and
registers its own endpoints. Routers hold no domain logic: they validate input,
call a service, and shape the response.
"""
from routes.auth_routes import AuthRoutes, current_user, login_required
from routes.health_routes import HealthRoutes
from routes.hook_routes import HookRoutes
from routes.model_routes import ModelRoutes
from routes.public_routes import PublicRoutes
from routes.ui_routes import UIRoutes

__all__ = ["AuthRoutes", "HealthRoutes", "HookRoutes", "ModelRoutes",
           "PublicRoutes", "UIRoutes", "current_user", "login_required"]
