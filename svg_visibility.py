"""
SVG Visibility Toggle Node for ComfyUI
Shows or hides SVG elements by selector (adds display:none or removes elements).

Inputs:
- svg_string: SVG XML string
- visibility_rules_json: JSON array of visibility rules
  Example:
  [
    {"selector": "#path0", "visible": true},
    {"selector": ".shadow", "visible": false},
    {"selector": "[id*=bg]", "visible": false}
  ]
- default_visible: Elements not specified in rules default to this
- remove_hidden: If true, remove hidden elements; if false, set display:none

Outputs:
- STRING: Modified SVG XML
- STRING: Meta JSON with visibility changes stats
"""

import json
from typing import List, Dict, Any, Optional
from xml.etree import ElementTree as ET


class SVGVisibility:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "svg_string": ("STRING", {"forceInput": True}),
            },
            "optional": {
                "visibility_rules_json": ("STRING", {
                    "default": "[]",
                    "multiline": True,
                    "tooltip": "Array of {selector, visible} to control element visibility"
                }),
                "default_visible": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Default visibility for elements not specified in rules"
                }),
                "remove_hidden": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "Remove hidden elements from SVG (true) or set display:none (false)"
                }),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("svg", "meta")
    FUNCTION = "toggle_visibility"
    CATEGORY = "TJ_Vector"

    def toggle_visibility(self, 
                          svg_string: str, 
                          visibility_rules_json: str = "[]",
                          default_visible: bool = True,
                          remove_hidden: bool = False):
        # Parse SVG
        try:
            root = ET.fromstring(svg_string)
        except Exception as e:
            return (svg_string, json.dumps({"error": f"SVG parse error: {e}"}))

        # Parse rules
        rules: List[Dict[str, Any]] = []
        try:
            rules = json.loads(visibility_rules_json)
            if not isinstance(rules, list):
                rules = []
        except Exception:
            rules = []

        # Build visibility map: element -> visible (bool)
        visibility_map: Dict[ET.Element, bool] = {}
        
        for rule in rules:
            selector = str(rule.get("selector", "")).strip()
            visible = bool(rule.get("visible", True))
            if not selector:
                continue
            
            # Find matching elements
            matched = self._find_elements_by_selector(root, selector)
            for elem in matched:
                visibility_map[elem] = visible

        stats = {
            "hidden": 0,
            "shown": 0,
            "removed": 0,
            "display_none": 0
        }

        # Apply visibility changes
        elements_to_remove = []
        
        for elem in root.iter():
            # Skip root
            if elem == root:
                continue
            
            # Determine visibility
            if elem in visibility_map:
                visible = visibility_map[elem]
            else:
                visible = default_visible
            
            if not visible:
                stats["hidden"] += 1
                if remove_hidden:
                    # Mark for removal (can't remove during iteration)
                    elements_to_remove.append(elem)
                    stats["removed"] += 1
                else:
                    # Set display:none
                    elem.set("display", "none")
                    stats["display_none"] += 1
            else:
                stats["shown"] += 1
                # Remove display:none if present
                if elem.get("display") == "none":
                    del elem.attrib["display"]

        # Remove hidden elements if requested
        if remove_hidden and elements_to_remove:
            # Find parents and remove children
            parent_map = {c: p for p in root.iter() for c in p}
            for elem in elements_to_remove:
                parent = parent_map.get(elem)
                if parent is not None:
                    parent.remove(elem)

        # Convert back to string
        output_svg = ET.tostring(root, encoding="unicode")
        
        return (output_svg, json.dumps(stats, indent=2))

    def _find_elements_by_selector(self, root: ET.Element, selector: str) -> List[ET.Element]:
        """Find all elements matching a simple selector"""
        results = []
        s = selector.strip()
        
        # ID selector: #id
        if s.startswith("#"):
            target_id = s[1:]
            for elem in root.iter():
                if elem.get("id") == target_id:
                    results.append(elem)
        
        # Class selector: .class
        elif s.startswith("."):
            target_class = s[1:]
            for elem in root.iter():
                classes = (elem.get("class") or "").split()
                if target_class in classes:
                    results.append(elem)
        
        # Tag selector: g, path, etc.
        elif s in ["g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text"]:
            ns_tag = f"{{http://www.w3.org/2000/svg}}{s}"
            for elem in root.iter():
                if elem.tag == ns_tag or elem.tag == s or elem.tag.endswith(f'}}{s}'):
                    results.append(elem)
        
        # Attribute contains selector: [attr*=value]
        elif s.startswith("[") and s.endswith("]") and "*=" in s:
            attr_part = s[1:-1]
            attr_name, attr_value = attr_part.split("*=", 1)
            attr_name = attr_name.strip()
            attr_value = attr_value.strip().strip('"').strip("'")
            for elem in root.iter():
                elem_value = elem.get(attr_name, "")
                if attr_value in elem_value:
                    results.append(elem)
        
        # Attribute equals selector: [attr=value]
        elif s.startswith("[") and s.endswith("]") and "=" in s and "*=" not in s:
            attr_part = s[1:-1]
            attr_name, attr_value = attr_part.split("=", 1)
            attr_name = attr_name.strip()
            attr_value = attr_value.strip().strip('"').strip("'")
            for elem in root.iter():
                if elem.get(attr_name) == attr_value:
                    results.append(elem)
        
        return results


NODE_CLASS_MAPPINGS = {
    "SVGVisibility": SVGVisibility,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SVGVisibility": "SVG Visibility Toggle",
}
