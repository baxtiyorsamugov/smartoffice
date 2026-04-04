import contextlib
import os
import warnings

import onnxruntime as ort
import torch
from insightface.app import FaceAnalysis


def configure_runtime():
    warnings.filterwarnings(
        "ignore",
        message="`estimate` is deprecated",
        category=FutureWarning,
    )
    try:
        ort.set_default_logger_severity(3)
    except Exception:
        pass


@contextlib.contextmanager
def suppress_native_output(enabled=True):
    if not enabled:
        yield
        return

    with open(os.devnull, "w") as devnull:
        with contextlib.redirect_stderr(devnull), contextlib.redirect_stdout(devnull):
            yield


def resolve_face_providers():
    providers = ["CPUExecutionProvider"]
    ctx_id = -1

    if torch.cuda.is_available():
        try:
            with suppress_native_output(enabled=True):
                ort.preload_dlls(directory="")
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
            ctx_id = 0
        except Exception as exc:
            print(f"ONNX preload fallback to CPU: {exc}")

    return providers, ctx_id


def build_face_app(det_size=(160, 160)):
    configure_runtime()
    providers, ctx_id = resolve_face_providers()
    try:
        with suppress_native_output(enabled=True):
            app = FaceAnalysis(name="buffalo_l", providers=providers)
            app.prepare(ctx_id=ctx_id, det_size=det_size)
        print(f"InsightFace ready on: {providers[0]}")
        return app
    except Exception as exc:
        if providers[0] == "CUDAExecutionProvider":
            print(f"InsightFace GPU init failed, fallback to CPU: {exc}")
            with suppress_native_output(enabled=True):
                app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
                app.prepare(ctx_id=-1, det_size=det_size)
            print("InsightFace ready on: CPUExecutionProvider")
            return app
        raise
