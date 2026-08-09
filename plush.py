import os
import csv
import io

import requests
from dotenv import load_dotenv
from PIL import Image, ImageOps


load_dotenv()

SHEET_ID = os.environ["SHEET_1"]
GID = os.environ["GID_1"]
CELL_RANGE = os.environ["CELL_RANGE_1"]
BASE_URL = os.environ["BASE_URL_1"]
VARIANTS = os.environ["VARIANTS_1"].split(",")


download_stats = {
    "processed": 0,
    "downloaded": 0,
    "missing": 0,
    "skipped": 0,
    "errors": 0,
}

process_stats = {
    "total": 0,
    "done": 0,
    "skipped": 0,
    "ignored": 0,
    "errors": 0,
}

folder = "plushies"

def download_assets():

    sheet_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}&range={CELL_RANGE}"

    os.makedirs(folder, exist_ok=True)

    try:
        response = requests.get(sheet_url, timeout=(10, 60))
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Could not access spreadsheet: {e}")
        download_stats["errors"] += 1
        return

    reader = csv.reader(io.StringIO(response.text))
    assets = set()

    for row in reader:
        if row and row[0]:
            assets.add(row[0])

    for asset in assets:
        if asset == "assetbundleName":
            continue

        for variant in VARIANTS:

            if not variant:
                continue

            filename = f"{asset}{variant}"
            path = os.path.join(folder, filename)

            download_stats["processed"] += 1

            if os.path.exists(path):
                download_stats["skipped"] += 1
                print(f"Skipping {filename}")
                continue

            url = BASE_URL.format(
                asset=asset,
                variant=variant,
            )

            try:
                response = requests.get(url, timeout=10)

                if response.status_code == 200:
                    with open(path, "wb") as f:
                        f.write(response.content)

                    download_stats["downloaded"] += 1
                    print(f"Downloaded {filename}")

                elif response.status_code == 404:
                    download_stats["missing"] += 1
                    print(f"Missing {filename}")

                else:
                    download_stats["errors"] += 1
                    print(f"HTTP {response.status_code} for {filename}")

            except requests.RequestException as e:
                download_stats["errors"] += 1
                print(f"Error downloading {filename}: {e}")


def get_main_name(filename):
    name, ext = os.path.splitext(os.path.basename(filename))

    for size in ("small", "medium", "large"):
        suffix = f"{size}_1"

        if name.endswith(suffix):
            return f"{name[:-len(suffix)]}main_1{ext}"

    return None


def process_images():
    images = [
        os.path.join(folder, filename)
        for filename in os.listdir(folder)
        if filename.endswith(".webp")
    ]

    if not images:
        print("No images found.")
        return

    reference = images[0]

    with Image.open(reference) as image:
        image = image.convert("RGBA")

        width, height = image.size

        corner = image.crop(
            (
                width - int(width * 0.27),
                height - int(height * 0.27),
                width,
                height,
            )
        )

        corner = corner.rotate(180)

    process_stats["total"] = len(images)

    for path in images:
        filename = os.path.basename(path)
        output_name = get_main_name(filename)

        if output_name is None:
            process_stats["ignored"] += 1
            continue

        output_path = os.path.join(folder, output_name)

        if os.path.exists(output_path):
            process_stats["skipped"] += 1
            print(f"Skipping {output_name}")
            continue

        try:
            with Image.open(path) as image:
                image = image.convert("RGBA")

                image.paste(corner, (0, 0))

                image.save(output_path, "WEBP", quality=90, method=6)

            process_stats["done"] += 1
            print(f"Created {output_name}")

        except Exception as e:
            process_stats["errors"] += 1
            print(f"Error processing {filename}: {e}")


def main():
    download_assets()

    print(f"Processed: {download_stats['processed']}")
    print(f"Downloaded: {download_stats['downloaded']}")
    print(f"Skipped: {download_stats['skipped']}")
    print(f"Missing: {download_stats['missing']}")
    print(f"Errors: {download_stats['errors']}")

    process_images()

    print(f"Found: {process_stats['total']}")
    print(f"Created: {process_stats['done']}")
    print(f"Skipped: {process_stats['skipped']}")
    print(f"Ignored: {process_stats['ignored']}")
    print(f"Errors: {process_stats['errors']}")


if __name__ == "__main__":
    main()