// TJ Color Picker Extension for ComfyUI
// Adds a color widget with live preview for STRING inputs (hex) and patches known color fields.
// Works without executing the node; updates immediately in the UI.

import { app } from "../../scripts/app.js";

app.registerExtension({
  name: "tj.colorpicker",

  // Automatically convert known color fields on our nodes to use the custom widget
  beforeRegisterNodeDef(nodeType, nodeData, app) {
    const targetNodes = new Set([
      // Display names from NODE_DISPLAY_NAME_MAPPINGS
      "SVG To Image", // svg_to_raster (display name)
      "SVGToImage", // legacy/defensive fallback
      "SVGGroupLayout", // svg_group_layout
      "SVG Style Editor (Simple)", // svg_style_editor_simple display name
      "SVG Style Editor", // svg_style_editor
      "SVG Color Picker" // svg_color_picker
    ]);

    const colorFields = new Set([
      // common
      "background_color",
      "override_stroke_color",
      "override_fill_color",
      "control_point_color",
      // color picker node
      "base_color",
      // group layout
      "grid_line_color",
      "label_color",
      "background_stroke_color",
      // style editor simple
      "stroke_color",
      "fill_color"
    ]);

    try {
      const displayName = nodeData?.title || nodeData?.name || "";
      if (!targetNodes.has(displayName)) return;

      const patchSection = (section) => {
        if (!section) return;
        for (const [key, val] of Object.entries(section)) {
          if (!Array.isArray(val) || val.length < 2) continue;
          const [type, extras] = val;
          if (type === "STRING" && colorFields.has(key)) {
            section[key][1] = Object.assign({}, extras || {}, { widget: "tj_color" });
          }
        }
      };

      patchSection(nodeData?.input?.required);
      patchSection(nodeData?.input?.optional);
    } catch (e) {
      console.warn("tj.colorpicker patch error", e);
    }
  },

  // Define the custom widget implementation
  getCustomWidgets(app) {
    return {
      tj_color(node, inputName, inputData) {
        const extras = inputData[1] || {};
        let value = extras.default ?? "";

        // Build container widget (serialized as text)
        const w = node.addWidget("text", inputName, value, (v) => {
          value = v || "";
          updateFromText();
        }, { serialize: true });

        // Create DOM overlay: color input + alpha slider + preview swatch
        // ComfyUI attaches widgets in the right side panel via widget.after
        // We'll attach a small UI row with controls.
        const makeRow = () => {
          if (!w.inputEl) return; // not in side panel yet
          if (w.__tj_row) return; // already built

          const row = document.createElement("div");
          row.style.display = "flex";
          row.style.alignItems = "center";
          row.style.gap = "6px";
          row.style.marginTop = "4px";

          const color = document.createElement("input");
          color.type = "color";
          color.style.width = "32px";
          color.style.height = "24px";
          color.style.padding = "0";
          color.style.border = "none";
          color.style.background = "transparent";

          const alpha = document.createElement("input");
          alpha.type = "range";
          alpha.min = "0";
          alpha.max = "255";
          alpha.step = "1";
          alpha.style.flex = "1";

          const badge = document.createElement("div");
          badge.style.width = "32px";
          badge.style.height = "18px";
          badge.style.border = "1px solid #888";
          badge.style.background = "transparent";
          badge.title = "preview";

          row.appendChild(color);
          row.appendChild(alpha);
          row.appendChild(badge);

          // Insert after the text input element
          w.inputEl.parentElement?.appendChild(row);
          w.__tj_row = row;
          w.__tj_color = color;
          w.__tj_alpha = alpha;
          w.__tj_badge = badge;

          // Wire events
          color.addEventListener("input", () => {
            const rgb = color.value; // #RRGGBB
            const a = Number(alpha.value || "255");
            value = toHexRGBA(rgb, a);
            w.value = value;
            node.setDirtyCanvas(true);
            updateBadge();
          });

          alpha.addEventListener("input", () => {
            const rgb = color.value || "#000000";
            const a = Number(alpha.value || "255");
            value = toHexRGBA(rgb, a);
            w.value = value;
            node.setDirtyCanvas(true);
            updateBadge();
          });

          // Initialize controls from current text
          updateFromText();
        };

        const updateFromText = () => {
          const { rgb, a } = fromHexOrNamed(value);
          if (w.__tj_color) w.__tj_color.value = rgb;
          if (w.__tj_alpha) w.__tj_alpha.value = String(a);
          updateBadge();
        };

        const updateBadge = () => {
          if (!w.__tj_badge) return;
          const { r, g, b, a } = parseRgba(value);
          const bg = `rgba(${r}, ${g}, ${b}, ${a/255})`;
          w.__tj_badge.style.background = bg;
          w.__tj_badge.style.backgroundImage =
            "linear-gradient(45deg,#80808022 25%,transparent 25%),"+
            "linear-gradient(-45deg,#80808022 25%,transparent 25%),"+
            "linear-gradient(45deg,transparent 75%,#80808022 75%),"+
            "linear-gradient(-45deg,transparent 75%,#80808022 75%)";
          w.__tj_badge.style.backgroundSize = "8px 8px";
          w.__tj_badge.style.backgroundPosition = "0 0,0 4px,4px -4px,-4px 0px";
        };

        // Hook when the widget is added to the side panel
        const onAdded = w.onAdd || (()=>{});
        w.onAdd = function() {
          onAdded.apply(this, arguments);
          // delay to ensure inputEl exists
          setTimeout(makeRow, 0);
        };

        return w;
      }
    };
  }
});

