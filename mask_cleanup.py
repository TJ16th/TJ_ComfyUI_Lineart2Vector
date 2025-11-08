"""
Mask Cleanup Node for ComfyUI
Removes duplicate lines and cleans up masks before centerline extraction
"""

import numpy as np
import torch
import cv2
from scipy.spatial.distance import cdist
from skimage.morphology import skeletonize, remove_small_objects


class MaskLineCleanup:
    """
    Cleans up line masks by removing duplicate parallel lines
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mask": ("MASK",),
                "cleanup_mode": (["merge_close_lines", "remove_duplicates", "thin_only", "distance_based"],),
                "merge_distance": ("INT", {
                    "default": 3,
                    "min": 1,
                    "max": 20,
                    "step": 1,
                    "tooltip": "Distance threshold for merging parallel lines"
                }),
                "min_component_size": ("INT", {
                    "default": 10,
                    "min": 0,
                    "max": 1000,
                    "step": 1,
                    "tooltip": "Remove components smaller than this (0=disabled)"
                }),
            },
            "optional": {
                "strength": ("FLOAT", {
                    "default": 1.0,
                    "min": 0.1,
                    "max": 3.0,
                    "step": 0.1,
                    "tooltip": "Cleanup strength"
                }),
            }
        }
    
    RETURN_TYPES = ("MASK", "IMAGE")
    RETURN_NAMES = ("cleaned_mask", "preview")
    FUNCTION = "cleanup_mask"
    CATEGORY = "TJ_Vector"
    
    def cleanup_mask(self, mask, cleanup_mode="merge_close_lines", merge_distance=3, 
                    min_component_size=10, strength=1.0):
        """
        Clean up mask by removing duplicate lines
        """
        # Convert mask to numpy
        mask_np = mask[0].cpu().numpy()
        mask_255 = (mask_np * 255).astype(np.uint8)
        
        height, width = mask_255.shape
        
        # Apply cleanup based on mode
        if cleanup_mode == "merge_close_lines":
            cleaned = self._merge_close_lines(mask_255, merge_distance)
        elif cleanup_mode == "remove_duplicates":
            cleaned = self._remove_duplicate_lines(mask_255, merge_distance, strength)
        elif cleanup_mode == "thin_only":
            cleaned = self._thin_lines(mask_255)
        elif cleanup_mode == "distance_based":
            cleaned = self._distance_based_cleanup(mask_255, merge_distance, strength)
        else:
            cleaned = mask_255
        
        # Remove small components
        if min_component_size > 0:
            cleaned = self._remove_small_components(cleaned, min_component_size)
        
        # Create preview
        preview = self._create_preview(mask_255, cleaned, width, height)
        
        # Convert to tensors
        cleaned_tensor = torch.from_numpy(cleaned.astype(np.float32) / 255.0).unsqueeze(0)
        preview_tensor = torch.from_numpy(preview.astype(np.float32) / 255.0).unsqueeze(0)
        
        return (cleaned_tensor, preview_tensor)
    
    def _merge_close_lines(self, mask, distance):
        """
        Merge lines that are close to each other
        """
        # Dilate to merge close lines
        kernel = np.ones((distance * 2 + 1, distance * 2 + 1), np.uint8)
        dilated = cv2.dilate(mask, kernel, iterations=1)
        
        # Thin back to single pixel width
        binary = dilated > 127
        skeleton = skeletonize(binary)
        
        return (skeleton * 255).astype(np.uint8)
    
    def _remove_duplicate_lines(self, mask, distance, strength):
        """
        Remove duplicate parallel lines using contour analysis
        """
        # Find contours
        contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        
        if len(contours) == 0:
            return mask
        
        # Create output mask
        output = np.zeros_like(mask)
        
        # Sort contours by length (keep longer ones)
        contours_with_length = [(c, cv2.arcLength(c, False)) for c in contours]
        contours_with_length.sort(key=lambda x: x[1], reverse=True)
        
        kept_contours = []
        distance_threshold = distance * strength
        
        for contour, length in contours_with_length:
            if length < 5:  # Skip very short contours
                continue
            
            # Check if this contour is too close to any kept contour
            is_duplicate = False
            
            for kept_contour in kept_contours:
                # Sample points from both contours
                if len(contour) > 10:
                    sample_indices = np.linspace(0, len(contour) - 1, 10, dtype=int)
                    sample_points = contour[sample_indices].reshape(-1, 2)
                else:
                    sample_points = contour.reshape(-1, 2)
                
                if len(kept_contour) > 10:
                    kept_sample_indices = np.linspace(0, len(kept_contour) - 1, 10, dtype=int)
                    kept_sample_points = kept_contour[kept_sample_indices].reshape(-1, 2)
                else:
                    kept_sample_points = kept_contour.reshape(-1, 2)
                
                # Calculate minimum distance between contours
                if len(sample_points) > 0 and len(kept_sample_points) > 0:
                    distances = cdist(sample_points, kept_sample_points)
                    min_dist = np.min(distances)
                    
                    if min_dist < distance_threshold:
                        is_duplicate = True
                        break
            
            if not is_duplicate:
                kept_contours.append(contour)
                cv2.drawContours(output, [contour], -1, 255, 1)
        
        return output
    
    def _thin_lines(self, mask):
        """
        Simply thin lines to single pixel width
        """
        binary = mask > 127
        skeleton = skeletonize(binary)
        return (skeleton * 255).astype(np.uint8)
    
    def _distance_based_cleanup(self, mask, distance, strength):
        """
        Use distance transform to find true centerlines and remove duplicates
        """
        # Dilate slightly to merge very close lines
        kernel_size = max(1, int(distance * strength))
        kernel = np.ones((kernel_size * 2 + 1, kernel_size * 2 + 1), np.uint8)
        dilated = cv2.dilate(mask, kernel, iterations=1)
        
        # Apply distance transform
        dist_transform = cv2.distanceTransform(dilated, cv2.DIST_L2, 5)
        
        # Normalize
        if np.max(dist_transform) > 0:
            dist_norm = dist_transform / np.max(dist_transform)
        else:
            return mask
        
        # Find local maxima (ridges) - these are the true centerlines
        kernel = np.ones((3, 3), np.uint8)
        dilated_dist = cv2.dilate(dist_norm, kernel, iterations=1)
        ridge = (dist_norm == dilated_dist) & (dist_norm > 0.05)
        
        # Thin the result
        ridge_binary = ridge.astype(bool)
        skeleton = skeletonize(ridge_binary)
        
        return (skeleton * 255).astype(np.uint8)
    
    def _remove_small_components(self, mask, min_size):
        """
        Remove small connected components
        """
        # Find connected components
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        
        # Create output mask
        output = np.zeros_like(mask)
        
        # Keep components larger than min_size
        for i in range(1, num_labels):  # Skip background (0)
            area = stats[i, cv2.CC_STAT_AREA]
            if area >= min_size:
                output[labels == i] = 255
        
        return output
    
    def _create_preview(self, original, cleaned, width, height):
        """
        Create side-by-side preview of original and cleaned masks
        """
        preview = np.zeros((height, width, 3), dtype=np.uint8)
        
        # Original in red (left half)
        preview[:, :, 0] = original
        
        # Cleaned in green (right half)
        preview[:, :, 1] = cleaned
        
        # Overlap in yellow
        overlap = cv2.bitwise_and(original, cleaned)
        preview[:, :, 2] = 0  # No blue channel
        
        # Make overlap yellow (red + green)
        preview[overlap > 127] = [255, 255, 0]
        
        return preview


NODE_CLASS_MAPPINGS = {
    "MaskLineCleanup": MaskLineCleanup
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MaskLineCleanup": "Mask Line Cleanup"
}
