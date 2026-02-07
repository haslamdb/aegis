"""Standardized API response helpers for the AEGIS dashboard.

All JSON API endpoints should return responses in a unified envelope format:

    Success: {"success": true, "data": ..., "message": ...}
    Error:   {"success": false, "error": ...}

Usage:
    from dashboard.utils.api_response import api_success, api_error

    @bp.route("/api/stats")
    def api_stats():
        try:
            stats = db.get_stats()
            return api_success(data=stats)
        except Exception as e:
            return api_error(str(e), 500)
"""

from flask import jsonify


def api_success(data=None, message=None):
    """Return a standardized success response.

    Returns: {"success": true, "data": ..., "message": ...}
    """
    response = {"success": True}
    if data is not None:
        response["data"] = data
    if message is not None:
        response["message"] = message
    return jsonify(response)


def api_error(error, status_code=400):
    """Return a standardized error response.

    Returns: {"success": false, "error": ...}
    """
    return jsonify({"success": False, "error": str(error)}), status_code
