import jwt
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os

# Shared across all services via the JWT_SECRET_KEY env var (set in
# docker-compose.yaml). Falls back to the original dev default so the
# service still runs standalone without Docker.
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "my_super_secret_jwt_key_for_microservices")
ALGORITHM = "HS256"

security = HTTPBearer()

def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    """Validates the JWT and returns the payload (user info)"""
    try:
        # Decode the token using our shared secret
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def require_admin(token_data: dict = Security(verify_token)):
    """
    Same as verify_token, but additionally requires the token's role claim
    to be "admin". Use as a dependency on any admin-only route:

        @app.put("/products/{id}")
        def update_product(id: int, token_data: dict = Depends(require_admin)):
            ...

    Relies on the role being embedded in the JWT at login time (see
    services/user-service/main.py's login endpoint) - there's no separate
    database lookup here, so this is only as trustworthy as the token
    issuer (user-service).
    """
    if token_data.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return token_data