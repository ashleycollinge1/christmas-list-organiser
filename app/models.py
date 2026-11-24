from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

ROLE_ADMIN = "admin"
ROLE_USER = "user"

# Gift lifecycle, in order. Tapping a status pill advances to the next one.
STATUS_IDEA = "idea"
STATUS_ORDERED = "ordered"
STATUS_DELIVERED = "delivered"
STATUS_WRAPPED = "wrapped"
STATUS_GIVEN = "given"
STATUSES = (STATUS_IDEA, STATUS_ORDERED, STATUS_DELIVERED, STATUS_WRAPPED, STATUS_GIVEN)

PRIORITY_HIGH = 1
PRIORITY_MEDIUM = 2
PRIORITY_LOW = 3


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default=ROLE_USER)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_users_username_lower", func.lower(username), unique=True),)

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    @property
    def name(self) -> str:
        return self.display_name or self.username


class AuthSession(Base):
    __tablename__ = "sessions"

    # SHA-256 of the cookie token; the raw token is never stored.
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped[User] = relationship(lazy="joined")


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # SHA-256 of the token in the link; the raw token is shown once, never stored.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    note: Mapped[str | None] = mapped_column(String(120))
    make_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    used_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    used_by: Mapped[User | None] = relationship(foreign_keys=[used_by_id])


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[object] = mapped_column(JSONB, nullable=False)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (Index("ix_categories_name_lower", func.lower(name), unique=True),)


# Occasion kinds. Each has its own app title: Christmas List, Birthday List, Gift List.
KIND_CHRISTMAS = "christmas"
KIND_BIRTHDAY = "birthday"
KIND_OTHER = "other"
KINDS = (KIND_CHRISTMAS, KIND_BIRTHDAY, KIND_OTHER)


class Occasion(Base):
    """A Christmas, a birthday or any other gift-giving occasion.

    Stored in the ``seasons`` table (its v0.1.0 name) so upgrades never rename tables.
    Any number can be active; archived occasions are read-only.
    """

    __tablename__ = "seasons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default=KIND_CHRISTMAS, server_default=KIND_CHRISTMAS)
    occasion_date: Mapped[date | None] = mapped_column(Date)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_by: Mapped[User | None] = relationship(lazy="joined")

    __table_args__ = (CheckConstraint("kind IN ('christmas','birthday','other')", name="ck_seasons_kind"),)


PERSON_RECIPIENT = "recipient"
PERSON_ME = "me"
PERSON_KINDS = (PERSON_RECIPIENT, PERSON_ME)


class Person(Base):
    """Someone you buy for, or "me" (your own wish list). Linked across occasions:
    notes and category live here, so editing Molly's sizes once updates every
    occasion she's in. Private to the owner."""

    __tablename__ = "people"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default=PERSON_RECIPIENT, server_default=PERSON_RECIPIENT
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    owner: Mapped[User] = relationship(lazy="joined")
    category: Mapped[Category | None] = relationship(lazy="joined")
    entries: Mapped[list[Recipient]] = relationship(back_populates="person", lazy="selectin")

    __table_args__ = (
        CheckConstraint("kind IN ('recipient','me')", name="ck_people_kind"),
        # One "me" per account.
        Index("uq_people_one_me", "owner_id", unique=True, postgresql_where=text("kind = 'me'")),
    )

    @property
    def is_me(self) -> bool:
        return self.kind == PERSON_ME


class Recipient(Base):
    """A person's entry in one occasion: budget, sharing and gifts."""

    __tablename__ = "recipients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    occasion_id: Mapped[int] = mapped_column(
        "season_id", ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # Deleting a person with entries is refused (NO ACTION); deleting a user cascades both.
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"), nullable=False, index=True)
    budget_pence: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # v0.1.0 columns, kept (never dropped) and mirrored from the person on every write,
    # so the data stays complete and readable by older versions.
    legacy_name: Mapped[str] = mapped_column("name", String(80), nullable=False)
    legacy_notes: Mapped[str | None] = mapped_column("notes", Text)
    legacy_category_id: Mapped[int | None] = mapped_column(
        "category_id", ForeignKey("categories.id", ondelete="SET NULL")
    )

    owner: Mapped[User] = relationship(lazy="joined")
    person: Mapped[Person] = relationship(back_populates="entries", lazy="joined")
    occasion: Mapped[Occasion] = relationship(lazy="joined")
    shares: Mapped[list[RecipientShare]] = relationship(
        back_populates="recipient", cascade="all, delete-orphan", lazy="selectin"
    )
    gifts: Mapped[list[Gift]] = relationship(
        back_populates="recipient", cascade="all, delete-orphan", lazy="selectin", order_by="Gift.id"
    )

    __table_args__ = (CheckConstraint("budget_pence IS NULL OR budget_pence >= 0", name="ck_recipient_budget"),)

    @property
    def name(self) -> str:
        return self.person.name

    def mirror_person(self) -> None:
        self.legacy_name = self.person.name
        self.legacy_notes = self.person.notes
        self.legacy_category_id = self.person.category_id


class RecipientShare(Base):
    __tablename__ = "recipient_shares"

    recipient_id: Mapped[int] = mapped_column(ForeignKey("recipients.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)

    recipient: Mapped[Recipient] = relationship(back_populates="shares")
    user: Mapped[User] = relationship(lazy="joined")


class Gift(Base):
    __tablename__ = "gifts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipient_id: Mapped[int] = mapped_column(
        ForeignKey("recipients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    link: Mapped[str | None] = mapped_column(String(2048))
    price_pence: Mapped[int | None] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # When splitting a joint gift, what it costs *us*; replaces price x quantity in totals.
    my_share_pence: Mapped[int | None] = mapped_column(Integer)
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=PRIORITY_MEDIUM)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=STATUS_IDEA)
    notes: Mapped[str | None] = mapped_column(Text)
    buyer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    retailer: Mapped[str | None] = mapped_column(String(120))
    tracking_number: Mapped[str | None] = mapped_column(String(120))
    delivery_date: Mapped[date | None] = mapped_column(Date)
    hiding_place: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    recipient: Mapped[Recipient] = relationship(back_populates="gifts")
    buyer: Mapped[User | None] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint("quantity >= 1", name="ck_gift_quantity"),
        CheckConstraint("price_pence IS NULL OR price_pence >= 0", name="ck_gift_price"),
        CheckConstraint("my_share_pence IS NULL OR my_share_pence >= 0", name="ck_gift_share"),
        CheckConstraint("priority BETWEEN 1 AND 3", name="ck_gift_priority"),
        CheckConstraint(
            "status IN ('idea','ordered','delivered','wrapped','given')",
            name="ck_gift_status",
        ),
    )


class Wish(Base):
    """Something you'd like. Belongs to your "me" person, either Anytime
    (occasion_id NULL) or a specific occasion. Never counts towards spending.
    If its occasion is deleted, it falls back to Anytime rather than being lost."""

    __tablename__ = "wishes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"), nullable=False, index=True)
    occasion_id: Mapped[int | None] = mapped_column(ForeignKey("seasons.id", ondelete="SET NULL"), index=True)
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    link: Mapped[str | None] = mapped_column(String(2048))
    price_pence: Mapped[int | None] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=PRIORITY_MEDIUM)
    notes: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    occasion: Mapped[Occasion | None] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint("quantity >= 1", name="ck_wish_quantity"),
        CheckConstraint("price_pence IS NULL OR price_pence >= 0", name="ck_wish_price"),
        CheckConstraint("priority BETWEEN 1 AND 3", name="ck_wish_priority"),
    )
