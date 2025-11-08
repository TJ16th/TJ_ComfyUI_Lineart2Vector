"""
SVG File Saver Node for ComfyUI
Saves SVG strings to files
"""

import os
import json
from datetime import datetime


class SVGFileSaver:
    """
    Saves SVG strings to files
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "svg_string": ("STRING", {"forceInput": True}),
                "filename_prefix": ("STRING", {"default": "centerline"}),
                "output_path": ("STRING", {"default": "output/svg"}),
            },
            "optional": {
                "auto_timestamp": ("BOOLEAN", {"default": True}),
                "overwrite": ("BOOLEAN", {"default": False}),
            }
        }
    
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("file_path",)
    FUNCTION = "save_svg"
    CATEGORY = "TJ_Vector"
    OUTPUT_NODE = True
    
    def save_svg(self, svg_string, filename_prefix="centerline", 
                output_path="output/svg", auto_timestamp=True, overwrite=False):
        """
        Save SVG string to file
        """
        # Create output directory if it doesn't exist
        os.makedirs(output_path, exist_ok=True)
        
        # Generate filename
        if auto_timestamp:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{filename_prefix}_{timestamp}.svg"
        else:
            filename = f"{filename_prefix}.svg"
        
        filepath = os.path.join(output_path, filename)
        
        # Check if file exists and handle overwrite
        if os.path.exists(filepath) and not overwrite:
            # Add counter to filename
            counter = 1
            base_name = filename[:-4]  # Remove .svg
            while os.path.exists(filepath):
                filename = f"{base_name}_{counter}.svg"
                filepath = os.path.join(output_path, filename)
                counter += 1
        
        # Save SVG file
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(svg_string)
            
            print(f"SVG saved to: {filepath}")
            return (filepath,)
        
        except Exception as e:
            print(f"Error saving SVG: {e}")
            return ("",)


class SVGBatchSaver:
    """
    Saves multiple SVG files with metadata
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "svg_string": ("STRING", {"forceInput": True}),
                "filename_prefix": ("STRING", {"default": "centerline"}),
                "output_path": ("STRING", {"default": "output/svg"}),
            },
            "optional": {
                "statistics": ("STRING", {"default": ""}),
                "color_info": ("STRING", {"default": ""}),
                "save_metadata": ("BOOLEAN", {"default": True}),
            }
        }
    
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("svg_path", "metadata_path")
    FUNCTION = "save_svg_batch"
    CATEGORY = "TJ_Vector"
    OUTPUT_NODE = True
    
    def save_svg_batch(self, svg_string, filename_prefix="centerline",
                      output_path="output/svg", statistics="", 
                      color_info="", save_metadata=True):
        """
        Save SVG with metadata
        """
        # Create output directory
        os.makedirs(output_path, exist_ok=True)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_filename = f"{filename_prefix}_{timestamp}"
        
        # Save SVG file
        svg_filepath = os.path.join(output_path, f"{base_filename}.svg")
        try:
            with open(svg_filepath, 'w', encoding='utf-8') as f:
                f.write(svg_string)
            print(f"SVG saved to: {svg_filepath}")
        except Exception as e:
            print(f"Error saving SVG: {e}")
            return ("", "")
        
        # Save metadata if requested
        metadata_filepath = ""
        if save_metadata:
            metadata = {
                "timestamp": timestamp,
                "svg_file": f"{base_filename}.svg",
                "statistics": {},
                "color_info": {}
            }
            
            # Parse statistics JSON
            if statistics:
                try:
                    metadata["statistics"] = json.loads(statistics)
                except:
                    metadata["statistics"] = {"raw": statistics}
            
            # Parse color info JSON
            if color_info:
                try:
                    metadata["color_info"] = json.loads(color_info)
                except:
                    metadata["color_info"] = {"raw": color_info}
            
            metadata_filepath = os.path.join(output_path, f"{base_filename}_metadata.json")
            try:
                with open(metadata_filepath, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False)
                print(f"Metadata saved to: {metadata_filepath}")
            except Exception as e:
                print(f"Error saving metadata: {e}")
        
        return (svg_filepath, metadata_filepath)


NODE_CLASS_MAPPINGS = {
    "SVGFileSaver": SVGFileSaver,
    "SVGBatchSaver": SVGBatchSaver
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SVGFileSaver": "SVG File Saver",
    "SVGBatchSaver": "SVG Batch Saver"
}
