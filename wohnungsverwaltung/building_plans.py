"""Single-building inventory and approximate outlines from the supplied project plans."""

# Legacy identifiers refer only to the original local development fixtures.
APARTMENTS = (
    ("1.01", "1", 0, "25.27"),
    ("1.02", "2", 0, "39.51"),
    ("1.03", "3", 0, "45.70"),
    ("1.04", "4", 0, "59.56"),
    ("1.05", "5", 0, "40.14"),
    ("2.01", "101", 1, "27.95"),
    ("2.02", "102", 1, "30.74"),
    ("2.03", "103", 1, "44.11"),
    ("2.04", "104", 1, "46.23"),
    ("2.05", "105", 1, "60.18"),
    ("5.03", "106", 1, "44.21"),
    ("3.01", "201", 2, "28.01"),
    ("3.02", "202", 2, "30.74"),
    ("3.03", "203", 2, "44.04"),
    ("3.04", "204", 2, "45.93"),
    ("3.05", "205", 2, "59.72"),
    ("5.04", "206", 2, "44.11"),
    ("4.01", "301", 3, "27.77"),
    ("4.02", "302", 3, "30.51"),
    ("4.03", "303", 3, "44.09"),
    ("4.04", "304", 3, "46.14"),
    ("4.05", "305", 3, "60.46"),
    ("5.05", "306", 3, "43.96"),
    ("5.01", "401", 4, "92.94"),
    ("5.02", "402", 4, "64.90"),
)

# Ground geometry regularizes the user's sketch into aligned architectural lines.
# Provisional user assignment: 1 upper middle, 2 right, 3 lower middle,
# 4 lower left, 5 upper left. Exact locations still require confirmation.
GROUND_SHAPES = (
    ("400,20 660,20 660,180 490,180 490,140 400,140", 585, 95),
    ("660,230 960,230 980,410 660,410", 835, 340),
    ("400,240 600,240 600,230 660,230 660,480 400,480", 565, 380),
    ("40,280 200,280 200,225 270,225 270,200 400,200 400,480 40,480", 215, 380),
    ("40,20 300,20 300,200 270,200 270,225 200,225 200,280 40,280", 120, 95),
)
# These polygons and the vector architecture use the same source coordinates
# and SVG transform, keeping the drawing and selectable areas aligned.
# Shared drawing for all three upper floors. Number positions remain provisional.
REGULAR_SHAPES = (
    ("410,68 685,68 685,218 502,218 502,194 410,194", 590, 130),
    ("685,68 958,68 978,218 685,218", 780, 145),
    ("680,282 987,282 1014,480 680,480", 854, 352),
    ("410,282 680,282 680,520 410,520", 585, 420),
    ("44,326 228,326 228,268 310,268 310,326 410,326 410,520 44,520", 230, 430),
    ("44,68 310,68 310,268 228,268 228,326 44,326", 135, 140),
)
ATTIC_SHAPES = (
    (
        "454,112 1082,112 1120,404 714,404 714,480 497,480 497,289 454,289",
        850,
        328,
    ),
    ("80,109 340,109 340,230 454,230 454,289 497,289 497,480 80,480", 365, 385),
)
PLAN_REFERENCES = {
    "regular": {
        "width": 358,
        "height": 541,
        "viewbox": "0 0 1047 613",
        "transform": "",
        "label_rotation": 0,
    },
    "ground": {
        "width": 953,
        "height": 747,
        "viewbox": "0 0 1008 590",
        "transform": "",
        "label_rotation": 0,
    },
    "attic": {
        "width": 305,
        "height": 561,
        "viewbox": "0 0 1160 590",
        "transform": "",
        "label_rotation": 0,
    },
}


def floor_label(number):
    return {0: "Erdgeschoss", 4: "Dachgeschoss"}.get(number, f"{number}. Obergeschoss")
