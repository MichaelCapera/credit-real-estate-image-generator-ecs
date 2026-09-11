import json
import logging
import os
import random
import sys
import time
import urllib.request
import ssl
from urllib.error import URLError, HTTPError
import fitz  # PyMuPDF
from io import BytesIO
from src.email_service import EmailService
from src.s3_service import S3Service
from src.database_service import DatabaseService
import datetime
from PIL import Image

# Standard container logging routing directly to stdout for CloudWatch/ECS logs
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
)
logger = logging.getLogger()


def format_price(price):
    """Format price with thousand separators"""
    try:
        return f"$ {float(price):,.0f}".replace(",", ".")
    except (ValueError, TypeError):
        return f"$ {price}"


def select_properties(properties, quantity):
    """Select N random properties from the list"""
    if len(properties) <= quantity:
        return properties
    return random.sample(properties, quantity)

def _cover_image_for_rect(raw_payload, target_width, target_height):
    """
    Resize and center-crop an image to exactly fill target_width x target_height.
    Mimics CSS 'object-fit: cover' behavior: fills the box without distortion,
    cropping the excess from the center.
    """
    img = Image.open(BytesIO(raw_payload)).convert("RGB")

    img_ratio = img.width / img.height
    target_ratio = target_width / target_height

    if img_ratio > target_ratio:
        # Image is wider than target: crop left/right
        new_width = int(img.height * target_ratio)
        offset = (img.width - new_width) // 2
        img = img.crop((offset, 0, img.width - offset, img.height))
    else:
        # Image is taller than target: crop top/bottom
        new_height = int(img.width / target_ratio)
        offset = (img.height - new_height) // 2
        img = img.crop((0, offset, img.width, img.height - offset))

    # Resize to exact target dimensions
    img = img.resize((target_width, target_height), Image.LANCZOS)

    out = BytesIO()
    img.save(out, format="JPEG", quality=92)
    return out.getvalue()

def _fit_text_in_rect(page, rect, text, fontname="Helvetica-Bold", align=1, color=(0, 0, 0), max_size=80, min_size=32):
    """Insert text into rect, auto-shrinking font until it fits."""
    for size in range(max_size, min_size - 1, -2):
        result = page.insert_textbox(
            rect,
            text,
            fontsize=size,
            fontname=fontname,
            align=align,
            color=color,
        )
        if result >= 0:
            logger.info(f"[FIT] '{text}' fits at fontsize={size}")
            return size
    # Fallback: force min size
    logger.warning(f"[FIT] '{text}' forced to min_size={min_size}")
    page.insert_textbox(rect, text, fontsize=min_size, fontname=fontname, align=align, color=color)
    return min_size


