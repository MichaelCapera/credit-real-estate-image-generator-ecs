import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage

logger = logging.getLogger()

class EmailService:
    """
    Service responsible for formatting and sending status reports and alerts
    using secure SMTP with TLS/SSL.
    """
    def __init__(self, user, app_password):
        self.user = user
        self.password = app_password
        self.server = "smtp.gmail.com"
        self.port = 465

    def send_report(self, recipient, subject, body_html):
        """
        Sends an HTML-formatted email to the specified recipient.
        """
        msg = MIMEMultipart()
        msg['From'] = self.user
        msg['To'] = recipient
        msg['Subject'] = subject
        msg.attach(MIMEText(body_html, 'html'))

        try:
            # Establish a secure SSL connection with the SMTP server
            with smtplib.SMTP_SSL(self.server, self.port) as server:
                server.login(self.user, self.password)
                server.send_message(msg)
            logger.info(f"[EMAIL] Success status report delivered to {recipient}")
            return True
        except Exception as e:
            logger.error(f"[EMAIL ERROR] Execution failed: {str(e)}")
            return False
    
    def send_images_email(self, recipient, subject, body_html, images):
        """
        Sends an HTML-formatted email with multiple image attachments.
        
        Args:
            recipient: Email address of the recipient
            subject: Email subject line
            body_html: HTML content for the email body
            images: List of dictionaries with keys 'bytes' (BytesIO), 'filename' (str)
        """
        msg = MIMEMultipart()
        msg['From'] = self.user
        msg['To'] = recipient
        msg['Subject'] = subject
        msg.attach(MIMEText(body_html, 'html'))
        
        # Attach all images
        for img_data in images:
            img_bytes = img_data['bytes']
            img_bytes.seek(0)  # Reset to beginning of BytesIO object
            img = MIMEImage(img_bytes.read(), name=img_data['filename'])
            msg.attach(img)
        
        try:
            # Establish a secure SSL connection with the SMTP server
            with smtplib.SMTP_SSL(self.server, self.port) as server:
                server.login(self.user, self.password)
                server.send_message(msg)
            logger.info(f"[EMAIL] Successfully sent {len(images)} images to {recipient}")
            return True
        except Exception as e:
            logger.error(f"[EMAIL ERROR] Failed to send images: {str(e)}")
            return False