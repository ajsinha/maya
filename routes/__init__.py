"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Route modules. Each subclasses Routes, which owns the scaffolding they all
share: the services, the brand context, the domain-refusal mapping, and the
login check. Routers hold no domain logic.
"""
from routes.assist_routes import AssistRoutes
from routes.baseline_routes import BaselineRoutes
from routes.auth_routes import AuthRoutes
from routes.base import API, Routes, current_user, login_required
from routes.feature_routes import FeatureRoutes
from routes.warrant_routes import WarrantRoutes
from routes.document_routes import DocumentRoutes
from routes.grammar_routes import GrammarRoutes
from routes.lifecycle_routes import LifecycleRoutes
from routes.model_routes import ModelRoutes
from routes.monitoring_routes import MonitoringRoutes
from routes.overlay_routes import OverlayRoutes
from routes.principal_routes import PrincipalRoutes
from routes.regime_routes import RegimeRoutes
from routes.public_routes import PublicRoutes
from routes.ui_routes import UIRoutes
from routes.validation_routes import ValidationRoutes

# Order matters: the model path segment is a greedy `:path` converter (URNs
# carry dots and slashes), so the module with the longer, more specific paths
# must register first or it will never be reached.
ALL_ROUTES = (PublicRoutes, AuthRoutes, PrincipalRoutes, GrammarRoutes,
              ModelRoutes, LifecycleRoutes,
              WarrantRoutes, FeatureRoutes, ValidationRoutes, MonitoringRoutes,
              DocumentRoutes, OverlayRoutes, AssistRoutes, BaselineRoutes,
              RegimeRoutes,
              UIRoutes)

__all__ = ["Routes", "API", "ALL_ROUTES", "AuthRoutes", "FeatureRoutes", "WarrantRoutes",
           "ModelRoutes", "PublicRoutes", "UIRoutes", "ValidationRoutes", "PrincipalRoutes",
           "LifecycleRoutes", "MonitoringRoutes", "GrammarRoutes", "DocumentRoutes", "OverlayRoutes", "AssistRoutes", "BaselineRoutes", "RegimeRoutes", "current_user", "login_required"]