def generate_image_in_memory(property_data, template_bytes, index, debug=False):
    t_start_render = time.perf_counter()

    # Create a new PDF document with the exact Instagram Stories dimensions
    doc = fitz.open()
    page = doc.new_page(width=1080, height=1920)

    # Insert the PNG template as the background of the page
    page.insert_image(fitz.Rect(0, 0, 1080, 1920), stream=template_bytes)

    # --- LAYOUT RECTANGLES (measured from template-1.png) ---
    # Header: Y=0 to Y=550
    # White zone (image): Y=550 to Y=1290
    image_rect = fitz.Rect(0, 550, 1080, 1290)

    # Black panel: Y=1290 to Y=1640
    info_panel_rect = fitz.Rect(0, 1290, 1080, 1640)

    # Title
    title_rect = fitz.Rect(60, 1310, 1020, 1450)

    # Area + Ref
    area_rect = fitz.Rect(60, 1450, 1020, 1560)

    # Price (gold, big)
    price_rect = fitz.Rect(60, 1650, 1020, 1750)

    # Phone (gold)
    phone_rect = fitz.Rect(60, 1540, 1020, 1630)

    # Colors
    GOLD_COLOR = (0.788, 0.663, 0.380)  # #C9A961
    WHITE_COLOR = (0.788, 0.663, 0.380)
    GRAY_COLOR = (0.65, 0.65, 0.65)
    BLACK_COLOR = (0, 0, 0)  

    if debug:
        shape = page.new_shape()
        for rect, color in [
            (image_rect, (1, 0, 0)),
            (info_panel_rect, (0, 1, 0)),
            (title_rect, (0, 0, 1)),
            (area_rect, (1, 1, 0)),
            (price_rect, (1, 0, 1)),
            (phone_rect, (0, 1, 1)),
        ]:
            shape.draw_rect(rect)
            shape.finish(color=color, width=1)
        shape.commit()

    # --- IMAGE FETCHING ---
    image_url = property_data.get("image_url")
    if image_url:
        try:
            logger.info(
                f"[{index}] Downloading property graphic asset from: {image_url}"
            )
            t_start_download = time.perf_counter()
            ssl_context = ssl._create_unverified_context()
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            }
            req = urllib.request.Request(image_url.strip(), headers=headers)
            with urllib.request.urlopen(req, context=ssl_context, timeout=15) as resp:
                raw_payload = resp.read()
                if raw_payload.startswith(b"\xff\xd8") or raw_payload.startswith(b"\x89PNG"):
                    # Pre-process the image to fill image_rect without distortion
                    image_width = int(image_rect.width)
                    image_height = int(image_rect.height)
                    prepared_bytes = _cover_image_for_rect(raw_payload, image_width, image_height)
                    page.insert_image(image_rect, stream=prepared_bytes)
                    logger.info(
                        f"[{index}] Image bound into 9:16 canvas. "
                        f"Original: {len(raw_payload)} bytes, prepared: {len(prepared_bytes)} bytes."
                    )
                else:
                    logger.warning(f"[{index}] Invalid image binary.")
        except Exception as e:
            logger.error(f"[{index}] Error parsing image stream layer: {e}")
    else:
        logger.warning(
            f"[{index}] No 'image_url' found for property ID: {property_data.get('id', '?')}"
        )

    # --- TITLE TEXT ---
    title_text = property_data.get("title", "No Title Available")
    area_text = property_data.get("area_built", "")
    prop_id = property_data.get("id", "")
    title_upper = title_text.upper()

    sub_parts = []
    if area_text:
        sub_parts.append(area_text)
    if prop_id:
        sub_parts.append(f"Ref: #{prop_id}")
    sub_line = " - ".join(sub_parts)

    page.insert_textbox(
        title_rect,
        title_upper,
        fontsize=42,
        fontname="Helvetica-Bold",
        align=1,
        color=GOLD_COLOR,
    )

    if sub_line:
        page.insert_textbox(
            area_rect,
            sub_line,
            fontsize=46,
            fontname="Helvetica-Bold",
            align=1,
            color=GRAY_COLOR,
    )

    # --- PHONE TEXT (inside the panel, gold color) ---
    phone_text = "+57 321 2769477"
    page.insert_textbox(
        phone_rect,
        phone_text,
        fontsize=44,
        fontname="Helvetica-Bold",
        align=1,
        color=GOLD_COLOR,
    )

    
    # --- PRICE TEXT (inside the panel, gold color) ---

    price_text = format_price(property_data.get("price", 0))

    if price_text:
        _fit_text_in_rect(
            page,
            price_rect,
            price_text,
            fontname="Helvetica-Bold",
            align=1,
            color=BLACK_COLOR,
            max_size=80,
            min_size=36,
        )

    # --- RENDER at 1.0x since canvas is already 1080x1920 ---
    pix = page.get_pixmap(matrix=fitz.Matrix(1.0, 1.0))
    img_bytes = pix.tobytes("jpeg", jpg_quality=92)
    doc.close()

    logger.info(
        f"[{index}] Image pipeline completed in {time.perf_counter() - t_start_render:.2f}s"
    )
    return BytesIO(img_bytes)


# --- PRIVATE HELPER FUNCTIONS FOR COGNITIVE COMPLEXITY REDUCTION ---


def _load_config():
    """Extract and validate environment variables for ECS Task context"""
    config = {
        "api_url": os.getenv("API_URL"),
        "images_quantity": int(os.getenv("IMAGES_QUANTITY", "5")),
        "recipient_emails": [
            email.strip()
            for email in os.getenv("RECIPIENT_EMAILS", "").split(",")
            if email.strip()
        ],
        "gmail_user": os.getenv("GMAIL_USER"),
        "gmail_app_password": os.getenv("GMAIL_APP_PASSWORD"),
        "debug_mode": os.getenv("DEBUG_MODE", "false").lower() == "true",
    }

    if not config["api_url"]:
        logger.error("FATAL: Environment variable 'API_URL' is not set.")
        sys.exit(1)
    if not config["gmail_user"] or not config["gmail_app_password"]:
        logger.error(
            "FATAL: Missing Gmail credentials in environment configuration fields."
        )
        sys.exit(1)
    if not config["recipient_emails"]:
        logger.error(
            "FATAL: Target mailing recipients array ('RECIPIENT_EMAILS') is unassigned or empty."
        )
        sys.exit(1)

    return config


def _fetch_feed(api_url):
    """Fetch property data arrays from target HTTP REST Endpoint feed via urllib"""
    try:
        t_api_start = time.perf_counter()
        ssl_context = ssl._create_unverified_context()
        req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})

        with urllib.request.urlopen(req, context=ssl_context, timeout=30) as response:
            properties = json.loads(response.read().decode("utf-8"))

        logger.info(
            f"[PERF] API connection executed in {time.perf_counter() - t_api_start:.2f}s"
        )
        return properties
    except Exception as e:
        logger.error(f"FATAL: Network breakdown fetching target data stream: {e}")
        sys.exit(1)


