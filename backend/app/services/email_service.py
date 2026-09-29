"""
app/services/email_service.py

Handles sending emails via SMTP.
"""

import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)

class EmailService:
    """
    Service for sending emails, such as OTPs, via Gmail SMTP.
    """

    @staticmethod
    def send_otp_email(recipient_email: str, otp: str) -> bool:
        """
        Sends an OTP email to the given recipient using Gmail SMTP with STARTTLS.
        
        Args:
            recipient_email: The email address of the user.
            otp: The plaintext OTP string.
            
        Returns:
            True if the email was sent successfully, False otherwise.
        """
        gmail_user = os.environ.get("GMAIL_ADDRESS")
        gmail_password = os.environ.get("GMAIL_APP_PASSWORD")

        if not gmail_user or not gmail_password:
            logger.error("[EmailService] GMAIL_ADDRESS or GMAIL_APP_PASSWORD is not set.")
            return False

        msg = EmailMessage()
        msg.set_content(
            f"Hello,\n\n"
            f"Your login verification code is: {otp}\n\n"
            f"This code will expire in 5 minutes. Do not share it with anyone."
        )
        msg["Subject"] = "Your Login Verification Code"
        msg["From"] = gmail_user
        msg["To"] = recipient_email

        try:
            # Connect to Gmail SMTP server on port 587 and use STARTTLS
            with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as server:
                server.starttls()
                server.login(gmail_user, gmail_password)
                server.send_message(msg)
                
            logger.info("[EmailService] OTP email sent successfully to %s", recipient_email)
            return True
            
        except Exception as e:
            logger.error("[EmailService] Failed to send OTP email to %s: %s", recipient_email, str(e))
            return False
