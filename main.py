from typing import Dict

import uvicorn
from fastapi import FastAPI

import under_control

app = FastAPI()


@app.get("/")
def read_root() -> Dict:
    return {"Hello": "World"}


@app.on_event("shutdown")
def shutdown_event():
    under_control.stop()


if __name__ == "__main__":
    under_control.setup('config.toml')
    under_control.start(app)
    uvicorn.run(app, host="0.0.0.0", port=7654)
