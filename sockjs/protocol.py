import collections
import hashlib
from datetime import datetime

STATE_NEW = 0
STATE_OPEN = 1
STATE_CLOSING = 2
STATE_CLOSED = 3

_days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_months = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
]

# json
# -----------

# Fastest
try:
    import ujson as json

    dumps_kwargs = {}  # pragma: no cover
except ImportError:  # pragma: no cover
    def datetime_handler(obj):
        if isinstance(obj, datetime):
            now = obj.timetuple()
            return "%s, %02d %s %04d %02d:%02d:%02d -0000" % (
                _days[now[6]],
                now[2],
                _months[now[1] - 1],
                now[0],
                now[3],
                now[4],
                now[5],
            )

    dumps_kwargs = {"default": datetime_handler, "separators": (",", ":")}

    # Faster
    try:
        import simplejson as json
    except ImportError:
        # Slowest
        import json

# Frames
# ------

FRAME_OPEN = "o"
FRAME_CLOSE = "c"
FRAME_MESSAGE = "a"
FRAME_MESSAGE_BLOB = "a1"
FRAME_HEARTBEAT = "h"

# ------------------

HTMLFILE_HTML = """
<!doctype html>
<html><head>
  <meta http-equiv="X-UA-Compatible" content="IE=edge" />
  <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
</head><body><h2>Don't panic!</h2>
  <script>
    document.domain = document.domain;
    var c = parent.%s;
    c.start();
    function p(d) {c.message(d);};
    window.onload = function() {c.stop();};
  </script>
""".strip()

IFRAME_HTML = """<!DOCTYPE html>
<html>
<head>
<meta http-equiv="X-UA-Compatible" content="IE=edge" />
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
  <script src="%s"></script>
  <script>
    document.domain = document.domain;
    SockJS.bootstrap_iframe();
  </script>
</head>
<body>
  <h2>Don"t panic!</h2>
  <p>This is a SockJS hidden iframe. It"s used for cross domain magic.</p>
</body>
</html>""".strip()

IFRAME_MD5 = hashlib.md5(IFRAME_HTML.encode("utf-8")).hexdigest()

loads = json.loads


def dumps(data):
    return json.dumps(data, **dumps_kwargs)


def close_frame(code, reason):
    return FRAME_CLOSE + json.dumps([code, reason], **dumps_kwargs)


def message_frame(message):
    return FRAME_MESSAGE + json.dumps([message], **dumps_kwargs)


def messages_frame(messages):
    return FRAME_MESSAGE + json.dumps(messages, **dumps_kwargs)


# Handler messages
# ---------------------

MSG_OPEN = 1
MSG_MESSAGE = 2
MSG_CLOSE = 3
MSG_CLOSED = 4

SockjsMessage = collections.namedtuple("SockjsMessage", ["type", "data"])

OpenMessage = SockjsMessage(MSG_OPEN, None)
CloseMessage = SockjsMessage(MSG_CLOSE, None)
ClosedMessage = SockjsMessage(MSG_CLOSED, None)
