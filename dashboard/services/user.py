"""User tracking abstraction for session-based user identification.

This module provides a simple abstraction for tracking the current user across
requests. Currently uses Flask session with manual name entry, but designed
to be easily swapped to authentication-based user identification later.

Usage in routes:
    from dashboard.services.user import get_current_user, get_user_from_request

    # In a route handler:
    user = get_user_from_request(json_key="reviewer")

Usage in templates:
    {{ current_user }}  # Injected via context processor
"""

from typing import Optional

from flask import session, request


def get_current_user() -> Optional[str]:
    """Get the current user from session or request headers.

    Checks in order:
    1. Flask session ('current_user' key)
    2. X-User header (for API clients)

    Returns:
        User name if found, None otherwise.
    """
    # Check session first (persists across requests)
    if "current_user" in session:
        return session["current_user"]

    # Fall back to X-User or X-User-Name header (for API clients)
    x_user = request.headers.get("X-User") or request.headers.get("X-User-Name")
    if x_user:
        return x_user

    return None


def set_current_user(name: str) -> None:
    """Store the current user in the Flask session.

    Args:
        name: The user's name to store.
    """
    if name and name.strip():
        session["current_user"] = name.strip()


def clear_current_user() -> None:
    """Clear the current user from the session."""
    session.pop("current_user", None)


def get_user_from_request(
    json_key: str = "reviewer",
    form_key: Optional[str] = None,
    query_key: str = "user",
    default: Optional[str] = None,
    remember: bool = True,
) -> Optional[str]:
    """Get user from request data, falling back to session/header.

    This is the main helper for routes. It checks multiple sources in order:
    1. JSON body (if present) using json_key
    2. Form data using form_key (defaults to json_key if not specified)
    3. Query parameters using query_key
    4. Session (via get_current_user)
    5. X-User header (via get_current_user)
    6. Default value

    If remember=True and a user is found in the request, it's stored in
    the session for future requests.

    Args:
        json_key: Key to check in JSON body (default: "reviewer")
        form_key: Key to check in form data (default: same as json_key)
        query_key: Key to check in query params (default: "user")
        default: Default value if no user found anywhere
        remember: If True, store found user in session

    Returns:
        User name if found, default otherwise.
    """
    user = None

    # Use json_key for form if not specified
    if form_key is None:
        form_key = json_key

    # 1. Check JSON body
    if request.is_json and request.json:
        user = request.json.get(json_key)
        if user:
            user = user.strip()

    # 2. Check form data
    if not user and request.form:
        user = request.form.get(form_key)
        if user:
            user = user.strip()

    # 3. Check query parameters
    if not user:
        user = request.args.get(query_key)
        if user:
            user = user.strip()

    # 4-5. Check session and X-User header
    if not user:
        user = get_current_user()

    # 6. Use default
    if not user:
        user = default

    # Remember the user if found and remember=True
    if user and remember:
        set_current_user(user)

    return user
