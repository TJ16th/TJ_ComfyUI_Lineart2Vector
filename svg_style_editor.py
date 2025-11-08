"""
SVG Style Editor Node for ComfyUI
Modifies stroke color, fill color, and stroke width of selected SVG elements by selector.

Inputs:
- svg_string: SVG XML string
- style_rules_json: JSON array of style override rules
  Example:
  [
    {"selector": "#path0", "stroke": "#FF0000", "stroke_width": 3.0, "fill": "none"},
    {"selector": ".hair", "stroke": "#000080", "fill": "#FFFF00"},
    {"selector": "[id*=eye]", "stroke": "#00FF00"}
  ]

Outputs:
- STRING: Modified SVG XML
- STRING: Meta JSON with applied rules stats
"""

import json
from typing import List, Dict, Any, Optional
from xml.etree import ElementTree as ET


class SVGStyleEditor:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "svg_string": ("STRING", {"forceInput": True}),
            },
            "optional": {
                "style_rules_json": ("STRING", {
                    "default": "[]", 
                    "multiline": True,
                    "tooltip": "Array of {selector, stroke?, fill?, stroke_width?, opacity?}"
                }),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("svg", "meta")
    FUNCTION = "edit_styles"
    CATEGORY = "TJ_Vector"

    def edit_styles(self, svg_string: str, style_rules_json: str = "[]"):
        # Parse SVG
        try:
            root = ET.fromstring(svg_string)
        except Exception as e:
            return (svg_string, json.dumps({"error": f"SVG parse error: {e}"}))

        # Parse rules
        rules: List[Dict[str, Any]] = []
        try:
            rules = json.loads(style_rules_json)
            if not isinstance(rules, list):
                rules = []
        except Exception:
            rules = []

        stats = {"rules": [], "total_modified": 0}
        
        # Apply each rule
        for rule in rules:
            selector = str(rule.get("selector", "")).strip()
            if not selector:
                continue
            
            stroke = rule.get("stroke")
            fill = rule.get("fill")
            stroke_width = rule.get("stroke_width")
            opacity = rule.get("opacity")
            
            modified_count = 0
            
            # Find all matching elements
            for elem in self._find_elements_by_selector(root, selector):
                # Apply style changes
                if stroke is not None:
                    elem.set("stroke", str(stroke))
                if fill is not None:
                    elem.set("fill", str(fill))
                if stroke_width is not None:
                    elem.set("stroke-width", str(stroke_width))
                if opacity is not None:
                    elem.set("opacity", str(opacity))
                modified_count += 1
            
            stats["rules"].append({
                "selector": selector,
                "modified_elements": modified_count
            })
            stats["total_modified"] += modified_count

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
    "SVGStyleEditor": SVGStyleEditor,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SVGStyleEditor": "SVG Style Editor",
}
