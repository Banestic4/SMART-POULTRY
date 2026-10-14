"""Draw breadboard wiring pictures for SMART-Poultry (stage 1 = DHT22, stage 2 = everything)."""
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch, Rectangle
from matplotlib.path import Path
from matplotlib.patches import PathPatch

ROWY = {"a": 14, "b": 13, "c": 12, "d": 11, "e": 10, "f": 7, "g": 6, "h": 5, "i": 4, "j": 3}
RAIL = {"top3v3": 18, "topgnd": 17, "botgnd": 0, "bot_unused": -1}
COL = {"3v3": "#ef7d00", "5v": "#d00000", "gnd": "#111111", "data": "#16a34a", "ao": "#8b3fd1"}
INK = "#1c2a22"


def build(stage, out):
    fig, ax = plt.subplots(figsize=(17, 10.2))
    ax.set_xlim(-6, 52); ax.set_ylim(-34 if stage == 2 else -18, 26); ax.set_aspect("equal"); ax.axis("off")

    # ---- breadboard body ----
    ax.add_patch(FancyBboxPatch((0, -2), 45.5, 21.5, boxstyle="round,pad=0.2", fc="#ecebe4", ec="#9a998f", lw=1.5, zorder=0))
    ax.add_patch(Rectangle((0.3, 8.1), 44.9, 0.9, fc="#d9d8cf", ec="none", zorder=1))      # centre gap
    ax.add_patch(Rectangle((0.3, 17.6), 44.9, 0.0, fc="none"))
    ax.plot([0.5, 44.9], [18.6, 18.6], color="#d62828", lw=2, zorder=1)                    # red stripe (top)
    ax.plot([0.5, 44.9], [16.4, 16.4], color="#1d4ed8", lw=2, zorder=1)                    # blue stripe (top)
    ax.plot([0.5, 44.9], [0.6, 0.6], color="#1d4ed8", lw=2, zorder=1)                      # blue stripe (bottom)
    ax.plot([0.5, 44.9], [-1.6, -1.6], color="#d62828", lw=2, zorder=1)                    # red stripe (bottom)
    for c in range(1, 45):
        for r, y in ROWY.items():
            ax.plot(c, y, "s", ms=3.2, color="#6b6a62", zorder=2)
        for y in RAIL.values():
            ax.plot(c, y, "s", ms=3.2, color="#6b6a62", zorder=2)
        ax.text(c, 8.5, str(c), ha="center", va="center", fontsize=6.3, color="#444", zorder=2)
    for r, y in ROWY.items():
        ax.text(-0.6, y, r, ha="center", va="center", fontsize=8, color="#444")
    ax.text(-1.4, 18, "+  3V3 rail", ha="right", va="center", fontsize=9, color="#d62828", fontweight="bold")
    ax.text(-1.4, 17, "-  GND rail", ha="right", va="center", fontsize=9, color="#1d4ed8", fontweight="bold")
    ax.text(-1.4, 0, "-  GND rail", ha="right", va="center", fontsize=9, color="#1d4ed8", fontweight="bold")
    ax.text(-1.4, -1, "+  (not used)", ha="right", va="center", fontsize=9, color="#999")
    ax.text(22, 8.5, "", fontsize=1)

    # ---- helpers ----
    def P(col, row): return (col, ROWY[row])

    def wire(p0, p1, color, ctrl=None, lw=3.0, z=6):
        if ctrl is None:
            verts, codes = [p0, p1], [Path.MOVETO, Path.LINETO]
        else:
            verts, codes = [p0, ctrl, p1], [Path.MOVETO, Path.CURVE3, Path.CURVE3]
        ax.add_patch(PathPatch(Path(verts, codes), fc="none", ec=color, lw=lw, capstyle="round", zorder=z))
        for p in (p0, p1):
            ax.plot(*p, "o", color=color, ms=6, zorder=z + 1)

    def tag(n, x, y):
        ax.add_patch(Circle((x, y), 0.95, fc="#fde047", ec="#111", lw=1.4, zorder=12))
        ax.text(x, y, str(n), ha="center", va="center", fontsize=10.5, fontweight="bold", zorder=13)

    def resistor(p0, p1, label, fc="#e8c98a"):
        (x0, y0), (x1, y1) = p0, p1
        ax.plot([x0, x1], [y0, y1], color="#888", lw=2, zorder=5)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        ax.add_patch(Rectangle((cx - 1.15, cy - 0.5), 2.3, 1.0, fc=fc, ec="#111", lw=1.2, zorder=7))
        ax.text(cx, cy, label, ha="center", va="center", fontsize=8, fontweight="bold", zorder=8)
        for p in (p0, p1): ax.plot(*p, "o", color="#666", ms=5, zorder=8)

    # ---- ESP32 (30-pin DevKit V1 style, USB to the right) ----
    ax.add_patch(Rectangle((28.4, 4.6), 15.2, 7.8, fc="#1f3b57", ec="#0b1b2b", lw=1.5, zorder=4))
    ax.add_patch(Rectangle((43.6, 6.8), 3.0, 3.4, fc="#c9c9c9", ec="#555", lw=1.2, zorder=4))
    ax.text(45.1, 8.5, "USB", ha="center", va="center", fontsize=8, fontweight="bold", zorder=5)
    ax.text(35.5, 8.5, "ESP32 DevKit  (top view)", ha="center", va="center", fontsize=10, color="white", fontweight="bold", zorder=5)
    top = ["D23", "D22", "TX0", "RX0", "D21", "D19", "D18", "D5", "D17", "D16", "D4", "D2", "D15", "GND", "3V3"]
    bot = ["EN", "VP", "VN", "D34", "D35", "D32", "D33", "D25", "D26", "D27", "D14", "D12", "D13", "GND", "VIN"]
    used_top = {"D4": "#16a34a", "GND": "#111", "3V3": "#ef7d00"}
    used_bot = {"D34": "#8b3fd1", "GND": "#111", "VIN": "#d00000"} if stage == 2 else {}
    for i, name in enumerate(top):
        x = 29 + i; c = used_top.get(name)
        ax.plot(x, 13, "s", ms=5, color="#d4af37", zorder=5)
        ax.text(x, 12.2, name, rotation=90, ha="center", va="top", fontsize=7.5, color="white", zorder=5,
                fontweight="bold" if c else "normal")
        if c: ax.add_patch(Circle((x, 13), 0.55, fc="none", ec=c, lw=2.2, zorder=6))
    for i, name in enumerate(bot):
        x = 29 + i; c = used_bot.get(name)
        ax.plot(x, 4, "s", ms=5, color="#d4af37", zorder=5)
        ax.text(x, 4.8, name, rotation=90, ha="center", va="bottom", fontsize=7.5, color="white", zorder=5,
                fontweight="bold" if c else "normal")
        if c: ax.add_patch(Circle((x, 4), 0.55, fc="none", ec=c, lw=2.2, zorder=6))

    # ---- DHT22 plugged into strips 8-11, row e ----
    ax.add_patch(Rectangle((6.6, 9.3), 5.8, 2.5, fc="#fff3b0", ec="#7a6a00", lw=1.5, zorder=4))
    for k, x in enumerate((8, 9, 10, 11)):
        ax.plot(x, 10, "s", ms=5, color="#7a6a00", zorder=5)
        ax.text(x, 10.9, str(k + 1), ha="center", va="center", fontsize=8, fontweight="bold", zorder=6)
    ax.text(9.5, 11.75, "", fontsize=1)
    ax.text(9.5, 19.9 + 2.2, "DHT22: grille facing you, pins down.  1=VCC  2=DATA  3=not used  4=GND",
            ha="center", fontsize=9.5, color="#7a6a00", fontweight="bold")
    ax.text(5.3, 10.6, "DHT22", ha="right", va="center", fontsize=9, fontweight="bold", color="#7a6a00")

    # ---- Stage 1 wires ----
    wire(P(43, "a"), (43, RAIL["top3v3"]), COL["3v3"]);                   tag(1, 44.2, 15.6)
    wire(P(42, "a"), (42, RAIL["topgnd"]), COL["gnd"]);                   tag(2, 40.7, 15.6)
    wire(P(8, "b"), (8, RAIL["top3v3"]), COL["3v3"]);                     tag(3, 6.6, 15.4)
    wire(P(11, "b"), (11, RAIL["topgnd"]), COL["gnd"]);                   tag(4, 12.5, 15.4)
    wire(P(9, "a"), P(39, "a"), COL["data"], ctrl=(24, 29), lw=3.0);      tag(5, 24, 23.2)
    resistor(P(9, "c"), P(13, "c"), "10k");                                tag(6, 14.9, 12.0)
    wire(P(13, "b"), (13, RAIL["top3v3"]), COL["3v3"]);                   tag(7, 14.6, 15.4)

    steps = [
        "1  ESP32 pin 3V3  ->  RED rail (top)",
        "2  ESP32 GND (top row)  ->  BLUE rail (top)",
        "3  DHT22 pin 1 (VCC), strip 8  ->  RED rail",
        "4  DHT22 pin 4 (GND), strip 11  ->  BLUE rail",
        "5  DHT22 pin 2 (DATA), strip 9  ->  ESP32 pin D4 (GPIO4)",
        "6  10k resistor from strip 9 to strip 13 (DATA to the pull-up strip)",
        "7  Strip 13  ->  RED rail (completes the pull-up to 3V3)",
    ]
    colour = "STAGE 1 : ESP32 + DHT22 (test this before adding the gas sensor)"

    if stage == 2:
        # bottom blue rail to ESP32 GND, MQ135 off-board, divider
        wire(P(42, "j"), (42, RAIL["botgnd"]), COL["gnd"]);               tag(8, 40.7, 1.9)
        # MQ135 module drawn below the board (pin order here: AO DO GND VCC - yours may differ)
        ax.add_patch(Rectangle((17, -14.5), 10, 7.2, fc="#2a5aa0", ec="#10305e", lw=1.5, zorder=4))
        ax.add_patch(Circle((22, -11.5), 1.8, fc="#c9c9c9", ec="#333", lw=1.2, zorder=5))
        ax.text(22, -11.5, "MQ135", ha="center", va="center", fontsize=7.5, zorder=6, fontweight="bold")
        ax.text(22, -16.2, "MQ135 module: your pin ORDER may differ, read the labels on it",
                ha="center", fontsize=9.5, color="#10305e", fontweight="bold")
        mq_x = {"AO": 19, "DO": 21, "GND": 23, "VCC": 25}
        for n, x in mq_x.items():
            ax.plot(x, -7.3, "s", ms=6, color="#d4af37", zorder=6)
            ax.text(x, -8.1, n, ha="center", va="top", fontsize=8.5, color="white", fontweight="bold", zorder=6)
        ax.text(21, -6.2, "x", ha="center", fontsize=11, color="#c00", fontweight="bold")
        ax.text(21, -5.2, "DO: leave empty", ha="center", fontsize=8, color="#555")
        wire((25, -7.3), P(43, "j"), COL["5v"], ctrl=(44, -13), lw=3.0);        tag(9, 39.5, -9.2)
        wire((23, -7.3), (23, RAIL["botgnd"]), COL["gnd"]);                     tag(10, 24.4, -3.6)
        wire((19, -7.3), P(17, "j"), COL["ao"]);                                tag(11, 16.6, -3.6)
        resistor(P(17, "h"), P(21, "h"), "10k");                                tag(12, 19, 7.1)
        resistor(P(21, "g"), P(25, "g"), "15k", fc="#d9c8f0");                  tag(13, 23, 7.75)
        wire(P(25, "i"), (25, RAIL["botgnd"]), COL["gnd"]);                     tag(14, 26.2, 1.9)
        wire(P(21, "j"), P(32, "j"), COL["ao"], ctrl=(26.5, -1.2));             tag(15, 28.6, 1.9)
        steps += [
            "8  ESP32 GND (bottom row)  ->  BLUE rail (bottom)",
            "9  MQ135 VCC  ->  ESP32 pin VIN (5V)   [RED wire: the only 5V wire]",
            "10 MQ135 GND  ->  BLUE rail (bottom)",
            "11 MQ135 AO  ->  strip 17",
            "12 10k resistor from strip 17 to strip 21",
            "13 15k resistor from strip 21 to strip 25",
            "14 Strip 25  ->  BLUE rail (bottom)",
            "15 Strip 21 (middle of the divider)  ->  ESP32 pin D34 (GPIO34)",
        ]
        colour = "STAGE 2 : full circuit (stage 1 wires 1-7 stay in place)"

    ax.set_title(colour, fontsize=15, fontweight="bold", loc="left", pad=4)
    # step list
    n = len(steps); cols = 2 if n > 9 else 1; per = (n + cols - 1) // cols
    for k, s in enumerate(steps):
        cx = -5.5 + (k // per) * 30; cy = -20.5 - (k % per) * 1.75 if stage == 2 else -6.5 - (k % per) * 1.7
        ax.text(cx, cy, s, fontsize=10.2, va="center", family="DejaVu Sans")
    ax.text(-5.5, 24.9 + 0.2, "Pin POSITIONS shown are for the common 30-pin ESP32 DevKit V1 with USB on the right. "
            "If yours differs, match by the printed LABEL, not by position.", fontsize=9, style="italic", color="#a00")
    fig.tight_layout(); fig.savefig(out, dpi=135); plt.close(fig)


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "."
    build(1, f"{base}/breadboard_stage1_dht22.png")
    build(2, f"{base}/breadboard_stage2_full.png")
    print("ok")

