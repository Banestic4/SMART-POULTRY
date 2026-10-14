"""Layout B: ESP32 NOT plugged into the breadboard (female-to-male Dupont wires).
Shows which breadboard hole each wire's MALE end goes into and which pin its FEMALE end goes on."""
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch, Rectangle

Y = {"a": 14, "b": 13, "c": 12, "d": 11, "e": 10}
COL = {"3v3": "#ef7d00", "gnd": "#111111", "d4": "#16a34a", "d34": "#8b3fd1", "5v": "#d00000", "ao": "#8b3fd1"}
INK = "#1c2a22"


def build(stage, out):
    fig, ax = plt.subplots(figsize=(15, 9.5))
    ax.set_xlim(-4, 36); ax.set_ylim(-9.5 if stage == 2 else -4.5, 27); ax.set_aspect("equal"); ax.axis("off")
    # breadboard (top half only)
    ax.add_patch(FancyBboxPatch((0, 8.2), 24.5, 7.4, boxstyle="round,pad=0.2", fc="#ecebe4", ec="#9a998f", lw=1.5, zorder=0))
    ax.add_patch(Rectangle((0.3, 8.35), 23.9, 0.9, fc="#d9d8cf", ec="none", zorder=1))
    for c in range(1, 24):
        for r, y in Y.items():
            ax.plot(c, y, "s", ms=4, color="#6b6a62", zorder=2)
        ax.text(c, 8.8, str(c), ha="center", va="center", fontsize=8, color="#444", zorder=2)
    for r, y in Y.items():
        ax.text(-0.7, y, r, ha="center", va="center", fontsize=9, color="#444")
    ax.text(12, 7.3, "(only the upper half of the breadboard is used; the lower half stays empty)", ha="center", fontsize=9, style="italic", color="#666")

    def tag(n, x, y, r=0.8):
        ax.add_patch(Circle((x, y), r, fc="#fde047", ec="#111", lw=1.4, zorder=12))
        ax.text(x, y, str(n), ha="center", va="center", fontsize=10 if r > 0.7 else 8, fontweight="bold", zorder=13)

    def stub(hole, color, label, n, top, diag=False, left=False):
        """Male end in `hole`; wire runs straight up (b-row wires hop one strip right); female end goes on `label` pin."""
        x, y = hole
        xs = x + (1 if diag else 0)
        pts = [(x, y), (xs, y + 1.3), (xs, top - 0.7)] if diag else [(x, y), (xs, top - 0.7)]
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color=color, lw=3.4, solid_capstyle="round", zorder=6)
        ax.plot(x, y, "o", color=color, ms=7, zorder=7)
        ax.text(xs + (-0.42 if left else 0.42), (y + 1.6 + top - 0.8) / 2 + 0.2, label, rotation=90, ha="center", va="center",
                fontsize=9.5, fontweight="bold", color=color, zorder=9)
        tag(n, xs, top)

    def resistor(p0, p1, label, fc="#e8c98a", stand=False):
        (x0, y0), (x1, y1) = p0, p1
        if stand:
            ax.plot([x0, x0], [y0, y0 + 0.9], color="#777", lw=2, zorder=5); ax.plot([x1, x1], [y1, y1 + 0.9], color="#777", lw=2, zorder=5)
            ax.add_patch(Rectangle((x0 - 0.3, y0 + 0.9), 1.6, 1.05, fc=fc, ec="#111", lw=1.2, zorder=7))
            ax.text(x0 + 0.5, y0 + 1.42, label, ha="center", va="center", fontsize=6.5, fontweight="bold", zorder=8)
            return
        ax.plot([x0, x1], [y0, y1], color="#888", lw=2, zorder=5)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        ax.add_patch(Rectangle((cx - 1.0, cy - 0.42), 2.0, 0.84, fc=fc, ec="#111", lw=1.2, zorder=7))
        ax.text(cx, cy, label, ha="center", va="center", fontsize=8, fontweight="bold", zorder=8)
        for p in (p0, p1): ax.plot(*p, "o", color="#666", ms=5, zorder=8)

    # DHT22 in strips 8-11, row e
    ax.add_patch(Rectangle((6.6, 9.3), 5.8, 2.15, fc="#fff3b0", ec="#7a6a00", lw=1.5, zorder=4))
    for k, x in enumerate((8, 9, 10, 11)):
        ax.plot(x, 10, "s", ms=6, color="#7a6a00", zorder=5)
        ax.text(x, 10.9, str(k + 1), ha="center", va="center", fontsize=8.5, fontweight="bold", zorder=6)
    ax.text(5.9, 10.6, "DHT22", ha="right", va="center", fontsize=10, fontweight="bold", color="#7a6a00")
    ax.text(9.5, 6.3 + 0.0, "", fontsize=1)
    ax.text(0, 5.9, "DHT22 (grille facing you, pins down): 1 = VCC, 2 = DATA, 3 = not used, 4 = GND",
            fontsize=10, color="#7a6a00", fontweight="bold", va="center")

    # ---- Stage 1 ----
    stub((8, Y["a"]), COL["3v3"], "ESP32 3V3", 1, 20.2)
    stub((11, Y["a"]), COL["gnd"], "ESP32 GND", 2, 20.2)
    stub((9, Y["a"]), COL["d4"], "ESP32 D4", 3, 21.8)
    ax.add_patch(Rectangle((7.75, 12.7), 1.5, 0.6, fc="#e8c98a", ec="#111", lw=1.2, zorder=7))
    tag(4, 8.5, 13.0, r=0.55)

    steps = [
        "1  Wire: male end in hole a8,  female end on ESP32 pin 3V3        (3.3V to the DHT22 VCC strip)",
        "2  Wire: male end in hole a11, female end on ESP32 pin GND       (the shared GND strip)",
        "3  Wire: male end in hole a9,  female end on ESP32 pin D4 (GPIO4)  (DHT22 DATA)",
        "4  10k resistor STANDING UPRIGHT, one leg in b8 and one in b9      (pull-up: DATA to 3V3; bend the legs 1 hole apart)",
    ]
    title = "LAYOUT B  -  STAGE 1 : ESP32 + DHT22  (ESP32 NOT on the breadboard)"

    if stage == 2:
        # 5V strip 14, divider strips 3 / 7 / 11
        stub((14, Y["a"]), COL["5v"], "ESP32 VIN", 5, 20.2)
        stub((14, Y["b"]), COL["5v"], "MQ135 VCC", 6, 21.8, diag=True)
        stub((11, Y["b"]), COL["gnd"], "MQ135 GND", 7, 21.8, diag=True)
        stub((3, Y["a"]), COL["ao"], "MQ135 AO", 8, 20.2)
        resistor((3, Y["b"]), (7, Y["b"]), "10k")
        tag(9, 5.0, 13.95, r=0.55)
        resistor((7, Y["c"]), (11, Y["c"]), "15k", fc="#d9c8f0")
        tag(10, 12.5, 12.0, r=0.55)
        stub((7, Y["a"]), COL["d34"], "ESP32 D34", 11, 22.4, left=True)
        steps += [
            "5  Wire: male end in hole a14, female end on ESP32 pin VIN (5V)     (the ONLY 5V wire)",
            "6  Wire: male end in hole b14, female end on MQ135 pin VCC          (5V strip: 5 and 6 share strip 14)",
            "7  Wire: male end in hole b11, female end on MQ135 pin GND          (shares the GND strip with wire 2)",
            "8  Wire: male end in hole a3,  female end on MQ135 pin AO           (gas signal in)",
            "9  10k resistor from hole b3 to hole b7                             (top of the divider)",
            "10 15k resistor from hole c7 to hole c11                            (bottom of the divider, to GND)",
            "11 Wire: male end in hole a7,  female end on ESP32 pin D34 (GPIO34)  (middle of the divider: strip 7)",
        ]
        title = "LAYOUT B  -  STAGE 2 : full circuit  (wires 1-4 from stage 1 stay in place)"
    ax.set_title(title, fontsize=14, fontweight="bold", loc="left", pad=6)
    for k, s in enumerate(steps):
        ax.text(-3.5, 4.2 - k * 1.05 if stage == 1 else 4.2 - k * 1.05, s, fontsize=9.6, va="center", family="DejaVu Sans Mono")
    ax.text(-3.5, 26.2, "Find each ESP32 / MQ135 pin by the LABEL printed on the board. Yellow numbers match the steps below.",
            fontsize=9.5, style="italic", color="#a00")
    fig.tight_layout(); fig.savefig(out, dpi=135); plt.close(fig)


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "."
    build(1, f"{base}/layoutB_stage1_dht22.png")
    build(2, f"{base}/layoutB_stage2_full.png")
    print("ok")
