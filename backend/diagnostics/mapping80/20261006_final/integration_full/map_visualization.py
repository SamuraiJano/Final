"""Colour predicted defects over the original fruit texture; never erase skin."""
import hashlib

import numpy as np


DEFECT_COLOURS = {
    'dark_marking': '#38bdf8',
    'light_brown_discolouration': '#facc15',
    'open_skin': '#ef4444',
    'skin_wrinkling': '#a78bfa',
    'wind_scarring': '#4ade80',
}


def render_defect_overlay(image, observed_mask, defect_masks, opacity=.45):
    """Return a separate tinted image and legend, preserving all input arrays.

    Normal skin stays unchanged. Unobserved pixels are never coloured. When
    labels overlap, small diagonal stripes display each class's own colour.
    The display has no effect on the masks, coverage or grading calculation.
    """
    if image.ndim != 3 or image.shape[2] != 3 or image.dtype != np.uint8:
        raise ValueError('Expected an unsigned-byte BGR fruit image')
    if observed_mask.shape != image.shape[:2] or not 0 < opacity < 1:
        raise ValueError('Invalid observed mask or overlay opacity')
    names = sorted(defect_masks)
    observed = observed_mask > 0
    masks = []
    legend = []
    for name in names:
        if defect_masks[name].shape != observed.shape:
            raise ValueError('Defect mask does not match the fruit image')
        mask = (defect_masks[name] > 0) & observed
        masks.append(mask)
        colour = DEFECT_COLOURS.get(name)
        if colour is None:
            # Keep a new model label's colour stable across fruit and frames.
            colour = '#' + hashlib.sha256(name.encode()).hexdigest()[:6]
        legend.append(dict(name=name, label=name.replace('_', ' ').capitalize(),
                           color=colour, observed_pixels=int(mask.sum())))
    overlay = image.copy()
    if not masks:
        return overlay, legend
    count = np.sum(masks, axis=0)
    y, x = np.indices(observed.shape)
    stripe = ((x + y) // 3) % np.maximum(count, 1)
    rank = np.zeros_like(count)
    for mask, item in zip(masks, legend):
        selected = mask & (rank == stripe)
        hex_colour = item['color'].lstrip('#')
        rgb = np.array([int(hex_colour[i:i+2], 16) for i in (0, 2, 4)])
        tinted = np.rint(image[selected] * (1-opacity) + rgb[::-1] * opacity)
        overlay[selected] = np.clip(tinted, 0, 255).astype(np.uint8)
        rank += mask
    return overlay, legend