def _load_template_bytes():
    """Load the base PNG asset into memory safe buffer context"""
    template_path = os.path.join(os.path.dirname(__file__), "assets", "template-1.jpg")
    try:
        with open(template_path, "rb") as f:
            return f.read()
    except Exception as e:
        logger.error(
            f"FATAL: Missing layout graphic asset at target path ({template_path}): {e}"
        )
        sys.exit(1)


def _build_html_body(images_data):
    """Build standardized structural reporting presentation layer template"""
    html_body = """
    <html>
    <body style="font-family: Arial, sans-serif; color: #333;">
        <h2 style="color: #2c3e50;">🏠 Real Estate Automation - Image Delivery Report</h2>
        <p>The image generator engine completed the batch tasks successfully.</p>
        <p><strong>Processed Real Estate Metadata Included:</strong></p>
        <ul style="line-height: 1.6;">
    """
    for img in images_data:
        html_body += f"    <li>{img['title']}</li>\n"
    html_body += """
        </ul>
        <p>High-resolution marketing graphics matching the criteria are attached to this delivery confirmation email.</p>
        <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
        <small style="color: #7f8c8d;">Automated Service Pipeline running inside AWS Elastic Container Service (ECS)</small>
    </body>
    </html>
    """
    return html_body


def _send_reports(config, images_data):
    """Orchestrate SMTP bulk shipping distribution layers safely"""
    email_service = EmailService(config["gmail_user"], config["gmail_app_password"])
    html_body = _build_html_body(images_data)

    t_email_start = time.perf_counter()
    for recipient in config["recipient_emails"]:
        try:
            logger.info(
                f"Shipping compiled graphic payload out to mailbox: {recipient}..."
            )
            email_service.send_images_email(
                recipient=recipient,
                subject="🏠 Marketing Media Assets - Property Update",
                body_html=html_body,
                images=images_data,
            )
        except Exception as mail_err:
            logger.error(
                f"Mailing system exception dropping package to {recipient}: {mail_err}"
            )

    logger.info(
        f"[PERF] Bulk report execution dispatch finished in {time.perf_counter() - t_email_start:.2f}s"
    )


# --- MAIN APPLICATION ENTRYPOINT ---


def main():
    """Main application orchestrator designed for ECS container tasks to generate images"""
    t_global_start = time.perf_counter()
    logger.info("Initializing ECS Task image generator engine...")

    # 1. Load context configuration parameters safely
    config = _load_config()
    logger.info(f"Targeting data feed URL: {config['api_url']}")

    # 2. Extract feed arrays from endpoint reference
    properties = _fetch_feed(config["api_url"])
    logger.info(f"Retrieved {len(properties)} total properties from source feed.")
    if not properties:
        logger.warning(
            "Data feed returned an empty properties array. Terminating engine process."
        )
        return

    # 3. Handle random selection filters
    selected = select_properties(properties, config["images_quantity"])
    logger.info(f"Staging processing engine queue for {len(selected)} selected nodes.")

    # 4. Extract base template binary assets
    template_bytes = _load_template_bytes()

    # 5. Execute processing pipelines sequentially
    s3_service = S3Service()
    db_service = DatabaseService()

    db_config = {
        "dbname": os.getenv("DB_NAME"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "host": os.getenv("DB_HOST"),
        "port": os.getenv("DB_PORT", "5432"),
    }

    images_data = []
    properties_to_save = []
    t_batch_start = time.perf_counter()
    for idx, prop in enumerate(selected):
        try:
            img_stream = generate_image_in_memory(
                prop, template_bytes, idx + 1, debug=config["debug_mode"]
            )

            file_name = f"story_{idx+1}.jpg"
            s3_public_url = s3_service.upload_bytes_to_s3(
                img_stream, file_name, subfolder="stories"
            )

            if s3_public_url:
                logger.info(
                    f"[{idx+1}] Image successfully uploaded to S3: {s3_public_url}"
                )
                prop["image_url"] = s3_public_url

            images_data.append(
                {
                    "bytes": img_stream,
                    "filename": f"property_{prop.get('id', idx+1)}.jpg",
                    "title": prop.get("title", "Untitled Real Estate Node")[:50],
                }
            )

            properties_to_save.append(prop)

        except Exception as e:
            logger.error(
                f"Pipeline processing failed on data array index reference {idx}: {e}"
            )

    logger.info(
        f"[PERF] Processing loop batch rendering completed in {time.perf_counter() - t_batch_start:.2f}s"
    )

    if properties_to_save:
        logger.info("Persisting processed properties in PostgreSQL...")
        db_service.save_to_database(properties_to_save, db_config)

    # 6. Execute bulk notification distribution layer if assets exist
    if images_data:
        _send_reports(config, images_data)
    else:
        logger.error(
            "Render exception: No valid graphic outputs were built. Dropping communication layer."
        )

    logger.info(
        f"[PERF] >>> TOTAL PROCESS PIPELINE EXECUTION TIME: {time.perf_counter() - t_global_start:.2f}s <<<"
    )


if __name__ == "__main__":
    main()
