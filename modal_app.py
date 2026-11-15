"""Modal smoke boundary for EvoHive. Candidate runs use Sandbox.create dynamically."""

import modal

APP_NAME = "evohive-track1"
app = modal.App(APP_NAME)
image = modal.Image.debian_slim(python_version="3.11").pip_install(".")


@app.function(image=image, timeout=300)
def smoke() -> dict[str, str]:
    return {"app": APP_NAME, "status": "ok", "security": "candidate sandboxes get no secrets"}
