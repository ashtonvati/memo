from __future__ import annotations

from functools import wraps

from flask import Response, current_app, redirect, request, session, url_for


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def device_token_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        configured_token = current_app.config["moment_config"].device_api_token
        supplied_token = request.headers.get("Authorization", "").removeprefix("Bearer ")
        if not configured_token or supplied_token != configured_token:
            return Response("Unauthorized", status=401)
        return view(*args, **kwargs)

    return wrapped
