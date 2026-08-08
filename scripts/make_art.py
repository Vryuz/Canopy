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

import heapq
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
    """Real topographic contour lines.

    Halftoning a raw elevation field just yields noise. Contours have to be drawn as
    *lines*: find where elevation crosses each level, and divide by the local gradient
    so the line keeps an even width instead of ballooning across flat ground.
    """
    elev = fbm((h, w), octaves=5, freq=150)
    levels = elev * 9.0
    gy, gx = np.gradient(levels)
    grad = np.hypot(gx, gy) + 1e-6
    crossing = np.abs(levels - np.round(levels)) / grad
    lines = np.clip(crossing / 0.85, 0, 1)
    # Every fifth contour is an index line, drawn heavier, as on a real map.
    index = (np.round(levels) % 5 == 0)
    lines = np.where(index, np.clip(crossing / 1.6, 0, 1), lines)
    return np.clip(lines, 0, 1)


def field_canopy(w: int = 320, h: int = 240) -> np.ndarray:
    """Individual tree crowns, clustered into stands with clearings between them."""
    img = Image.new("L", (w, h), 255)
    draw = ImageDraw.Draw(img)
    density = fbm((h, w), octaves=4, freq=90)

    for _ in range(1400):
        x, y = int(RNG.integers(0, w)), int(RNG.integers(0, h))
        # Stands cluster where the density field is high; clearings stay open.
        if density[y, x] < 0.44 or RNG.random() > density[y, x]:
            continue
        r = float(RNG.uniform(2.6, 7.0))
        tone = int(RNG.integers(20, 95))
        draw.ellipse([x - r, y - r, x + r, y + r], fill=tone)

    return np.asarray(img.filter(ImageFilter.GaussianBlur(0.6)), np.float32) / 255.0


def _fill_pits(elev: np.ndarray) -> np.ndarray:
    """Priority-flood depression filling.

    Without this, flow terminates in every local minimum and the network comes out as
    scattered fragments. Leaning on a steep regional tilt "fixes" that by making all
    flow run straight downhill — which trades fragments for parallel streaks and still
    isn't a drainage network. Filling the pits is what lets a noise-dominated surface
    (the kind that actually branches) route properly.
    """
    h, w = elev.shape
    filled = elev.copy()
    seen = np.zeros((h, w), bool)
    heap: list[tuple[float, int, int]] = []

    for x in range(w):
        for y in (0, h - 1):
            heapq.heappush(heap, (float(filled[y, x]), y, x))
            seen[y, x] = True
    for y in range(h):
        for x in (0, w - 1):
            if not seen[y, x]:
                heapq.heappush(heap, (float(filled[y, x]), y, x))
                seen[y, x] = True

    while heap:
        e, y, x = heapq.heappop(heap)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and not seen[ny, nx]:
                seen[ny, nx] = True
                # The epsilon keeps a usable gradient across filled flats.
                raised = max(float(filled[ny, nx]), e + 1e-5)
                filled[ny, nx] = raised
                heapq.heappush(heap, (raised, ny, nx))
    return filled


def field_watershed(w: int = 260, h: int = 195) -> np.ndarray:
    """A dendritic channel network from actual flow accumulation.

    Depressions are filled, then water is routed downhill cell by cell (steepest
    descent, highest ground first) and the accumulated flow thresholded. Thresholded
    noise only ever produces blobs; this produces genuine branching drainage.
    """
    elev = fbm((h, w), octaves=6, freq=110)
    tilt = np.linspace(0, 1, h)[:, None]
    # Noise-dominant so tributaries converge; a light tilt just gives an outlet.
    elev = _fill_pits(elev * 0.78 + (1.0 - tilt) * 0.22)

    flat = elev.ravel()
    acc = np.ones(h * w, np.float32)
    order = np.argsort(flat)[::-1]            # drain from the highest ground down
    offsets = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]

    for idx in order:
        y, x = divmod(int(idx), w)
        best, best_elev = -1, flat[idx]
        for dy, dx in offsets:
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w:
                n_idx = ny * w + nx
                if flat[n_idx] < best_elev:
                    best_elev, best = flat[n_idx], n_idx
        if best >= 0:
            acc[best] += acc[idx]

    # Channel width grows with the log of upstream area, as real rivers do.
    # Threshold on catchment size, not on "some flow". At 0.33 of the log range a cell
    # needs only ~38 upstream cells to qualify, which is almost all of them — the frame
    # fills with texture. 0.56 keeps the trunk and its real tributaries.
    strength = np.log1p(acc.reshape(h, w)) / math.log(h * w)
    channels = np.clip((strength - 0.56) * 10.0, 0, 1)
    channels = np.asarray(
        Image.fromarray((channels * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3)),
        np.float32,
    ) / 255.0
    return np.clip(1.0 - channels, 0, 1)


def field_parcels(w: int = 320, h: int = 240) -> np.ndarray:
    """Land division by recursive subdivision — irregular lots, not a uniform lattice."""
    img = Image.new("L", (w, h), 255)
    draw = ImageDraw.Draw(img)

    def split(x0: float, y0: float, x1: float, y1: float, depth: int) -> None:
        bw, bh = x1 - x0, y1 - y0
        if depth == 0 or (bw < 34 and bh < 34) or RNG.random() < 0.12:
            tone = int(RNG.choice([255, 255, 232, 210, 165]))
            draw.rectangle([x0, y0, x1, y1], fill=tone, outline=45, width=1)
            return
        # Split the longer side, off-centre, so lots read as surveyed rather than tiled.
        t = float(RNG.uniform(0.34, 0.66))
        if bw >= bh:
            xm = x0 + bw * t
            split(x0, y0, xm, y1, depth - 1)
            split(xm, y0, x1, y1, depth - 1)
        else:
            ym = y0 + bh * t
            split(x0, y0, x1, ym, depth - 1)
            split(x0, ym, x1, y1, depth - 1)

    split(1, 1, w - 2, h - 2, 5)
    return np.asarray(img, np.float32) / 255.0


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
    # Finer screen on the plates: at cell=5 the dot lattice swallows contour lines and
    # channel threads, which is what made the earlier set read as random noise.
    emit("plate-terrain", field_terrain(), cell=3, scale=5)
    emit("plate-canopy", field_canopy(), cell=3, scale=5)
    emit("plate-watershed", field_watershed(), cell=3, scale=5)
    emit("plate-parcels", field_parcels(), cell=3, scale=5)
    write_logo()


if __name__ == "__main__":
    main()
