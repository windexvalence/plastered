from plastered.api.routes.api_routes import plastered_api_router
from plastered.api.routes.auth_routes import auth_router
from plastered.api.routes.webserver_routes import plastered_web_router

__all__ = ["auth_router", "plastered_api_router", "plastered_web_router"]