// Helpers
function toHexRGBA(rgb, a) {
  // rgb: #RRGGBB, a: 0..255
  const r = parseInt(rgb.slice(1,3),16);
  const g = parseInt(rgb.slice(3,5),16);
  const b = parseInt(rgb.slice(5,7),16);
  const aa = clamp(Math.round(a),0,255);
  return `#${hex2(r)}${hex2(g)}${hex2(b)}${hex2(aa)}`;
}

function fromHexOrNamed(s) {
  const { r,g,b,a } = parseRgba(s);
  return { rgb: `#${hex2(r)}${hex2(g)}${hex2(b)}`, a };
}

function parseRgba(s) {
  if (!s) return { r:0,g:0,b:0,a:255 };
  s = String(s).trim();
  // #RRGGBB or #RRGGBBAA
  if (s.startsWith('#')) {
    if (s.length === 7) {
      return { r:hex(s.slice(1,3)), g:hex(s.slice(3,5)), b:hex(s.slice(5,7)), a:255 };
    } else if (s.length === 9) {
      return { r:hex(s.slice(1,3)), g:hex(s.slice(3,5)), b:hex(s.slice(5,7)), a:hex(s.slice(7,9)) };
    }
  }
  // rgba(r,g,b,a)
  const m = s.match(/rgba?\(([^)]+)\)/i);
  if (m) {
    const parts = m[1].split(',').map(x=>x.trim());
    const r = clamp(parseFloat(parts[0]||'0'),0,255);
    const g = clamp(parseFloat(parts[1]||'0'),0,255);
    const b = clamp(parseFloat(parts[2]||'0'),0,255);
    let a = parts[3]!==undefined ? parseFloat(parts[3]) : 1.0;
    if (a<=1.0) a = Math.round(a*255);
    return { r, g, b, a: clamp(Math.round(a),0,255) };
  }
  // named colors -> let browser parse
  const tmp = document.createElement('div');
  tmp.style.color = s;
  document.body.appendChild(tmp);
  const cs = getComputedStyle(tmp).color; // rgb(r,g,b)
  document.body.removeChild(tmp);
  const m2 = cs.match(/rgb\(([^)]+)\)/i);
  if (m2) {
    const parts = m2[1].split(',').map(x=>parseFloat(x.trim()));
    return { r:parts[0]||0, g:parts[1]||0, b:parts[2]||0, a:255 };
  }
  return { r:0,g:0,b:0,a:255 };
}

function hex2(n){ return n.toString(16).toUpperCase().padStart(2,'0'); }
function hex(s){ return Math.max(0, Math.min(255, parseInt(s,16)||0)); }
function clamp(v,min,max){ return Math.max(min, Math.min(max, v)); }
