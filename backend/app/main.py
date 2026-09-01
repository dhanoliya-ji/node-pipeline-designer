"""Application entry point.

Run it with:

    python -m uvicorn app.main:app --reload --port 8000

The app is built by a factory so tests can create an isolated instance, and
the routes live in `app.api` so this file stays limited to wiring.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api import router
from .config import CORS_ORIGIN_REGEX

DESCRIPTION = """
The backend of **Node Pipeline Designer**.

It takes the graph a user draws on the canvas and answers three questions:
is it a valid directed acyclic graph, is it wired correctly, and what
happens when it runs.
""".strip()


def create_app() -> FastAPI:
    app = FastAPI(
        title='Node Pipeline Designer API',
        description=DESCRIPTION,
        version=__version__,
    )

    # The dev frontend is served from a different origin, so the browser
    # preflights every POST. A regex rather than a fixed list because
    # Create React App moves to another port when 3000 is taken.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=CORS_ORIGIN_REGEX,
        allow_methods=['*'],
        allow_headers=['*'],
    )

    app.include_router(router)

    @app.get('/', tags=['meta'])
    def read_root() -> dict:
        return {
            'name': 'Node Pipeline Designer API',
            'version': __version__,
            'docs': '/docs',
        }

    return app


app = create_app()
