"""
TJ_Vector - ComfyUI Custom Nodes
Line art to vector conversion nodes
"""

from .line_region_detector import NODE_CLASS_MAPPINGS as LINE_NODES, NODE_DISPLAY_NAME_MAPPINGS as LINE_NAMES
from .centerline_to_svg import NODE_CLASS_MAPPINGS as SVG_NODES, NODE_DISPLAY_NAME_MAPPINGS as SVG_NAMES

# Combine all node mappings
NODE_CLASS_MAPPINGS = {
    **LINE_NODES,
    **SVG_NODES
}

NODE_DISPLAY_NAME_MAPPINGS = {
    **LINE_NAMES,
    **SVG_NAMES
}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
