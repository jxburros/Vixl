"""Build an editable VIXL Line review sheet and ready-to-use emoji packs, offline."""

from pathlib import Path

from vixl import Project
from vixl.emojis import _entries, export_pack, identifier

SAMPLES = [
    "😀",
    "😂",
    "🥹",
    "😍",
    "😎",
    "🤔",
    "😴",
    "🥳",
    "👋",
    "👍",
    "🙏",
    "💪",
    "👋🏻",
    "👋🏽",
    "👋🏿",
    "🫶",
    "🧑‍🚀",
    "👩🏽‍🎨",
    "🧑‍💻",
    "👨‍👩‍👧‍👦",
    "🧑‍🦽",
    "🏃‍➡️",
    "🧜‍♀️",
    "🕺",
    "🐶",
    "🐱",
    "🦊",
    "🐸",
    "🦋",
    "🐙",
    "🌵",
    "🌻",
    "🍎",
    "🍑",
    "🥑",
    "🍕",
    "🍜",
    "☕",
    "🍰",
    "🍓",
    "🚀",
    "🚲",
    "🏠",
    "🎨",
    "🎮",
    "🎸",
    "📷",
    "💡",
    "❤️",
    "✨",
    "🔥",
    "✅",
    "🇬🇧",
    "🇯🇵",
    "🏳️‍🌈",
    "1️⃣",
]


def sheet(output, stem, samples, title, subtitle, credit):
    output.mkdir(parents=True, exist_ok=True)
    rows = (len(samples) + 7) // 8
    p = Project(960, rows * 112 + 312, background="#F7F5EF")
    ops = [
        {
            "type": "text",
            "name": "title",
            "text": title,
            "size": 48,
            "color": "#23364D",
            "x": 48,
            "y": 36,
        },
        {
            "type": "text",
            "name": "subtitle",
            "text": subtitle,
            "size": 17,
            "color": "#4C5968",
            "x": 50,
            "y": 99,
        },
    ]
    for i, emoji in enumerate(samples):
        x = 48 + (i % 8) * 108
        y = 144 + (i // 8) * 112
        ops.append(
            {
                "type": "shape",
                "shape": "rounded-rectangle",
                "radius": 12,
                "name": f"card-{i}",
                "width": 96,
                "height": 100,
                "fill": "#FFFCF5",
                "x": x,
                "y": y,
            }
        )
        ops.append({"type": "text", "name": f"emoji-{i}", "text": emoji, "size": 72, "x": x + 12, "y": y + 2})
        name = _entries()[identifier(emoji)]["name"]
        if len(name) > 14:
            name = name[:12] + "…"
        ops.append(
            {
                "type": "text",
                "name": f"name-{i}",
                "text": name,
                "size": 10,
                "color": "#4C5968",
                "x": x + 8,
                "y": y + 82,
            }
        )
    ops += [
        {
            "type": "text",
            "name": "sizes",
            "text": "Small-size check:",
            "size": 14,
            "color": "#23364D",
            "x": 50,
            "y": rows * 112 + 170,
        }
    ]
    for i, emoji in enumerate(samples[:: max(1, len(samples) // 6)][:6]):
        ops.append(
            {
                "type": "text",
                "name": f"small-{i}",
                "text": emoji,
                "size": 24,
                "x": 220 + i * 40,
                "y": rows * 112 + 166,
            }
        )
        ops.append(
            {
                "type": "text",
                "name": f"medium-{i}",
                "text": emoji,
                "size": 32,
                "x": 500 + i * 44,
                "y": rows * 112 + 162,
            }
        )
    ops.append(
        {
            "type": "text",
            "name": "credit",
            "text": credit,
            "size": 13,
            "color": "#4C5968",
            "x": 50,
            "y": rows * 112 + 223,
        }
    )
    p.apply(ops, detail="compact")
    assert p.check(checks=["bounds"])["passed"]
    p.save(output / (stem + ".vixl"), overwrite=True)
    p.export(output / (stem + ".png"), overwrite=True)


def build(output=Path("examples/output/emojis")):
    originals = [key for key in _entries() if key.startswith(":")]
    reactions = [key for key in originals if _entries()[key]["group"] == "VIXL Reactions"]
    faces = [key for key in originals if _entries()[key]["group"] == "VIXL Faces"]
    everyday = [key for key in originals if _entries()[key]["group"] == "VIXL Everyday"]
    sheet(
        output,
        "vixl-line",
        SAMPLES,
        "VIXL Line 2",
        "Soft geometry · Unicode 17 · editable vector masters",
        "Adapted from OpenMoji 17 · CC BY-SA 4.0 · Made with Vixl",
    )
    sheet(
        output,
        "vixl-reactions",
        reactions,
        "VIXL Reactions",
        f"{len(reactions)} original reactions · gestures, support, celebration and status",
        "Original VIXL artwork · CC BY-SA 4.0 · Editable masters included",
    )
    for stem, samples, title, subtitle in (
        (
            "vixl-originals",
            originals,
            "VIXL Originals",
            "100 original emojis · faces, reactions and everyday symbols",
        ),
        (
            "vixl-faces",
            faces,
            "VIXL Faces",
            "24 original faces and moods · softened geometry, expressive details",
        ),
        (
            "vixl-everyday",
            everyday,
            "VIXL Everyday",
            "32 original everyday symbols · food, hobbies, places and activities",
        ),
    ):
        sheet(
            output,
            stem,
            samples,
            title,
            subtitle,
            "Original VIXL artwork · CC BY-SA 4.0 · Editable masters included",
        )
        export_pack(output / (stem + ".zip"), samples, destination="discord", overwrite=True)
    sheet(
        output,
        "vixl-style-preview",
        [
            ":delighted:",
            ":cheeky:",
            ":skeptical:",
            ":happy_tears:",
            ":yawning:",
            ":determined:",
            ":heart_eyes:",
            ":quiet_please:",
            ":high_five:",
            ":fist_bump:",
            ":sending_love:",
            ":good_luck:",
            ":teamwork:",
            ":big_win:",
            ":take_a_break:",
            ":deal:",
            ":coffee_time:",
            ":study_time:",
            ":music_time:",
            ":plant_care:",
            ":pet_time:",
            ":rainy_day:",
            ":bed_time:",
            ":budget_check:",
        ],
        "VIXL Originals",
        "A selection from 100 original faces, reactions and everyday symbols",
        "Original VIXL artwork · CC BY-SA 4.0 · Editable masters included",
    )
    export_pack(
        output / "discord-starter.zip",
        SAMPLES[:8] + SAMPLES[8::3] + originals[:24],
        destination="discord",
        overwrite=True,
    )
    export_pack(output / "vixl-reactions.zip", reactions, destination="discord", overwrite=True)
    export_pack(
        output / "vixl-originals-images.zip", originals, destination="images", size=512, overwrite=True
    )
    export_pack(output / "vixl-line-images.zip", destination="images", overwrite=True)
    print(output.resolve(), flush=True)


if __name__ == "__main__":
    build()
