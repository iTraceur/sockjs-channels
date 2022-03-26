import http.cookies
from datetime import datetime, timedelta

CACHE_CONTROL = b"no-store, no-cache, no-transform, must-revalidate, max-age=0"


def cors_headers(headers, force=False):
    headers = dict(headers)
    origin = headers.get(b"Origin", b"*")
    if force:
        origin = b"*"

    cors = {b"Access-Control-Allow-Origin": origin}

    ac_headers = headers.get(b"Access-Control-Request-Headers")
    if ac_headers:
        cors[b"Access-Control-Allow-Headers"] = ac_headers

    if origin != b"*":
        cors[b"Access-Control-Allow-Credentials"] = b"true"

    return cors


def session_cookie(scope):
    session_id = scope.get("cookies", {}).get("sessionID", "dummy")
    cookies = http.cookies.SimpleCookie()
    cookies["sessionID"] = session_id
    cookies["sessionID"]["path"] = "/"
    return {b"Set-Cookie": cookies["sessionID"].OutputString().encode("utf-8")}


td365 = timedelta(days=365)
td365seconds = str(int(td365.total_seconds())).encode("utf-8")


def cache_headers():
    d = datetime.now() + td365
    return {
        b"Access-Control-Max-Age": td365seconds,
        b"Cache-Control": b"max-age=%s, public" % td365seconds,
        b"Expires": d.strftime("%a, %d %b %Y %H:%M:%S").encode("utf-8"),
    }
