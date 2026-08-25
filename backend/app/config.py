"""Runtime settings.

Everything here can be overridden with an environment variable so the same
image runs in development and in a container without a code change.
"""

import os

# The dev frontend is served from a different origin, so the browser
# preflights every POST. Any localhost port is allowed by default so the app
# works whichever port Create React App lands on.
CORS_ORIGIN_REGEX = os.getenv(
    'NPD_CORS_ORIGIN_REGEX',
    r'https?://(localhost|127\.0\.0\.1)(:\d+)?',
)

# Guard rails for the execution engine. A pipeline is user input, and a
# runaway graph should fail fast rather than exhaust the worker.
MAX_NODES = int(os.getenv('NPD_MAX_NODES', '2000'))
MAX_EDGES = int(os.getenv('NPD_MAX_EDGES', '8000'))

# Outbound HTTP performed by the API node.
HTTP_TIMEOUT_CEILING = float(os.getenv('NPD_HTTP_TIMEOUT_CEILING', '30'))
ALLOW_OUTBOUND_HTTP = os.getenv('NPD_ALLOW_OUTBOUND_HTTP', 'false').lower() == 'true'
