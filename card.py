import csv
import io
import os

import requests
from dotenv import load_dotenv
from PIL import Image


load_dotenv()

SHEET_ID = os.environ["SHEET_2"]
GID = os.environ["GID_2"]
CELL_RANGE = os.environ["CELL_RANGE_2"]
BASE_URL = os.environ["BASE_URL_2"]
VARIANTS = os.environ["VARIANTS_2"].split(",")

FRAME_DIR = "overlays/frame"
ATTR_DIR = "overlays/attributes"
STAR_DIR = "overlays/star"

CARD_SIZE = (156, 156)

VERSIONS = (1, 2)

LAYOUTS = {
    1: {
        "base_pos": (8, 8),
        "base_size": (140, 140),
        "attr_pos": (1, 1),
        "attr_size": (35, 35),
        "star_pos": [
            (10, 118),
            (36, 118),
            (62, 118),
            (88, 118),
        ],
        "star_size": (28, 28),
        "crop": False,
    },

    2: {
        "base_pos": (2, 2),
        "base_size": (152, 152),
        "attr_pos": (0, 0),
        "attr_size": (35, 35),
        "star_pos": [
            (5, 125),
            (29, 125),
            (53, 125),
            (77, 125),
        ],
        "star_size": (24, 24),
        "crop": True,
    },
}

STATS = {
    "downloaded": 0,
    "done": 0,
    "skipped": 0,
    "missing": 0,
    "errors": 0,
}

OVERLAY_CACHE = {}


def get_sheet():
    sheet_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}&range={CELL_RANGE}"


    response = requests.get(sheet_url, timeout=(10, 60))
    response.raise_for_status()

    reader = csv.DictReader(io.StringIO(response.text))

    return [
        (row["cardRarityType"], row["attr"], row["assetbundleName"])
        for row in reader
    ]


def fit_image(image, size):
    scale = max(
        size[0] / image.width,
        size[1] / image.height,
    )

    new_size = (
        int(image.width * scale),
        int(image.height * scale),
    )

    resized = image.resize(
        new_size,
        Image.Resampling.LANCZOS,
    )

    left = (resized.width - size[0]) // 2
    top = (resized.height - size[1]) // 2

    cropped = resized.crop(
        (
            left,
            top,
            left + size[0],
            top + size[1],
        )
    )

    resized.close()

    return cropped


def add_overlay(canvas, path, position, target_size):
    cache_key = (path, target_size)

    if cache_key not in OVERLAY_CACHE:
        overlay = Image.open(path).convert("RGBA")

        if overlay.size != target_size:
            resized = overlay.resize(
                target_size,
                Image.Resampling.LANCZOS,
            )
            overlay.close()
            overlay = resized

        overlay.load()
        OVERLAY_CACHE[cache_key] = overlay

    canvas.alpha_composite(OVERLAY_CACHE[cache_key], position)


def fetch_image(assetname, variant):
    url = BASE_URL.format(
        asset=assetname,
        variant=variant,
    )

    response = requests.get(
        url,
        timeout=(10, 60),
    )

    if response.status_code != 200:
        return None

    image = Image.open(io.BytesIO(response.content)).convert("RGBA")

    image.load()
    STATS["downloaded"] += 1

    return image


def render(original, filename, version, rarity, attr, state):
    layout = LAYOUTS[version]

    output_dir = f"thumbnail_{version}"
    output_path = os.path.join(output_dir, filename)

    os.makedirs(output_dir, exist_ok=True)

    canvas = None
    try:
        canvas = Image.new("RGBA", CARD_SIZE)

        if layout["crop"]:
            base = fit_image(
                original,
                layout["base_size"],
            )
        else:
            base = original.resize(
                layout["base_size"],
                Image.Resampling.LANCZOS,
            )

        canvas.alpha_composite(
            base,
            layout["base_pos"],
        )
        base.close()

        add_overlay(
            canvas,
            os.path.join(
                FRAME_DIR,
                f"{version}_frame_{rarity}.png",
            ),
            (0, 0),
            CARD_SIZE,
        )

        add_overlay(
            canvas,
            os.path.join(ATTR_DIR, f"{version}_attr_{attr}.png"),
            layout["attr_pos"],
            layout["attr_size"],
        )

        if rarity == "birthday":
            add_overlay(
                canvas,
                os.path.join(STAR_DIR, "star_birthday.png"),
                layout["star_pos"][0],
                layout["star_size"],
            )
        else:
            star_file = (
                "star_after.png"
                if state == "training"
                else "star_normal.png"
            )

            star_path = os.path.join(STAR_DIR, star_file)

            for position in layout["star_pos"][:int(rarity)]:
                add_overlay(
                    canvas,
                    star_path,
                    position,
                    layout["star_size"],
                )

        canvas = canvas.resize(original.size, Image.Resampling.LANCZOS)

        if version == 1:
            converted = canvas.convert("RGB")
            canvas.close()
            canvas = converted

        elif version == 2:
            background = Image.new("RGB", canvas.size, (255, 255, 255))
            background.paste(canvas, mask=canvas.getchannel("A"))
            canvas.close()
            canvas = background

        canvas.save(output_path, "WEBP", quality=85, method=6)

        STATS["done"] += 1
        print(f"done {filename}")

    except Exception as error:
        STATS["errors"] += 1
        print(f"error v{version} {filename}: {error}")

    finally:
        if canvas is not None:
            canvas.close()

def main():
    for rarity, attr, assetname in get_sheet():
        if rarity == "rarity_birthday":
            rarity = "birthday"
        else:
            rarity = rarity.replace("rarity_", "")

        variants = [
            (f"{assetname}_normal.webp", "_normal.webp", "normal")
        ]

        if rarity in ("3", "4"):
            variants.append(
                (f"{assetname}_after_training.webp", "_after_training.webp", "training")
            )

        for filename, variant, state in variants:
            missing_versions = [
                version
                for version in VERSIONS
                if not os.path.exists(os.path.join(f"thumbnail_{version}", filename))
            ]

            if not missing_versions:
                STATS["skipped"] += 1
                print(f"skip {filename}")
                continue

            original = fetch_image(assetname, variant)

            if original is None:
                STATS["missing"] += 1
                print(f"missing {filename}")
                continue

            try:
                for version in missing_versions:
                    render(
                        original,
                        filename,
                        version,
                        rarity,
                        attr,
                        state,
                    )
            finally:
                original.close()

    for overlay in OVERLAY_CACHE.values():
        overlay.close()

    print()
    print("Complete")
    print(f"Downloaded: {STATS['downloaded']}")
    print(f"Done      : {STATS['done']}")
    print(f"Skipped   : {STATS['skipped']}")
    print(f"Missing   : {STATS['missing']}")
    print(f"Errors    : {STATS['errors']}")


if __name__ == "__main__":
    main()