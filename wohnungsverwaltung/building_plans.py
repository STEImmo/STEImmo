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

# Coordinates follow the ground-floor reference (953 × 747 pixels), not floor area.
# Number-to-outline assignment is inferred and still requires confirmation.
GROUND_SHAPES = (
    ("400,166 597,166 597,278 509,278 509,297 478,297 478,278 400,278", 548, 215),
    ("120,166 299,166 299,276 278,276 278,297 233,297 233,352 120,352", 175, 222),
    ("120,359 231,359 231,328 303,328 303,302 394,302 394,505 120,505", 264, 437),
    ("402,331 509,331 509,305 605,305 605,505 402,505", 538, 418),
    ("613,331 831,331 848,455 702,455 702,402 613,402", 663, 365),
)
# These polygons use the original image pixel coordinates. The image and hit areas
# share one SVG transform, so viewport size cannot shift them relative to each other.
UPPER_SHAPES = (
    ("54,375 122,375 122,415 136,415 136,510 54,510", 92, 469),
    ("54,175 135,175 135,260 122,260 122,316 54,316", 92, 217),
    ("54,25 135,15 135,167 54,167", 94, 128),
    ("143,421 191,421 191,382 294,382 294,510 143,510", 231, 444),
    ("173,176 294,176 294,376 193,376 193,318 173,318", 231, 225),
    ("173,13 271,2 271,166 173,166", 222, 83),
)
ATTIC_SHAPES = (
    (
        "74,33 111,28 111,59 153,59 153,23 209,17 209,182 148,182 "
        "148,234 242,208 242,306 155,306 155,327 74,327 74,247 126,247 126,208 74,208",
        174,
        153,
    ),
    ("74,386 128,386 128,383 155,383 155,331 245,331 245,503 74,503", 195, 416),
)
PLAN_REFERENCES = {
    "ground": {
        "image": "plans/ground-floor-reference.png",
        "width": 953,
        "height": 747,
        "viewbox": "95 140 770 460",
        "transform": "",
        "label_rotation": 0,
    },
    "upper": {
        "image": "plans/upper-floor-reference.png",
        "width": 358,
        "height": 541,
        "viewbox": "15 20 515 315",
        "transform": "translate(541 0) rotate(90)",
        "label_rotation": -90,
    },
    "attic": {
        "image": "plans/attic-reference.png",
        "width": 305,
        "height": 561,
        "viewbox": "12 10 545 290",
        "transform": "translate(561 0) rotate(90)",
        "label_rotation": -90,
    },
}


def floor_label(number):
    return {0: "Erdgeschoss", 4: "Dachgeschoss"}.get(number, f"{number}. Obergeschoss")
