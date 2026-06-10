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

# Standard container logging routing directly to stdout for CloudWatch/ECS logs
logging.basicConfig(
    stream=sys.stdout, 
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s'
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

def generate_image_in_memory(property_data, template_bytes, index, debug=False):
    """
    Generate a high-quality JPG image from the PDF template and property data.
    Validates images using binary magic numbers to bypass misconfigured CDNs.
    """
    t_start_render = time.perf_counter()
    
    doc = fitz.open(stream=template_bytes, filetype="pdf")
    page = doc[0]
    
    image_rect = fitz.Rect(0, 100, 810, 750)
    title_rect = fitz.Rect(50, 770, 760, 850)
    price_rect = fitz.Rect(0, 880, 810, 950)
    
    if debug:
        shape = page.new_shape()
        shape.draw_rect(image_rect)
        shape.finish(color=(1, 0, 0), width=1)
        shape.draw_rect(title_rect)
        shape.finish(color=(0, 1, 0), width=1)
        shape.draw_rect(price_rect)
        shape.finish(color=(0, 0, 1), width=1)
        shape.commit()
    
    # --- IMAGE FETCHING WORKFLOW ---
    image_url = property_data.get('image_url')
    if image_url:
        try:
            logger.info(f"[{index}] Downloading property graphic asset from: {image_url}")
            t_start_download = time.perf_counter()
            
            ssl_context = ssl._create_unverified_context()
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
            }
            
            req = urllib.request.Request(image_url.strip(), headers=headers)
            with urllib.request.urlopen(req, context=ssl_context, timeout=15) as resp:
                raw_payload = resp.read()
                
                # Verify real format by inspecting file signatures (Magic Bytes) directly
                if raw_payload.startswith(b'\xff\xd8') or raw_payload.startswith(b'\x89PNG'):
                    page.insert_image(image_rect, stream=raw_payload, keep_proportion=True)
                    logger.info(f"[{index}] Image stream successfully bound into canvas layout context. Size: {len(raw_payload)} bytes. Runtime: {time.perf_counter() - t_start_download:.2f}s")
                else:
                    content_type = resp.info().get_content_type()
                    error_sample = raw_payload.decode('utf-8', errors='ignore')[:100]
                    logger.warning(f"[{index}] Content-Type check failed or invalid binary. Content-Type: {content_type}. Header sample: {error_sample}")
                        
        except Exception as e:
            logger.error(f"[{index}] Unexpected error parsing image stream layer: {e}")
    else:
        logger.warning(f"[{index}] No 'image_url' found for property ID: {property_data.get('id', '?')}")
    
    # --- TEXT CONSTRUCTION AND TYPOGRAPHY INJECTION ---
    title_text = property_data.get('title', 'No Title Available')
    area_text = property_data.get('area_built', '')
    full_title = f"{title_text} - {area_text}" if area_text else title_text
    price_text = format_price(property_data.get('price', 0))
    
    page.insert_textbox(title_rect, full_title, fontsize=20, fontname="Helvetica-Bold", align=1, color=(0.2, 0.2, 0.2))
    page.insert_textbox(price_rect, price_text, fontsize=40, fontname="Helvetica-Bold", align=1, color=(1, 0.5, 0))
    
    pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
    img_bytes = pix.tobytes("jpeg")
    doc.close()
    
    logger.info(f"[{index}] Image transformation pipeline completed in {time.perf_counter() - t_start_render:.2f}s")
    return BytesIO(img_bytes)


# --- PRIVATE HELPER FUNCTIONS FOR COGNITIVE COMPLEXITY REDUCTION ---

def _load_config():
    """Extract and validate environment variables for ECS Task context"""
    config = {
        'api_url': os.getenv('API_URL'),
        'images_quantity': int(os.getenv('IMAGES_QUANTITY', '5')),
        'recipient_emails': [email.strip() for email in os.getenv('RECIPIENT_EMAILS', '').split(',') if email.strip()],
        'gmail_user': os.getenv('GMAIL_USER'),
        'gmail_app_password': os.getenv('GMAIL_APP_PASSWORD'),
        'debug_mode': os.getenv('DEBUG_MODE', 'false').lower() == 'true'
    }
    
    if not config['api_url']:
        logger.error("FATAL: Environment variable 'API_URL' is not set.")
        sys.exit(1)
    if not config['gmail_user'] or not config['gmail_app_password']:
        logger.error("FATAL: Missing Gmail credentials in environment configuration fields.")
        sys.exit(1)
    if not config['recipient_emails']:
        logger.error("FATAL: Target mailing recipients array ('RECIPIENT_EMAILS') is unassigned or empty.")
        sys.exit(1)
        
    return config

