import json
import json
from dataclasses import dataclass
from typing import List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from wh40k_bot.db import ArmyList, ArmyListRepository, UserRepository
from wh40k_bot.services.datasource_service import validate_army_list, update_army_list_from_datasources
from wh40k_bot.services.datasource_service import detect_army_format, normalize_gdc_format


@dataclass
class UnitInfo:
    """Информация о юните"""
    name: str
    points: int
    models: int
    is_warlord: bool = False
    enhancement_name: Optional[str] = None
    enhancement_cost: int = 0


@dataclass
class ParsedArmyList:
    """Распарсенный список армии"""
    name: str
    faction: Optional[str]
    total_points: int
    units: List[UnitInfo]


def parse_army_list_json(json_data) -> ParsedArmyList:
    """Парсит JSON файл списка армии из game-datacards (datasource или GDC list формат). Принимает str или dict."""

    if isinstance(json_data, str):
        data = json.loads(json_data)
    else:
        data = json_data

    if detect_army_format(data) == "gdc":
        data = normalize_gdc_format(data)

    name = data.get("name", "Без названия")
    faction = None
    total_points = 0
    units = []
    
    # Данные находятся в data[0].datasheets
    if "data" in data and len(data["data"]) > 0:
        roster = data["data"][0]
        datasheets = roster.get("datasheets", [])
        
        for unit in datasheets:
            unit_name = unit.get("name", "Unknown")
            
            # Получаем фракцию из первого юнита
            if faction is None and "factions" in unit and len(unit["factions"]) > 0:
                faction = unit["factions"][0]
            
            # Проверяем warlord
            is_warlord = unit.get("isWarlord", False)
            
            # Проверяем энхансмент
            enhancement = unit.get("selectedEnhancement")
            enhancement_name = None
            enhancement_cost = 0
            if enhancement:
                enhancement_name = enhancement.get("name")
                enhancement_cost = int(enhancement.get("cost", 0))
            
            # Получаем очки из unitSize если есть, иначе из points
            unit_size = unit.get("unitSize", {})
            if unit_size and "cost" in unit_size:
                points = int(unit_size["cost"])
                models = int(unit_size.get("models", 1))
            elif "points" in unit and len(unit["points"]) > 0:
                # Берём первый активный вариант
                for pt in unit["points"]:
                    if pt.get("active", True):
                        points = int(pt.get("cost", 0))
                        models = int(pt.get("models", 1))
                        break
                else:
                    points = 0
                    models = 1
            else:
                points = 0
                models = 1
            
            # Добавляем стоимость энхансмента к очкам юнита
            unit_total_points = points + enhancement_cost
            total_points += unit_total_points
            
            units.append(UnitInfo(
                name=unit_name, 
                points=unit_total_points, 
                models=models,
                is_warlord=is_warlord,
                enhancement_name=enhancement_name,
                enhancement_cost=enhancement_cost
            ))
    
    return ParsedArmyList(
        name=name,
        faction=faction,
        total_points=total_points,
        units=units
    )


def format_army_list_short(army_list: ArmyList) -> str:
    """Короткое описание списка армии"""
    return f"📋 <b>{army_list.name}</b>\n⚔️ {army_list.faction or 'Unknown'} | {army_list.total_points} pts"


def format_army_list_full(army_list: ArmyList) -> str:
    """Полное описание списка армии с юнитами"""
    lines = [
        f"📋 <b>{army_list.name}</b>",
        f"⚔️ Фракция: {army_list.faction or 'Unknown'}",
    ]
    
    if army_list.detachment:
        lines.append(f"🎖 Detachment: {army_list.detachment}")
    
    lines.append(f"🎯 Всего очков: {army_list.total_points}")
    
    if army_list.datasources_version:
        lines.append(f"📦 Версия данных: {army_list.datasources_version}")
    
    lines.append("")
    lines.append("<b>Юниты:</b>")
    
    try:
        parsed = parse_army_list_json(army_list.json_data)
        for unit in parsed.units:
            models_str = f" x{unit.models}" if unit.models > 1 else ""
            warlord_str = " 👑" if unit.is_warlord else ""
            enhancement_str = f" (+{unit.enhancement_name})" if unit.enhancement_name else ""
            lines.append(f"  • {unit.name}{models_str}{warlord_str}{enhancement_str} — {unit.points} pts")
    except Exception as e:
        lines.append(f"  <i>Ошибка парсинга: {e}</i>")
    
    return "\n".join(lines)


