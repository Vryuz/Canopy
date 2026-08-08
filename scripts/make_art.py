"""Generate Canopy's halftone artwork and logo.

Original artwork, generated rather than sourced. The reference aesthetic — chunky
dithered dot patterns, a landscape dissolving into paper — is reproduced with a real
halftone screen: one dot per cell, radius tracking local darkness, supersampled so the
dots come out smooth. The fields underneath mean something for Canopy: a forested
horizon, terrain contours, canopy cover, watershed, parcel division.

Run:  python scripts/make_art.py
Out:  web/img/*.png, web/img/logo.svg
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parents[1] / "web" / "img"
RNG = np.random.default_rng(11)


# --------------------------------------------------------------------- noise

def _smooth(shape: tuple[int, int], freq: int) -> np.ndarray:
    gh, gw = max(2, int(shape[0] / freq)), max(2, int(shape[1] / freq))
    grid = RNG.random((gh, gw)).astype(np.float32)
    img = Image.fromarray((grid * 255).astype(np.uint8), "L")
    return np.asarray(img.resize((shape[1], shape[0]), Image.BICUBIC), np.float32) / 255.0


def fbm(shape: tuple[int, int], octaves: int = 5, freq: int = 90) -> np.ndarray:
    total = np.zeros(shape, np.float32)
    amp, f, norm = 1.0, float(freq), 0.0
    for _ in range(octaves):
        total += amp * _smooth(shape, max(2, int(f)))
        norm += amp
        amp *= 0.5
        f /= 2
    out = total / norm
    return (out - out.min()) / (np.ptp(out) + 1e-9)


def ridge_1d(width: int, freq: int, octaves: int = 5) -> np.ndarray:
    """A 1-D fractal skyline — one mountain/tree ridge.

    Note the inversion: `freq` is a wavelength, not a count. It sets the spacing
    between lattice points, so a LARGER value means FEWER, BIGGER landforms
    (freq=220 → ~19 peaks; freq=8 → ~300, which is noise, not terrain).
    """
    total = np.zeros(width, np.float32)
    amp, f, norm = 1.0, float(freq), 0.0
    for _ in range(octaves):
        n = max(2, int(width / f))
        pts = RNG.random(n).astype(np.float32)
        total += amp * np.interp(np.linspace(0, n - 1, width), np.arange(n), pts)
        norm += amp
        amp *= 0.5
        f /= 2
    out = total / norm
    return (out - out.min()) / (np.ptp(out) + 1e-9)


# ------------------------------------------------------------------- fields
# Every field returns float [0,1] where 0 = ink, 1 = paper.

def field_horizon(w: int = 1500, h: int = 620) -> np.ndarray:
    """A forested horizon receding into haze — the hero plate.

    Built like a screen print: each ridge is a *flat* tone painted over the one
    behind it, so the silhouettes stay crisp. Blending the layers instead (a
    depth gradient, or np.minimum) collapses the whole thing into one wash with
    no readable landforms.
    """
    field = np.ones((h, w), np.float32)
    yy = np.arange(h)[:, None]

    # Amplitude must exceed the spacing between crests, or each band is just a
    # near-horizontal stripe and the stack reads as a gradient. Big amplitudes let
    # near peaks rise into the far layers, which is what makes ridges interlock.
    layers = [
        # (crest y fraction, ridge amplitude, ink darkness, ridge wavelength)
        (0.42, 0.150, 0.12, 260),
        (0.53, 0.175, 0.27, 190),
        (0.64, 0.195, 0.45, 140),
        (0.76, 0.150, 0.63, 100),
    ]
    for frac, amp, dark, wavelength in layers:
        crest = (frac - ridge_1d(w, wavelength) * amp) * h
        field = np.where(yy >= crest[None, :], 1.0 - dark, field)
        # Mist pooling just under each crest. Without this separation the bands sit
        # tone-against-tone and the ridges behind read as one mass.
        mist = (yy >= crest[None, :]) & (yy < crest[None, :] + h * 0.045)
        field = np.where(mist, 1.0 - dark * 0.30, field)

    # Front tree line: individual crowns breaking the silhouette.
    crowns = fbm((h, w), octaves=5, freq=26)
    tree_crest = (0.865 - ridge_1d(w, 70) * 0.055) * h
    crown_band = (yy >= tree_crest[None, :] - h * 0.085) & (yy < tree_crest[None, :])
    field = np.where(crown_band & (crowns > 0.50), 0.18, field)
    field = np.where(yy >= tree_crest[None, :], 0.18, field)

    # Foreground floor, densest at the very bottom edge.
    field = np.where(yy >= 0.93 * h, 0.06, field)

    # No positional haze gradient here on purpose: depth is already carried by each
    # layer's ink weight, and a vertical fade across the same band irons the tonal
    # steps back into one smooth ramp — which is what kills the landforms. The only
    # softening is a short dissolve just above the furthest crest, so the plate meets
    # the paper without a hard line.
    top = 0.27 * h
    dissolve = np.clip((yy - (top - h * 0.05)) / (h * 0.05), 0, 1)
    field = 1.0 - (1.0 - field) * dissolve
    return np.clip(field, 0, 1)


def field_terrain(w: int = 320, h: int = 240) -> np.ndarray:
    """Topographic contour bands."""
    elev = fbm((h, w), 5, 110)
    bands = np.sin(elev * math.pi * 14.0)
    contours = 1.0 - np.clip(1.0 - np.abs(bands) * 4.5, 0, 1)
    return np.clip(contours * 0.75 + elev * 0.45, 0, 1)


def field_canopy(w: int = 320, h: int = 240) -> np.ndarray:
    """Tree-crown cover with open gaps."""
    base = fbm((h, w), 6, 48)
    crowns = np.clip((base - 0.42) * 3.2, 0, 1)
    return np.clip(1.0 - crowns * 0.88, 0, 1)


def field_watershed(w: int = 320, h: int = 240) -> np.ndarray:
    """Ridged noise — the branching channels of a drainage basin."""
    n = fbm((h, w), 6, 120)
    ridged = 1.0 - np.abs(n * 2.0 - 1.0)
    return np.clip(1.0 - np.clip((ridged - 0.62) * 5.0, 0, 1) * 0.95, 0, 1)


def field_parcels(w: int = 320, h: int = 240) -> np.ndarray:
    """Land division — a jittered lattice of parcels at differing tones."""
    out = np.ones((h, w), np.float32)
    tone = fbm((h, w), 3, 70)
    y = 0
    while y < h:
        rh = int(RNG.integers(30, 58))
        x = 0
        while x < w:
            rw = int(RNG.integers(34, 72))
            block = tone[y : y + rh, x : x + rw]
            if block.size:
                v = float(block.mean())
                out[y : y + rh, x : x + rw] = 0.30 if v > 0.62 else 0.68 if v > 0.42 else 1.0
            out[y : y + rh, x : x + 1] = 0.12
            x += rw
        out[y : y + 1, :] = 0.12
        y += rh
    return np.clip(out, 0, 1)


# ------------------------------------------------------------------ halftone

def halftone(field: np.ndarray, cell: int = 5, scale: int = 4, angle: float = 15.0) -> Image.Image:
    """Classic halftone screen, supersampled then downscaled for clean dot edges."""
    h, w = field.shape
    big = Image.new("L", (w * scale, h * scale), 255)
    draw = ImageDraw.Draw(big)

    rad = math.radians(angle)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    max_r = cell * scale * 0.80 / 2
    span = int(max(w, h) / cell) + 4

    for j in range(-span, span * 2):
        for i in range(-span, span * 2):
            u, v = (i + 0.5) * cell, (j + 0.5) * cell
            cx = u * cos_a - v * sin_a
            cy = u * sin_a + v * cos_a
            if not (0 <= cx < w and 0 <= cy < h):
                continue
            x0, y0 = int(cx - cell / 2), int(cy - cell / 2)
            block = field[max(0, y0) : y0 + cell, max(0, x0) : x0 + cell]
            if block.size == 0:
                continue
            r = (1.0 - float(block.mean())) * max_r
            if r < 0.32:
                continue
            px, py = cx * scale, cy * scale
            draw.ellipse([px - r, py - r, px + r, py + r], fill=0)

    return big.resize((w, h), Image.LANCZOS).filter(ImageFilter.SHARPEN)


def emit(name: str, field: np.ndarray, cell: int = 5, scale: int = 4) -> None:
    """Save as RGBA ink-on-transparent so a plate sits on any paper tone."""
    grey = np.asarray(halftone(field, cell=cell, scale=scale).convert("L"), np.uint8)
    rgba = np.zeros((*grey.shape, 4), np.uint8)
    rgba[..., 0:3] = 30                 # ink #1e1e1e
    rgba[..., 3] = 255 - grey           # darkness becomes opacity
    Image.fromarray(rgba, "RGBA").save(OUT / f"{name}.png", optimize=True)
    print(f"  {name}.png  {grey.shape[1]}x{grey.shape[0]}")


# ---------------------------------------------------------------------- logo

def _closed_bezier(points: list[tuple[float, float]]) -> str:
    """Catmull-Rom through the points, emitted as a closed cubic-bezier path."""
    n = len(points)
    d = [f"M{points[0][0]:.2f} {points[0][1]:.2f}"]
    for i in range(n):
        p0, p1 = points[(i - 1) % n], points[i]
        p2, p3 = points[(i + 1) % n], points[(i + 2) % n]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d.append(f"C{c1[0]:.2f} {c1[1]:.2f} {c2[0]:.2f} {c2[1]:.2f} {p2[0]:.2f} {p2[1]:.2f}")
    return " ".join(d) + "Z"


def _contour(cx: float, cy: float, radius: float,
             harmonics: list[tuple[int, float, float]], samples: int = 22) -> str:
    """One elevation contour: a circle perturbed by a couple of low harmonics.

    The irregularity is the whole point — perfectly concentric circles read as a
    bullseye, and offset organic rings read as topography.
    """
    pts = []
    for i in range(samples):
        t = 2 * math.pi * i / samples
        r = radius * (1 + sum(a * math.cos(k * t + p) for k, a, p in harmonics))
        pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
    return _closed_bezier(pts)


# Three receding ridge lines — the hero plate reduced to a mark.
#
# Three prior attempts each failed on association rather than craft, which is the
# thing that actually matters in a logo: overlapping circles read as a cloud (and the
# fill-rule="evenodd" knockout silently did nothing, since even-odd resolves within a
# single path, never across sibling <circle> elements); nested arcs over a dot read as
# an upside-down wifi glyph; concentric contour rings read as topography at 160px but
# collapsed into an eye at 16px. Ridge lines are the brand's own vocabulary, match the
# generated hero landscape, and resemble no existing glyph at any size.
LOGO_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" role="img" '
    'aria-label="Canopy" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round">'
    # Angular, not curved: smooth parallel lines are the water glyph. Two ridges,
    # not three, for the same reason.
    '<path d="M2.5 14.6 7.9 7.2l3.8 4.9 3.5-3.6 6.3 7.2"/>'
    '<path d="M2.5 20.6 8.7 15l3.7 3.4 4.2-3.7 4.9 5.2"/>'
    "</svg>"
)


def write_logo() -> None:
    (OUT / "logo.svg").write_text(LOGO_SVG, encoding="utf-8")
    print("  logo.svg")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print("Generating Canopy artwork:")
    emit("hero-horizon", field_horizon(), cell=6, scale=3)
    emit("plate-terrain", field_terrain())
    emit("plate-canopy", field_canopy())
    emit("plate-watershed", field_watershed())
    emit("plate-parcels", field_parcels())
    write_logo()


if __name__ == "__main__":
    main()
