from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator


class AuthenticatedIdentity(BaseModel):
    email: str


class Role(StrEnum):
    ADMIN = "admin"
    STUDENT = "student"
    CHECK_IN = "checkin"


class ActivityStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"


class CheckInQrLookup(BaseModel):
    token: str = Field(min_length=43, max_length=43, pattern=r"^[A-Za-z0-9_-]{43}$")
    activity_id: int | None = Field(default=None, ge=1)


class ActivityCategory(StrEnum):
    TALK = "talk"
    WORKSHOP = "workshop"
    CLUB = "club"
    CULTURE = "culture"
    SPORTS = "sports"
    CAREER = "career"
    OTHER = "other"


class User(BaseModel):
    id: int
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    display_name: str
    role: Role


class UserProvision(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    display_name: str = Field(min_length=1, max_length=255)
    role: Role
    password: str | None = Field(default=None, min_length=12, max_length=128)


class AccountRegistration(BaseModel):
    email: str = Field(
        min_length=3,
        max_length=320,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    display_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=12, max_length=128)


class PasswordLogin(BaseModel):
    email: str = Field(
        min_length=3,
        max_length=320,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    password: str = Field(min_length=1, max_length=128)


class ActivityCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=10000)
    location: str = Field(min_length=1, max_length=255)
    organizer: str = Field(min_length=1, max_length=255)
    category: ActivityCategory = ActivityCategory.OTHER
    capacity: int = Field(ge=1, le=100000)
    duration: str = Field(default="", max_length=100)
    starts_at: datetime
    ends_at: datetime | None = None
    registration_opens_at: datetime | None = None
    registration_deadline: datetime

    @field_validator("starts_at", "registration_deadline")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Datetime values must include a timezone.")
        return value

    @field_validator("ends_at", "registration_opens_at")
    @classmethod
    def require_optional_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Datetime values must include a timezone.")
        return value

    @model_validator(mode="after")
    def validate_time_ranges(self) -> "ActivityCreate":
        if self.ends_at is not None and self.ends_at <= self.starts_at:
            raise ValueError("Activity end must be after its start.")
        if self.registration_opens_at is not None:
            if self.registration_opens_at > self.registration_deadline:
                raise ValueError("Registration opening must not be after its deadline.")
            if self.registration_deadline > self.starts_at:
                raise ValueError("Registration deadline must not be after the activity start.")
        return self

class ActivityUpdate(ActivityCreate):
    pass


class ActivityReview(BaseModel):
    approved: bool
    note: str | None = Field(default=None, max_length=2000)


class NoteCreate(BaseModel):
    title: str
    content: str


class Note(NoteCreate):
    id: int
    created_at: datetime | None = None
