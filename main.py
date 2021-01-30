from typing import Dict, List

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import under_control
import under_control.config as config
import under_control.logger as log

app = FastAPI()


def set_cors(app: FastAPI, origins: List[str]):
    log.logger.info(f"Enabling CORS middleware for origins: {origins}")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.get("/")
def read_root() -> Dict:
    return {"Hello": "World"}


@app.on_event("shutdown")
def shutdown_event():
    under_control.stop()


if __name__ == "__main__":
    under_control.setup('config.toml')
    cors_origins = config.get("cors_origins")
    if cors_origins:
        set_cors(app, cors_origins)
    under_control.start(app)
    uvicorn.run(app, host="0.0.0.0", port=7654)
