import uvicorn
from fastapi import FastAPI

from manta.routes.health_route import router as health_router


def create_app() -> FastAPI:
    app = FastAPI(title="Manta")
    app.include_router(health_router)
    return app


app = create_app()


def main():
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
