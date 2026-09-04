from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_campaigns: Mapped[list["Campaign"]] = relationship(
        "Campaign", back_populates="created_by"
    )
    campaign_members: Mapped[list["CampaignMember"]] = relationship(
        "CampaignMember", back_populates="user"
    )


if TYPE_CHECKING:
    from app.models.campaign import Campaign, CampaignMember
