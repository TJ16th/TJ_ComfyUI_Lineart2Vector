"""
Diagnostic node to report Python runtime information inside ComfyUI.
Helps determine which interpreter is executing the custom nodes so that
dependencies (e.g. cairosvg) can be installed in the correct environment.
"""

import sys
import json
import importlib.util
import platform
from typing import Dict, Any

try:
    import site  # type: ignore
except Exception:
    site = None  # type: ignore


class VectorPythonInfo:
    """ComfyUI node: outputs JSON string with interpreter diagnostics."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("info",)
    FUNCTION = "inspect"
    CATEGORY = "TJ_Vector"

    def inspect(self) -> tuple:
        info: Dict[str, Any] = {}
        info["sys_executable"] = sys.executable
        info["python_version"] = sys.version
        info["platform"] = platform.platform()
        info["implementation"] = platform.python_implementation()
        if site:
            try:
                info["site_packages"] = site.getsitepackages()
            except Exception:
                info["site_packages"] = []
        # Selected packages presence
        for pkg in ["cairosvg", "cairocffi", "tinycss2", "cssselect2", "PIL", "skimage", "cv2"]:
            spec = importlib.util.find_spec(pkg)
            info[f"has_{pkg}"] = bool(spec)
            if spec and spec.origin:
                info[f"{pkg}_location"] = spec.origin
        return (json.dumps(info, indent=2),)


NODE_CLASS_MAPPINGS = {
    "VectorPythonInfo": VectorPythonInfo
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "VectorPythonInfo": "Python Runtime Info"
}
