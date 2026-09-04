from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import CampaignMemberRole, CampaignStatus
from app.models.base import Base, TimestampMixin


class Campaign(Base, TimestampMixin):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[CampaignStatus] = mapped_column(
        Enum(CampaignStatus), default=CampaignStatus.ACTIVE
    )
    invite_code: Mapped[str] = mapped_column(String(255), unique=True)
    created_by_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    created_by: Mapped["User"] = relationship(
        "User", back_populates="created_campaigns"
    )
    campaign_members: Mapped[list["CampaignMember"]] = relationship(
        "CampaignMember", back_populates="campaign"
    )


class CampaignMember(Base, TimestampMixin):
    __tablename__ = "campaign_members"
    __table_args__ = (
        UniqueConstraint("campaign_id", "user_id", name="uix_campaign_user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(Integer, ForeignKey("campaigns.id"))
    campaign: Mapped["Campaign"] = relationship(
        "Campaign", back_populates="campaign_members"
    )
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    user: Mapped["User"] = relationship("User", back_populates="campaign_members")
    role: Mapped[CampaignMemberRole] = mapped_column(Enum(CampaignMemberRole))


if TYPE_CHECKING:
    from app.models.user import User
