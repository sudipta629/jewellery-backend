"""
app/models/chat.py

SQLAlchemy models for the customer-admin chat system.

Models
------
Conversation          — A chat thread between a customer and admin/staff.
ConversationParticipant — Who is in the conversation (customer + staff).
Message               — Individual messages in a conversation.

Design Notes
------------
* REST-based for now. WebSocket support can be added later without
  changing the database schema.
* Messages support text, image URL, audio URL, and custom design references.
* Message status: SENT → DELIVERED → READ.
* Participants table allows multi-staff conversations if needed.
"""

import enum

from app.extensions import db
from app.models.base import TimestampMixin


class MessageStatus(str, enum.Enum):
    SENT      = "SENT"
    DELIVERED = "DELIVERED"
    READ      = "READ"


class MessageType(str, enum.Enum):
    TEXT          = "TEXT"
    IMAGE         = "IMAGE"
    AUDIO         = "AUDIO"
    DESIGN_REF    = "DESIGN_REF"   # custom design reference
    SYSTEM        = "SYSTEM"       # automated status messages


class Conversation(TimestampMixin, db.Model):
    """
    Represents a chat thread.

    Table: conversations
    """

    __tablename__ = "conversations"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # Customer who initiated the conversation
    customer_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Optional: link to a specific order or product for context
    order_id   = db.Column(db.Integer, db.ForeignKey("orders.id",   ondelete="SET NULL"), nullable=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="SET NULL"), nullable=True)

    subject = db.Column(db.String(200), nullable=True)

    is_open = db.Column(db.Boolean, nullable=False, default=True, index=True)

    # Relationships
    customer     = db.relationship("User",    foreign_keys=[customer_id],
                                   backref=db.backref("conversations", lazy="dynamic"))
    participants = db.relationship("ConversationParticipant", back_populates="conversation",
                                   cascade="all, delete-orphan")
    messages     = db.relationship("Message", back_populates="conversation",
                                   cascade="all, delete-orphan",
                                   order_by="Message.created_at.asc()")

    def __repr__(self) -> str:
        return f"<Conversation id={self.id} customer_id={self.customer_id} open={self.is_open}>"


class ConversationParticipant(db.Model):
    """
    Many-to-many: which staff members are in a conversation.

    Table: conversation_participants
    """

    __tablename__ = "conversation_participants"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    conversation_id = db.Column(
        db.Integer,
        db.ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        db.UniqueConstraint("conversation_id", "user_id", name="uq_conversation_participant"),
    )

    conversation = db.relationship("Conversation", back_populates="participants")
    user         = db.relationship("User")


class Message(TimestampMixin, db.Model):
    """
    A single message in a conversation.

    Table: messages
    """

    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    conversation_id = db.Column(
        db.Integer,
        db.ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    sender_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    message_type = db.Column(db.String(20), nullable=False, default=MessageType.TEXT)

    # Main text content
    content  = db.Column(db.Text, nullable=True)

    # URL for image/audio/file attachments (stored in cloud, not in DB)
    media_url = db.Column(db.String(500), nullable=True)

    status = db.Column(db.String(20), nullable=False, default=MessageStatus.SENT, index=True)

    is_deleted = db.Column(db.Boolean, nullable=False, default=False)

    # Relationships
    conversation = db.relationship("Conversation", back_populates="messages")
    sender       = db.relationship("User")

    def __repr__(self) -> str:
        return (
            f"<Message id={self.id} conversation_id={self.conversation_id} "
            f"sender_id={self.sender_id} type={self.message_type}>"
        )