class ArmyListService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)
        self.army_list_repo = ArmyListRepository(session)
    
    async def create_army_list(self, telegram_id: int, json_str: str, skip_validation: bool = False) -> Optional[ArmyList]:
        """Создать список армии из JSON с валидацией по datasources"""
        from wh40k_bot.services.datasource_service import get_datasources_version
        
        user = await self.user_repo.get_by_telegram_id(telegram_id)
        if not user:
            return None
        
        # Парсим JSON в dict
        try:
            json_data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Невалидный JSON: {e}")
        
        # Валидация по datasources
        validation = validate_army_list(json_data)
        if not skip_validation and not validation.valid:
            raise ValueError("Валидация не пройдена:\n" + "\n".join(validation.errors))
        
        army_list = await self.army_list_repo.create(
            user_id=user.id,
            name=json_data.get("name", "Без названия"),
            faction=validation.faction,
            detachment=validation.detachment,
            total_points=validation.total_points,
            json_data=json_data,
            datasources_version=get_datasources_version()
        )
        
        await self.session.commit()
        return army_list
    
    async def get_user_army_lists(self, telegram_id: int) -> List[ArmyList]:
        """Получить все списки армий пользователя"""
        return await self.army_list_repo.get_by_user_telegram_id(telegram_id)
    
    async def get_army_list(self, army_list_id: int) -> Optional[ArmyList]:
        """Получить список армии по ID"""
        return await self.army_list_repo.get_by_id(army_list_id)
    
    async def delete_army_list(self, telegram_id: int, army_list_id: int) -> bool:
        """Удалить список армии (проверяя владельца)"""
        army_list = await self.army_list_repo.get_by_id(army_list_id)
        if not army_list:
            return False
        
        user = await self.user_repo.get_by_telegram_id(telegram_id)
        if not user or army_list.user_id != user.id:
            return False
        
        result = await self.army_list_repo.delete(army_list_id)
        await self.session.commit()
        return result
    
    async def get_army_list_stats(self, army_list_id: int) -> dict:
        """Получить статистику списка армии"""
        return await self.army_list_repo.get_stats(army_list_id)
    
    async def validate_army_list_for_game(self, army_list_id: int) -> Tuple[bool, List[str]]:
        """
        Валидировать список армии перед прикреплением к игре.
        Проверяет актуальность данных по текущим datasources.
        """
        army_list = await self.army_list_repo.get_by_id(army_list_id)
        if not army_list:
            return False, ["Список армии не найден"]
        
        # Валидируем по текущим datasources
        validation = validate_army_list(army_list.json_data)
        
        if not validation.valid:
            return False, validation.errors
        
        # Проверяем версию datasources
        from wh40k_bot.services.datasource_service import get_datasources_version
        current_version = get_datasources_version()
        
        warnings = []
        if army_list.datasources_version and current_version:
            if army_list.datasources_version != current_version:
                warnings.append(
                    f"⚠️ Список создан для версии {army_list.datasources_version}, "
                    f"текущая версия {current_version}. Рекомендуется обновить список."
                )
        
        return True, warnings
    
    async def update_army_list_from_datasources(self, telegram_id: int, army_list_id: int) -> Tuple[bool, List[str]]:
        """Обновить список армии данными из datasources"""
        army_list = await self.army_list_repo.get_by_id(army_list_id)
        if not army_list:
            return False, ["Список не найден"]
        
        user = await self.user_repo.get_by_telegram_id(telegram_id)
        if not user or army_list.user_id != user.id:
            return False, ["Нет доступа к этому списку"]
        
        # Обновляем JSON
        updated_json, changes = update_army_list_from_datasources(army_list.json_data)
        
        # Валидируем обновлённые данные
        validation = validate_army_list(updated_json)
        
        # Обновляем в БД
        from wh40k_bot.services.datasource_service import get_datasources_version
        
        army_list.json_data = updated_json
        army_list.total_points = validation.total_points
        army_list.faction = validation.faction
        army_list.detachment = validation.detachment
        army_list.datasources_version = get_datasources_version()
        
        await self.session.commit()
        
        return True, changes
