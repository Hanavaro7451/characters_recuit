from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnprocessableError,
)
from app.domain.enums import CampaignMemberRole, CampaignStatus, CharacterStatus
from app.models.ability_roll import AbilityRollSet
from app.models.campaign import Campaign, CampaignMember
from app.models.catalog import BackgroundCatalog, ClassCatalog, SpeciesCatalog
from app.models.character import Character
from app.models.user import User
from app.repositories.ability_roll import AbilityRollRepository
from app.repositories.catalog import CatalogRepository
from app.repositories.character import CharacterRepository
from app.schemas.character import CharacterCreate, CharacterPatch
from app.services.ability_roll import generate_rolls


class CharacterService:
    """Проверки доступа и атомарное редактирование черновика."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = CharacterRepository(session)
        self.catalog = CatalogRepository(session)
        self.rolls = AbilityRollRepository(session)

    async def _membership(
        self, campaign_id: int, user: User, *, for_write: bool = False
    ) -> tuple[CampaignMember, Campaign]:
        result = await self.repo.membership(campaign_id, user.id, for_write=for_write)
        if result is None:
            raise NotFoundError("Кампания не найдена")
        return result

    @staticmethod
    def _require_write_access(member: CampaignMember, campaign: Campaign) -> None:
        if member.role != CampaignMemberRole.PLAYER:
            raise ForbiddenError("Действие доступно только игроку")
        if campaign.status != CampaignStatus.ACTIVE:
            raise ConflictError("Кампания завершена")

    async def _validate_catalog(self, values: dict[str, int]) -> None:
        if (
            "species_id" in values
            and await self.catalog.lock_available(SpeciesCatalog, values["species_id"])
            is None
        ):
            raise UnprocessableError("Вид недоступен для выбора")
        if (
            "class_catalog_id" in values
            and await self.catalog.lock_available(
                ClassCatalog, values["class_catalog_id"]
            )
            is None
        ):
            raise UnprocessableError("Класс недоступен для выбора")
        if (
            "background_id" in values
            and await self.catalog.lock_available(
                BackgroundCatalog, values["background_id"]
            )
            is None
        ):
            raise UnprocessableError("Предыстория недоступна для выбора")

    async def create(
        self, campaign_id: int, user: User, payload: CharacterCreate
    ) -> Character:
        member, campaign = await self._membership(campaign_id, user, for_write=True)
        self._require_write_access(member, campaign)
        if await self.repo.get_by_member(member.id) is not None:
            raise ConflictError("Персонаж для этого членства уже существует")
        catalog_ids = payload.model_dump(exclude={"name"})
        await self._validate_catalog(catalog_ids)
        character = Character(
            campaign_member_id=member.id,
            name=payload.name,
            **catalog_ids,
        )
        try:
            await self.repo.create(character)
            await self.session.commit()
        except IntegrityError as error:
            await self.session.rollback()
            raise ConflictError("Персонаж для этого членства уже существует") from error
        result = await self.repo.get(campaign_id, character.id)
        assert result is not None
        return result

    async def get(self, campaign_id: int, character_id: int, user: User) -> Character:
        member, _ = await self._membership(campaign_id, user)
        character = await self.repo.get(campaign_id, character_id)
        if character is None:
            raise NotFoundError("Персонаж не найден")
        if (
            member.role != CampaignMemberRole.MASTER
            and character.campaign_member_id != member.id
        ):
            raise NotFoundError("Персонаж не найден")
        return character

    async def patch(
        self,
        campaign_id: int,
        character_id: int,
        user: User,
        payload: CharacterPatch,
    ) -> Character:
        member, campaign = await self._membership(campaign_id, user, for_write=True)
        character = await self.repo.get(campaign_id, character_id)
        if character is None:
            raise NotFoundError("Персонаж не найден")
        if (
            member.role != CampaignMemberRole.MASTER
            and character.campaign_member_id != member.id
        ):
            raise NotFoundError("Персонаж не найден")
        if member.role != CampaignMemberRole.PLAYER:
            raise ForbiddenError("Действие доступно только игроку")
        self._require_write_access(member, campaign)
        if character.status != CharacterStatus.DRAFT:
            raise ConflictError("Редактирование доступно только для черновика")
        changes = payload.model_dump(exclude_unset=True, exclude={"expected_version"})
        catalog_ids = {
            key: value for key, value in changes.items() if key.endswith("_id")
        }
        await self._validate_catalog(catalog_ids)
        success = await self.repo.update_draft(
            character_id=character_id,
            member_id=member.id,
            expected_version=payload.expected_version,
            changes=changes,
        )
        if not success:
            await self.session.rollback()
            raise ConflictError("Версия черновика устарела")
        await self.session.commit()
        self.session.expire_all()
        result = await self.repo.get(campaign_id, character_id)
        assert result is not None
        return result

    async def get_ability_rolls(
        self, campaign_id: int, character_id: int, user: User
    ) -> AbilityRollSet:
        """Прочитать набор владельцу либо мастеру той же кампании."""
        await self.get(campaign_id, character_id, user)
        roll_set = await self.rolls.get(character_id)
        if roll_set is None:
            raise NotFoundError("Набор бросков не найден")
        return roll_set

    async def generate_ability_rolls(
        self, campaign_id: int, character_id: int, user: User
    ) -> tuple[AbilityRollSet, bool]:
        """Сохранить единственный набор под блокировкой строки персонажа."""
        member, campaign = await self._membership(campaign_id, user, for_write=True)
        character = await self.repo.lock_for_rolls(campaign_id, character_id)
        if character is None or (
            member.role != CampaignMemberRole.MASTER
            and character.campaign_member_id != member.id
        ):
            raise NotFoundError("Персонаж не найден")
        if member.role != CampaignMemberRole.PLAYER:
            raise ForbiddenError("Действие доступно только игроку")
        if campaign.status != CampaignStatus.ACTIVE:
            raise ConflictError("Кампания завершена")
        if character.status != CharacterStatus.DRAFT:
            raise ConflictError("Генерация доступна только для черновика")
        existing = await self.rolls.get(character_id)
        if existing is not None:
            return existing, False
        await self.rolls.create(character_id, generate_rolls())
        character.version += 1
        await self.session.commit()
        saved = await self.rolls.get(character_id)
        assert saved is not None
        return saved, True