def _fetch_feed(api_url):
    """Fetch property data arrays from target HTTP REST Endpoint feed via urllib"""
    try:
        t_api_start = time.perf_counter()
        ssl_context = ssl._create_unverified_context()
        req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
        
        with urllib.request.urlopen(req, context=ssl_context, timeout=30) as response:
            properties = json.loads(response.read().decode('utf-8'))
            
        logger.info(f"[PERF] API connection executed in {time.perf_counter() - t_api_start:.2f}s")
        return properties
    except Exception as e:
        logger.error(f"FATAL: Network breakdown fetching target data stream: {e}")
        sys.exit(1)

def _load_template_bytes():
    """Load the base PDF asset into memory safe buffer context"""
    template_path = os.path.join(os.path.dirname(__file__), 'assets', 'template-1.pdf')
    try:
        with open(template_path, 'rb') as f:
            return f.read()
    except Exception as e:
        logger.error(f"FATAL: Missing layout graphic asset at target path ({template_path}): {e}")
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
    email_service = EmailService(config['gmail_user'], config['gmail_app_password'])
    html_body = _build_html_body(images_data)
    
    t_email_start = time.perf_counter()
    for recipient in config['recipient_emails']:
        try:
            logger.info(f"Shipping compiled graphic payload out to mailbox: {recipient}...")
            email_service.send_images_email(
                recipient=recipient,
                subject="🏠 Marketing Media Assets - Property Update",
                body_html=html_body,
                images=images_data
            )
        except Exception as mail_err:
            logger.error(f"Mailing system exception dropping package to {recipient}: {mail_err}")
            
    logger.info(f"[PERF] Bulk report execution dispatch finished in {time.perf_counter() - t_email_start:.2f}s")


# --- MAIN APPLICATION ENTRYPOINT ---

def main():
    """Main application orchestrator designed for ECS container tasks"""
    t_global_start = time.perf_counter()
    logger.info("Initializing ECS Task image generator engine...")
    
    # 1. Load context configuration parameters safely
    config = _load_config()
    logger.info(f"Targeting data feed URL: {config['api_url']}")
    
    # 2. Extract feed arrays from endpoint reference
    properties = _fetch_feed(config['api_url'])
    logger.info(f"Retrieved {len(properties)} total properties from source feed.")
    if not properties:
        logger.warning("Data feed returned an empty properties array. Terminating engine process.")
        return

    # 3. Handle random selection filters
    selected = select_properties(properties, config['images_quantity'])
    logger.info(f"Staging processing engine queue for {len(selected)} selected nodes.")
    
    # 4. Extract base template binary assets
    template_bytes = _load_template_bytes()
    
    # 5. Execute processing pipelines sequentially
    images_data = []
    t_batch_start = time.perf_counter()
    for idx, prop in enumerate(selected):
        try:
            img_stream = generate_image_in_memory(prop, template_bytes, idx+1, debug=config['debug_mode'])
            images_data.append({
                'bytes': img_stream,
                'filename': f"property_{prop.get('id', idx+1)}.jpg",
                'title': prop.get('title', 'Untitled Real Estate Node')[:50]
            })
        except Exception as e:
            logger.error(f"Pipeline processing failed on data array index reference {idx}: {e}")

    logger.info(f"[PERF] Processing loop batch rendering completed in {time.perf_counter() - t_batch_start:.2f}s")
    
    # 6. Execute bulk notification distribution layer if assets exist
    if images_data:
        _send_reports(config, images_data)
    else:
        logger.error("Render exception: No valid graphic outputs were built. Dropping communication layer.")
        
    logger.info(f"[PERF] >>> TOTAL PROCESS PIPELINE EXECUTION TIME: {time.perf_counter() - t_global_start:.2f}s <<<")

if __name__ == "__main__":
    main()