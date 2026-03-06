"""
Генератор карточек юнитов в стиле game-datacards.
"""
import io
import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

# Цвета
COLORS = {
    "background": "#1a1a1a",
    "header": "#2d2d2d", 
    "stat_box": "#3a3a3a",
    "stat_value_bg": "#4a4a4a",
    "text_white": "#ffffff",
    "text_gray": "#b0b0b0",
    "text_light": "#d0d0d0",
    "accent_red": "#8b0000",
    "accent_dark_red": "#5a0000",
    "table_header": "#4a0000",
    "table_row_odd": "#2a2a2a",
    "table_row_even": "#1f1f1f",
    "border": "#5a5a5a",
    "border_light": "#707070",
    "invuln_shield": "#d4af37",
    "damaged_bg": "#3d1515",
    "keywords_bg": "#1a1a1a",
    "faction_bg": "#4a0000",
    "enhancement_bg": "#1a3a1a",
    "enhancement_border": "#2a5a2a",
    "detachment_bg": "#1a1a3a",
    "detachment_border": "#3a3a6a",
}

# Увеличенные размеры (x2)
SCALE = 2
CARD_WIDTH = 900 * SCALE
CARD_MIN_HEIGHT = 700 * SCALE
PADDING = 20 * SCALE
STAT_BOX_WIDTH = 70 * SCALE
STAT_BOX_HEIGHT = 80 * SCALE
HEADER_HEIGHT = 100 * SCALE

# Размеры шрифтов (увеличены)
FONT_SIZE_TITLE = 32 * SCALE
FONT_SIZE_POINTS = 28 * SCALE
FONT_SIZE_STAT_LABEL = 14 * SCALE
FONT_SIZE_STAT_VALUE = 28 * SCALE
FONT_SIZE_TABLE_HEADER = 14 * SCALE
FONT_SIZE_TABLE_CELL = 13 * SCALE
FONT_SIZE_ABILITY_TITLE = 14 * SCALE
FONT_SIZE_ABILITY = 12 * SCALE
FONT_SIZE_KEYWORDS = 14 * SCALE
FONT_SIZE_SMALL = 11 * SCALE
FONT_SIZE_INVULN = 22 * SCALE


def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Получить шрифт"""
    font_paths_bold = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    font_paths_regular = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]
    
    paths = font_paths_bold if bold else font_paths_regular
    
    for path in paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except:
                continue
    
    return ImageFont.load_default()


@dataclass
class WeaponProfile:
    """Профиль оружия"""
    name: str
    range: str
    attacks: str
    skill: str
    strength: str
    ap: str
    damage: str
    keywords: List[str]


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Конвертировать HEX в RGB"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def parse_weapon_profiles(weapons: List[Dict]) -> List[WeaponProfile]:
    """Парсинг профилей оружия"""
    profiles = []
    
    for weapon in weapons:
        if not weapon.get("active", True):
            continue
        
        for profile in weapon.get("profiles", []):
            if not profile.get("active", True):
                continue
            
            keywords = profile.get("keywords", [])
            
            profiles.append(WeaponProfile(
                name=profile.get("name", "Unknown"),
                range=profile.get("range", "-"),
                attacks=profile.get("attacks", "-"),
                skill=profile.get("skill", "-"),
                strength=profile.get("strength", "-"),
                ap=profile.get("ap", "0"),
                damage=profile.get("damage", "-"),
                keywords=keywords
            ))
    
    return profiles


def draw_stat_box(draw: ImageDraw, x: int, y: int, label: str, value: str, fonts: dict) -> int:
    """Нарисовать бокс со статом"""
    width = STAT_BOX_WIDTH
    height = STAT_BOX_HEIGHT
    
    # Фон лейбла (верхняя часть)
    label_height = 22 * SCALE
    draw.rectangle([x, y, x + width, y + label_height], fill=COLORS["stat_box"])
    
    # Фон значения (нижняя часть)
    draw.rectangle([x, y + label_height, x + width, y + height], fill=COLORS["stat_value_bg"])
    
    # Рамка
    draw.rectangle([x, y, x + width, y + height], outline=COLORS["border"], width=2)
    draw.line([x, y + label_height, x + width, y + label_height], fill=COLORS["border"], width=1)
    
    # Текст лейбла (по центру)
    label_bbox = draw.textbbox((0, 0), label, font=fonts["stat_label"])
    label_w = label_bbox[2] - label_bbox[0]
    draw.text((x + (width - label_w) // 2, y + 3 * SCALE), label, fill=COLORS["text_gray"], font=fonts["stat_label"])
    
    # Текст значения (по центру)
    value_bbox = draw.textbbox((0, 0), str(value), font=fonts["stat_value"])
    value_w = value_bbox[2] - value_bbox[0]
    value_h = value_bbox[3] - value_bbox[1]
    value_y = y + label_height + (height - label_height - value_h) // 2 - 5 * SCALE
    draw.text((x + (width - value_w) // 2, value_y), str(value), fill=COLORS["text_white"], font=fonts["stat_value"])
    
    return height


def draw_invuln_save(draw: ImageDraw, x: int, y: int, value: str, fonts: dict) -> int:
    """Нарисовать invulnerable save (щит)"""
    size = 55 * SCALE
    
    # Рисуем щит (шестиугольник)
    points = [
        (x + size // 2, y),
        (x + size, y + size // 4),
        (x + size, y + size * 3 // 4),
        (x + size // 2, y + size),
        (x, y + size * 3 // 4),
        (x, y + size // 4),
    ]
    draw.polygon(points, fill=COLORS["invuln_shield"], outline=COLORS["border_light"])
    
    # Значение в центре
    value_bbox = draw.textbbox((0, 0), value, font=fonts["invuln"])
    value_w = value_bbox[2] - value_bbox[0]
    value_h = value_bbox[3] - value_bbox[1]
    draw.text(
        (x + (size - value_w) // 2, y + (size - value_h) // 2 - 3 * SCALE),
        value, 
        fill=COLORS["background"], 
        font=fonts["invuln"]
    )
    
    # Подпись
    draw.text((x - 5 * SCALE, y + size + 5 * SCALE), "INVULNERABLE", fill=COLORS["text_gray"], font=fonts["small"])
    draw.text((x + 10 * SCALE, y + size + 18 * SCALE), "SAVE", fill=COLORS["text_gray"], font=fonts["small"])
    
    return size + 35 * SCALE


def draw_weapons_table(draw: ImageDraw, x: int, y: int, width: int, 
                        profiles: List[WeaponProfile], weapon_type: str,
                        fonts: dict) -> int:
    """Нарисовать таблицу оружия"""
    if not profiles:
        return 0
    
    # Колонки
    if weapon_type == "ranged":
        headers = ["RANGED WEAPONS", "RANGE", "A", "BS", "S", "AP", "D"]
    else:
        headers = ["MELEE WEAPONS", "RANGE", "A", "WS", "S", "AP", "D"]
    
    # Ширины колонок
    name_width = width - 320 * SCALE
    col_widths = [name_width, 60 * SCALE, 45 * SCALE, 45 * SCALE, 45 * SCALE, 45 * SCALE, 45 * SCALE]
    
    row_height = 28 * SCALE
    header_height = 26 * SCALE
    
    # Заголовок секции
    icon = ">>" if weapon_type == "ranged" else "X"
    draw.rectangle([x, y, x + width, y + header_height], fill=COLORS["table_header"])
    draw.text((x + 8 * SCALE, y + 5 * SCALE), f"{icon} {headers[0]}", fill=COLORS["text_white"], font=fonts["table_header"])
    
    # Заголовки колонок
    col_x = x + col_widths[0]
    for i, header in enumerate(headers[1:], 1):
        header_bbox = fonts["table_header"].getbbox(header)
        header_w = header_bbox[2] - header_bbox[0]
        draw.text((col_x + (col_widths[i] - header_w) // 2, y + 5 * SCALE), header, 
                  fill=COLORS["text_white"], font=fonts["table_header"])
        col_x += col_widths[i]
    
    current_y = y + header_height
    
    # Строки с оружием
    for idx, profile in enumerate(profiles):
        bg_color = COLORS["table_row_odd"] if idx % 2 == 0 else COLORS["table_row_even"]
        draw.rectangle([x, current_y, x + width, current_y + row_height], fill=bg_color)
        
        # Имя оружия
        name_text = profile.name
        if profile.keywords:
            kw_str = ", ".join(profile.keywords)
            name_text = f"{profile.name}"
            # Keywords в скобках меньшим шрифтом
            name_bbox = fonts["table_cell"].getbbox(name_text)
            draw.text((x + 8 * SCALE, current_y + 6 * SCALE), name_text, fill=COLORS["text_white"], font=fonts["table_cell"])
            
            kw_text = f" [{kw_str}]"
            kw_x = x + 8 * SCALE + name_bbox[2] - name_bbox[0]
            # Обрезаем если слишком длинно
            max_kw_width = col_widths[0] - (kw_x - x) - 10 * SCALE
            while fonts["small"].getbbox(kw_text)[2] > max_kw_width and len(kw_text) > 10:
                kw_text = kw_text[:-5] + "...]"
            draw.text((kw_x, current_y + 8 * SCALE), kw_text, fill=COLORS["text_gray"], font=fonts["small"])
        else:
            draw.text((x + 8 * SCALE, current_y + 6 * SCALE), name_text, fill=COLORS["text_white"], font=fonts["table_cell"])
        
        # Значения
        values = [profile.range, profile.attacks, profile.skill, profile.strength, profile.ap, profile.damage]
        col_x = x + col_widths[0]
        
        for i, value in enumerate(values):
            val_bbox = fonts["table_cell"].getbbox(str(value))
            val_w = val_bbox[2] - val_bbox[0]
            draw.text((col_x + (col_widths[i + 1] - val_w) // 2, current_y + 6 * SCALE), 
                      str(value), fill=COLORS["text_white"], font=fonts["table_cell"])
            col_x += col_widths[i + 1]
        
        current_y += row_height
    
    # Рамка таблицы
    draw.rectangle([x, y, x + width, current_y], outline=COLORS["border"], width=1)
    
    return current_y - y


def draw_abilities(draw: ImageDraw, x: int, y: int, width: int, 
                   abilities: dict, fonts: dict) -> int:
    """Нарисовать блок способностей"""
    current_y = y
    line_height = 18 * SCALE
    
    # Заголовок
    header_height = 26 * SCALE
    draw.rectangle([x, current_y, x + width, current_y + header_height], fill=COLORS["table_header"])
    draw.text((x + 8 * SCALE, current_y + 5 * SCALE), "ABILITIES", fill=COLORS["text_white"], font=fonts["table_header"])
    current_y += header_height + 8 * SCALE
    
    # Core abilities - в виде блока
    core = abilities.get("core", [])
    if core:
        block_height = 28 * SCALE
        draw.rectangle([x, current_y, x + width, current_y + block_height], 
                       fill=COLORS["table_row_odd"], outline=COLORS["border"], width=1)
        draw.text((x + 8 * SCALE, current_y + 6 * SCALE), "CORE:", fill=COLORS["text_gray"], font=fonts["ability_bold"])
        core_text = f" {', '.join(core)}"
        draw.text((x + 70 * SCALE, current_y + 6 * SCALE), core_text, fill=COLORS["text_light"], font=fonts["ability"])
        current_y += block_height + 5 * SCALE
    
    # Faction abilities - в виде блока
    faction = abilities.get("faction", [])
    if faction:
        block_height = 28 * SCALE
        draw.rectangle([x, current_y, x + width, current_y + block_height], 
                       fill=COLORS["table_row_odd"], outline=COLORS["border"], width=1)
        draw.text((x + 8 * SCALE, current_y + 6 * SCALE), "FACTION:", fill=COLORS["text_gray"], font=fonts["ability_bold"])
        faction_text = f" {', '.join(faction)}"
        draw.text((x + 95 * SCALE, current_y + 6 * SCALE), faction_text, fill=COLORS["text_light"], font=fonts["ability"])
        current_y += block_height + 5 * SCALE
    
    current_y += 5 * SCALE
    
    # Other abilities - каждая в отдельном блоке
    other = abilities.get("other", [])
    for ability in other:
        if not ability.get("showAbility", True):
            continue
        
        name = ability.get("name", "")
        desc = ability.get("description", "")
        
        # Рассчитываем высоту блока для этой способности
        block_start_y = current_y
        inner_y = current_y + 8 * SCALE
        
        # Название способности
        draw.text((x + 10 * SCALE, inner_y), f"{name}", fill=COLORS["text_white"], font=fonts["ability_bold"])
        inner_y += line_height + 2 * SCALE
        
        # Описание
        if ability.get("showDescription", True) and desc:
            words = desc.split()
            line = ""
            max_width = width - 20 * SCALE
            for word in words:
                test_line = f"{line} {word}".strip()
                if fonts["ability"].getbbox(test_line)[2] > max_width:
                    draw.text((x + 10 * SCALE, inner_y), line, fill=COLORS["text_gray"], font=fonts["ability"])
                    inner_y += line_height - 4 * SCALE
                    line = word
                else:
                    line = test_line
            if line:
                draw.text((x + 10 * SCALE, inner_y), line, fill=COLORS["text_gray"], font=fonts["ability"])
                inner_y += line_height
        
        inner_y += 5 * SCALE
        
        # Рисуем фон блока
        block_height = inner_y - block_start_y
        draw.rectangle([x, block_start_y, x + width, block_start_y + block_height], 
                       fill=COLORS["table_row_even"], outline=COLORS["border"], width=1)
        
        # Перерисовываем текст поверх фона
        inner_y = block_start_y + 8 * SCALE
        draw.text((x + 10 * SCALE, inner_y), f"{name}", fill=COLORS["text_white"], font=fonts["ability_bold"])
        inner_y += line_height + 2 * SCALE
        
        if ability.get("showDescription", True) and desc:
            words = desc.split()
            line = ""
            max_width = width - 20 * SCALE
            for word in words:
                test_line = f"{line} {word}".strip()
                if fonts["ability"].getbbox(test_line)[2] > max_width:
                    draw.text((x + 10 * SCALE, inner_y), line, fill=COLORS["text_gray"], font=fonts["ability"])
                    inner_y += line_height - 4 * SCALE
                    line = word
                else:
                    line = test_line
            if line:
                draw.text((x + 10 * SCALE, inner_y), line, fill=COLORS["text_gray"], font=fonts["ability"])
        
        current_y = block_start_y + block_height + 8 * SCALE
    
    return current_y - y


def draw_damaged(draw: ImageDraw, x: int, y: int, width: int, 
                 damaged: dict, fonts: dict) -> int:
    """Нарисовать блок Damaged"""
    if not damaged.get("showDamagedAbility", False):
        return 0
    
    range_text = damaged.get("range", "")
    description = damaged.get("description", "")
    
    height = 80 * SCALE
    
    # Фон
    draw.rectangle([x, y, x + width, y + height], fill=COLORS["damaged_bg"])
    draw.rectangle([x, y, x + width, y + height], outline=COLORS["accent_red"], width=3)
    
    # Иконка и заголовок
    draw.text((x + 8 * SCALE, y + 5 * SCALE), f"[!] DAMAGED: {range_text}", 
              fill=COLORS["text_white"], font=fonts["ability_bold"])
    
    # Описание
    current_y = y + 28 * SCALE
    line_height = 16 * SCALE
    words = description.split()
    line = ""
    max_width = width - 16 * SCALE
    for word in words:
        test_line = f"{line} {word}".strip()
        if fonts["ability"].getbbox(test_line)[2] > max_width:
            draw.text((x + 8 * SCALE, current_y), line, fill=COLORS["text_gray"], font=fonts["ability"])
            current_y += line_height
            line = word
        else:
            line = test_line
    if line:
        draw.text((x + 8 * SCALE, current_y), line, fill=COLORS["text_gray"], font=fonts["ability"])
    
    return height + 10 * SCALE


def draw_keywords(draw: ImageDraw, x: int, y: int, width: int, 
                  keywords: List[str], faction: str, fonts: dict) -> int:
    """Нарисовать блок keywords и faction"""
    padding = 12 * SCALE
    inner_padding = 8 * SCALE
    
    # Keywords блок
    keywords_block_height = 45 * SCALE
    draw.rectangle([x, y, x + width, y + keywords_block_height], 
                   fill=COLORS["table_row_odd"], outline=COLORS["border"], width=1)
    
    # Формируем текст keywords с переносом если нужно
    keywords_text = ", ".join(keywords)
    max_keywords_width = width - 2 * padding - 100 * SCALE  # Учитываем "KEYWORDS: "
    
    # Обрезаем если слишком длинно
    while fonts["keywords"].getbbox(keywords_text)[2] > max_keywords_width and len(keywords_text) > 20:
        keywords_text = keywords_text[:-4] + "..."
    
    draw.text((x + inner_padding, y + 8 * SCALE), "KEYWORDS:", 
              fill=COLORS["text_gray"], font=fonts["small"])
    draw.text((x + inner_padding, y + 22 * SCALE), keywords_text, 
              fill=COLORS["text_white"], font=fonts["keywords"])
    
    # Faction keywords блок - в одну строку
    faction_y = y + keywords_block_height + 5 * SCALE
    faction_block_height = 32 * SCALE
    draw.rectangle([x, faction_y, x + width, faction_y + faction_block_height], 
                   fill=COLORS["faction_bg"], outline=COLORS["border"], width=1)
    
    # FACTION: Adepta Sororitas - в одну строку
    faction_label = "FACTION: "
    draw.text((x + inner_padding, faction_y + 8 * SCALE), 
              faction_label, fill=COLORS["text_gray"], font=fonts["keywords"])
    
    # Позиция для названия фракции после "FACTION: "
    label_width = fonts["keywords"].getbbox(faction_label)[2]
    draw.text((x + inner_padding + label_width, faction_y + 8 * SCALE), 
              faction, fill=COLORS["text_white"], font=fonts["keywords"])
    
    # Общая высота с отступом снизу
    total_height = keywords_block_height + 5 * SCALE + faction_block_height + 30 * SCALE
    
    return total_height


def draw_enhancement(draw: ImageDraw, x: int, y: int, width: int, 
                     enhancement: dict, fonts: dict) -> int:
    """Нарисовать блок enhancement"""
    if not enhancement:
        return 0
    
    name = enhancement.get("name", "Unknown")
    cost = enhancement.get("cost", 0)
    description = enhancement.get("description", "")
    detachment = enhancement.get("detachment", "")
    
    # Заголовок
    header_height = 30 * SCALE
    draw.rectangle([x, y, x + width, y + header_height], fill=COLORS["enhancement_bg"])
    draw.rectangle([x, y, x + width, y + header_height], outline=COLORS["enhancement_border"], width=2)
    draw.text((x + 10 * SCALE, y + 6 * SCALE), f"[ENHANCEMENT] {name} (+{cost} pts)", 
              fill=COLORS["text_white"], font=fonts["ability_bold"])
    
    current_y = y + header_height + 5 * SCALE
    
    # Detachment
    if detachment:
        draw.text((x + 10 * SCALE, current_y), f"Detachment: {detachment}", 
                  fill=COLORS["text_gray"], font=fonts["ability"])
        current_y += 20 * SCALE
    
    # Описание
    if description:
        line_height = 16 * SCALE
        words = description.split()
        line = ""
        max_width = width - 20 * SCALE
        for word in words:
            test_line = f"{line} {word}".strip()
            if fonts["ability"].getbbox(test_line)[2] > max_width:
                draw.text((x + 10 * SCALE, current_y), line, fill=COLORS["text_gray"], font=fonts["ability"])
                current_y += line_height
                line = word
            else:
                line = test_line
        if line:
            draw.text((x + 10 * SCALE, current_y), line, fill=COLORS["text_gray"], font=fonts["ability"])
            current_y += line_height
    
    return current_y - y + 10 * SCALE


def calculate_weapons_table_height(profiles: List[WeaponProfile]) -> int:
    """Рассчитать высоту таблицы оружия"""
    if not profiles:
        return 0
    row_height = 28 * SCALE
    header_height = 26 * SCALE
    return header_height + len(profiles) * row_height


def calculate_abilities_height(abilities: dict, width: int, fonts: dict) -> int:
    """Рассчитать высоту блока способностей"""
    current_y = 0
    line_height = 18 * SCALE
    header_height = 26 * SCALE
    
    current_y += header_height + 8 * SCALE
    
    # Core - блок
    if abilities.get("core"):
        current_y += 28 * SCALE + 5 * SCALE
    
    # Faction - блок
    if abilities.get("faction"):
        current_y += 28 * SCALE + 5 * SCALE
    
    current_y += 5 * SCALE
    
    # Other abilities - каждая в отдельном блоке
    for ability in abilities.get("other", []):
        if not ability.get("showAbility", True):
            continue
        
        block_height = 8 * SCALE  # top padding
        block_height += line_height + 2 * SCALE  # name
        
        if ability.get("showDescription", True):
            desc = ability.get("description", "")
            if desc:
                max_width = width - 20 * SCALE
                words = desc.split()
                line = ""
                for word in words:
                    test_line = f"{line} {word}".strip()
                    if fonts["ability"].getbbox(test_line)[2] > max_width:
                        block_height += line_height - 4 * SCALE
                        line = word
                    else:
                        line = test_line
                if line:
                    block_height += line_height
        
        block_height += 5 * SCALE  # bottom padding
        current_y += block_height + 8 * SCALE  # block + margin
    
    return current_y


def calculate_damaged_height(damaged: dict) -> int:
    """Рассчитать высоту блока Damaged"""
    if not damaged.get("showDamagedAbility", False):
        return 0
    return 90 * SCALE


def calculate_enhancement_height(enhancement: dict, width: int, fonts: dict) -> int:
    """Рассчитать высоту блока enhancement"""
    if not enhancement:
        return 0
    
    header_height = 30 * SCALE
    current_y = header_height + 5 * SCALE
    
    if enhancement.get("detachment"):
        current_y += 20 * SCALE
    
    description = enhancement.get("description", "")
    if description:
        line_height = 16 * SCALE
        max_width = width - 20 * SCALE
        words = description.split()
        line = ""
        for word in words:
            test_line = f"{line} {word}".strip()
            if fonts["ability"].getbbox(test_line)[2] > max_width:
                current_y += line_height
                line = word
            else:
                line = test_line
        if line:
            current_y += line_height
    
    return current_y + 15 * SCALE


def generate_unit_card(unit_data: dict) -> bytes:
    """Сгенерировать карточку юнита"""
    # Шрифты
    fonts = {
        "title": get_font(FONT_SIZE_TITLE, bold=True),
        "points": get_font(FONT_SIZE_POINTS, bold=True),
        "stat_label": get_font(FONT_SIZE_STAT_LABEL),
        "stat_value": get_font(FONT_SIZE_STAT_VALUE, bold=True),
        "table_header": get_font(FONT_SIZE_TABLE_HEADER, bold=True),
        "table_cell": get_font(FONT_SIZE_TABLE_CELL),
        "ability": get_font(FONT_SIZE_ABILITY),
        "ability_bold": get_font(FONT_SIZE_ABILITY, bold=True),
        "keywords": get_font(FONT_SIZE_KEYWORDS),
        "small": get_font(FONT_SIZE_SMALL),
        "invuln": get_font(FONT_SIZE_INVULN, bold=True),
    }
    
    # Данные
    name = unit_data.get("name", "Unknown Unit")
    stats = unit_data.get("stats", [{}])[0] if unit_data.get("stats") else {}
    abilities = unit_data.get("abilities", {})
    ranged_weapons = unit_data.get("rangedWeapons", [])
    melee_weapons = unit_data.get("meleeWeapons", [])
    keywords = unit_data.get("keywords", [])
    factions = unit_data.get("factions", [])
    faction = factions[0] if factions else "Unknown"
    enhancement = unit_data.get("selectedEnhancement")
    is_warlord = unit_data.get("isWarlord", False)
    
    # Очки
    points = 0
    unit_size = unit_data.get("unitSize", {})
    if unit_size and "cost" in unit_size:
        points = int(unit_size["cost"])
    elif unit_data.get("points"):
        for pt in unit_data["points"]:
            if pt.get("active", True):
                points = int(pt.get("cost", 0))
                break
    
    if enhancement:
        points += int(enhancement.get("cost", 0))
    
    # Парсим оружие
    ranged_profiles = parse_weapon_profiles(ranged_weapons)
    melee_profiles = parse_weapon_profiles(melee_weapons)
    
    content_width = CARD_WIDTH - 2 * PADDING
    
    # === ТОЧНЫЙ РАСЧЁТ ВЫСОТЫ ===
    height = 0
    height += HEADER_HEIGHT  # Header
    height += PADDING  # Отступ после header
    height += STAT_BOX_HEIGHT  # Stats
    height += 25 * SCALE  # Отступ после stats
    
    # Ranged weapons
    ranged_height = calculate_weapons_table_height(ranged_profiles)
    if ranged_height > 0:
        height += ranged_height + 15 * SCALE
    
    # Melee weapons
    melee_height = calculate_weapons_table_height(melee_profiles)
    if melee_height > 0:
        height += melee_height + 15 * SCALE
    
    # Abilities
    abilities_height = calculate_abilities_height(abilities, content_width, fonts)
    height += abilities_height + 10 * SCALE
    
    # Damaged
    damaged_height = calculate_damaged_height(abilities.get("damaged", {}))
    if damaged_height > 0:
        height += damaged_height + 10 * SCALE
    
    # Enhancement
    enhancement_height = calculate_enhancement_height(enhancement, content_width, fonts)
    if enhancement_height > 0:
        height += enhancement_height + 10 * SCALE
    
    # Keywords
    height += 80 * SCALE
    
    # Небольшой запас
    height += 20 * SCALE
    
    # === СОЗДАЁМ ИЗОБРАЖЕНИЕ ===
    img = Image.new("RGB", (CARD_WIDTH, height), COLORS["background"])
    draw = ImageDraw.Draw(img)
    
    # === HEADER ===
    draw.rectangle([0, 0, CARD_WIDTH, HEADER_HEIGHT], fill=COLORS["header"])
    
    name_x = PADDING
    if is_warlord:
        draw.text((PADDING, 25 * SCALE), "[WARLORD]", fill=COLORS["invuln_shield"], font=fonts["small"])
        name_x = PADDING + 100 * SCALE
    
    draw.text((name_x, 25 * SCALE), name.upper(), fill=COLORS["text_white"], font=fonts["title"])
    
    points_text = f"{points} PTS"
    points_bbox = fonts["points"].getbbox(points_text)
    points_width = points_bbox[2] - points_bbox[0]
    points_x = CARD_WIDTH - points_width - 40 * SCALE
    draw.rectangle([points_x - 15 * SCALE, 15 * SCALE, CARD_WIDTH - 15 * SCALE, 65 * SCALE], fill=COLORS["accent_red"])
    draw.text((points_x, 22 * SCALE), points_text, fill=COLORS["text_white"], font=fonts["points"])
    
    current_y = HEADER_HEIGHT + PADDING
    
    # === STATS ===
    stat_labels = ["M", "T", "SV", "W", "LD", "OC"]
    stat_keys = ["m", "t", "sv", "w", "ld", "oc"]
    
    stat_x = PADDING
    for label, key in zip(stat_labels, stat_keys):
        value = stats.get(key, "-")
        draw_stat_box(draw, stat_x, current_y, label, str(value), fonts)
        stat_x += STAT_BOX_WIDTH + 8 * SCALE
    
    invul = abilities.get("invul", {})
    if invul.get("showInvulnerableSave") and invul.get("value"):
        invul_x = stat_x + 30 * SCALE
        draw_invuln_save(draw, invul_x, current_y, invul["value"], fonts)
    
    current_y += STAT_BOX_HEIGHT + 25 * SCALE
    
    # === RANGED WEAPONS ===
    if ranged_profiles:
        actual_height = draw_weapons_table(draw, PADDING, current_y, content_width, 
                                           ranged_profiles, "ranged", fonts)
        current_y += actual_height + 15 * SCALE
    
    # === MELEE WEAPONS ===
    if melee_profiles:
        actual_height = draw_weapons_table(draw, PADDING, current_y, content_width,
                                           melee_profiles, "melee", fonts)
        current_y += actual_height + 15 * SCALE
    
    # === ABILITIES ===
    actual_height = draw_abilities(draw, PADDING, current_y, content_width, abilities, fonts)
    current_y += actual_height + 10 * SCALE
    
    # === DAMAGED ===
    damaged = abilities.get("damaged", {})
    if damaged.get("showDamagedAbility"):
        actual_height = draw_damaged(draw, PADDING, current_y, content_width, damaged, fonts)
        current_y += actual_height + 10 * SCALE
    
    # === ENHANCEMENT ===
    if enhancement:
        actual_height = draw_enhancement(draw, PADDING, current_y, content_width, enhancement, fonts)
        current_y += actual_height + 10 * SCALE
    
    # === KEYWORDS (в самом низу) ===
    keywords_y = height - 80 * SCALE
    draw_keywords(draw, 0, keywords_y, CARD_WIDTH, keywords, faction, fonts)
    
    # Сохраняем
    output = io.BytesIO()
    img.save(output, format="PNG", quality=95)
    output.seek(0)
    
    return output.getvalue()


def extract_enhancements_info(army_list_data: dict) -> List[dict]:
    """Извлечь информацию об энхансментах из данных армии"""
    if "data" not in army_list_data or len(army_list_data["data"]) == 0:
        return []
    
    roster = army_list_data["data"][0]
    datasheets = roster.get("datasheets", [])
    
    enhancements = []
    
    for unit in datasheets:
        enh = unit.get("selectedEnhancement")
        if enh:
            enhancements.append({
                "name": enh.get("name"),
                "cost": enh.get("cost"),
                "description": enh.get("description", ""),
                "unit": unit.get("name")
            })
    
    return enhancements


def generate_army_cards(army_list_data: dict) -> List[bytes]:
    """Сгенерировать карточки для всех юнитов"""
    cards = []
    
    if "data" not in army_list_data or len(army_list_data["data"]) == 0:
        return cards
    
    roster = army_list_data["data"][0]
    datasheets = roster.get("datasheets", [])
    
    for unit in datasheets:
        try:
            card = generate_unit_card(unit)
            cards.append(card)
        except Exception as e:
            print(f"Error generating card for {unit.get('name', 'Unknown')}: {e}")
            continue
    
    return cards


def generate_army_rules_card(faction_data: dict) -> Optional[bytes]:
    """Сгенерировать карточку Army Rules из данных фракции"""
    if not faction_data:
        return None
    
    faction_name = faction_data.get("name", "Unknown Faction")
    rules = faction_data.get("rules", {})
    army_rules = rules.get("army", [])
    
    if not army_rules:
        return None
    
    fonts = {
        "title": get_font(FONT_SIZE_TITLE, bold=True),
        "subtitle": get_font(FONT_SIZE_POINTS, bold=True),
        "ability": get_font(FONT_SIZE_ABILITY),
        "ability_bold": get_font(FONT_SIZE_ABILITY, bold=True),
        "small": get_font(FONT_SIZE_SMALL),
    }
    
    # Рассчитываем высоту
    line_height = 18 * SCALE
    header_height = 110 * SCALE  # Увеличен для отступов
    height = header_height + PADDING
    
    for rule in army_rules:
        rule_name = rule.get("name", "")
        rule_items = rule.get("rules", [])
        
        height += 35 * SCALE  # Название правила
        
        for item in rule_items:
            item_type = item.get("type", "text")
            if item_type == "header":
                height += 25 * SCALE
            else:
                text = item.get("text", "")
                lines = len(text) // 80 + 1
                height += lines * line_height + 10 * SCALE
    
    height += 40 * SCALE
    
    # Создаём изображение
    img = Image.new("RGB", (CARD_WIDTH, height), COLORS["background"])
    draw = ImageDraw.Draw(img)
    
    # Header с увеличенными отступами
    draw.rectangle([0, 0, CARD_WIDTH, header_height], fill=COLORS["faction_bg"])
    draw.rectangle([0, 0, CARD_WIDTH, header_height], outline=COLORS["accent_red"], width=3)
    
    draw.text((PADDING + 10 * SCALE, 20 * SCALE), "[ARMY RULES]", fill=COLORS["text_gray"], font=fonts["small"])
    draw.text((PADDING + 10 * SCALE, 45 * SCALE), faction_name.upper(), fill=COLORS["text_white"], font=fonts["title"])
    
    current_y = header_height + PADDING
    content_width = CARD_WIDTH - 2 * PADDING
    
    # Rules
    for rule in army_rules:
        rule_name = rule.get("name", "")
        rule_items = rule.get("rules", [])
        
        # Название правила
        draw.rectangle([PADDING, current_y, CARD_WIDTH - PADDING, current_y + 30 * SCALE],
                       fill=COLORS["table_header"], outline=COLORS["border"])
        draw.text((PADDING + 10 * SCALE, current_y + 6 * SCALE), rule_name.upper(), 
                  fill=COLORS["text_white"], font=fonts["ability_bold"])
        current_y += 35 * SCALE
        
        # Элементы правила
        for item in rule_items:
            item_type = item.get("type", "text")
            text = item.get("text", "")
            
            if item_type == "header":
                draw.text((PADDING + 10 * SCALE, current_y), text, 
                          fill=COLORS["text_white"], font=fonts["ability_bold"])
                current_y += 25 * SCALE
            elif item_type == "quote":
                # Цитата - курсивом/серым
                draw.rectangle([PADDING, current_y, CARD_WIDTH - PADDING, current_y + 30 * SCALE],
                               fill=COLORS["table_row_odd"])
                draw.text((PADDING + 15 * SCALE, current_y + 6 * SCALE), text[:100] + "..." if len(text) > 100 else text, 
                          fill=COLORS["text_gray"], font=fonts["small"])
                current_y += 35 * SCALE
            else:
                # Обычный текст
                # Убираем markdown разметку
                clean_text = text.replace("**", "").replace("*", "").replace("■", "•")
                
                words = clean_text.split()
                line = ""
                max_width = content_width - 20 * SCALE
                for word in words:
                    test_line = f"{line} {word}".strip()
                    if fonts["ability"].getbbox(test_line)[2] > max_width:
                        draw.text((PADDING + 10 * SCALE, current_y), line, 
                                  fill=COLORS["text_gray"], font=fonts["ability"])
                        current_y += line_height
                        line = word
                    else:
                        line = test_line
                if line:
                    draw.text((PADDING + 10 * SCALE, current_y), line, 
                              fill=COLORS["text_gray"], font=fonts["ability"])
                    current_y += line_height + 5 * SCALE
    
    output = io.BytesIO()
    img.save(output, format="PNG", quality=95)
    output.seek(0)
    return output.getvalue()


def generate_stratagem_card(stratagem: dict, detachment_name: str) -> bytes:
    """Сгенерировать карточку стратагемы (вытянутая, как игральная карта)"""
    fonts = {
        "title": get_font(20 * SCALE, bold=True),
        "subtitle": get_font(14 * SCALE, bold=True),
        "ability": get_font(14 * SCALE),
        "ability_bold": get_font(14 * SCALE, bold=True),
        "small": get_font(12 * SCALE),
        "cost": get_font(16 * SCALE, bold=True),
    }
    
    name = stratagem.get("name", "Unknown")
    cost = stratagem.get("cost", 1)
    type_str = stratagem.get("type", "")
    when = stratagem.get("when", "")
    target = stratagem.get("target", "")
    effect = stratagem.get("effect", "")
    restrictions = stratagem.get("restrictions", "")
    
    # Цвет в зависимости от типа
    if "battle tactic" in type_str.lower():
        header_color = "#2d5a2d"  # Зелёный
        accent_color = "#4a8a4a"
    elif "strategic ploy" in type_str.lower():
        header_color = "#2d2d5a"  # Синий
        accent_color = "#4a4a8a"
    elif "epic deed" in type_str.lower():
        header_color = "#5a5a2d"  # Жёлтый
        accent_color = "#8a8a4a"
    else:
        header_color = COLORS["table_header"]
        accent_color = COLORS["accent_red"]
    
    # Ширина карточки уже (как игральная карта)
    card_width = 600 * SCALE
    card_padding = 15 * SCALE
    content_width = card_width - 2 * card_padding
    header_height = 70 * SCALE
    line_height = 16 * SCALE
    
    # Рассчитываем высоту
    height = header_height + card_padding
    
    sections = [("WHEN", when), ("TARGET", target), ("EFFECT", effect)]
    if restrictions:
        sections.append(("RESTRICTIONS", restrictions))
    
    for label, text in sections:
        if text:
            # Более точный расчёт строк
            words = text.split()
            line = ""
            lines_count = 1
            max_width = content_width - 20 * SCALE
            for word in words:
                test_line = f"{line} {word}".strip()
                if fonts["ability"].getbbox(test_line)[2] > max_width:
                    lines_count += 1
                    line = word
                else:
                    line = test_line
            height += 26 * SCALE + lines_count * line_height + 12 * SCALE
    
    height += 30 * SCALE
    
    # Создаём изображение
    img = Image.new("RGB", (card_width, height), COLORS["background"])
    draw = ImageDraw.Draw(img)
    
    # Рамка карточки
    draw.rectangle([0, 0, card_width - 1, height - 1], outline=accent_color, width=4)
    
    # Header
    draw.rectangle([0, 0, card_width, header_height], fill=header_color)
    draw.rectangle([0, 0, card_width, header_height], outline=accent_color, width=2)
    
    # Cost (слева) - компактный квадрат
    cost_size = 36 * SCALE
    cost_x = card_padding
    cost_y = (header_height - cost_size) // 2
    draw.rectangle([cost_x, cost_y, cost_x + cost_size, cost_y + cost_size],
                   fill=COLORS["background"], outline=COLORS["text_white"], width=2)
    
    # Число стоимости по центру
    cost_text = str(cost)
    cost_bbox = fonts["cost"].getbbox(cost_text)
    cost_w = cost_bbox[2] - cost_bbox[0]
    draw.text((cost_x + (cost_size - cost_w) // 2, cost_y + 4 * SCALE), 
              cost_text, fill=COLORS["text_white"], font=fonts["cost"])
    # CP под числом мелким шрифтом
    cp_bbox = fonts["small"].getbbox("CP")
    cp_w = cp_bbox[2] - cp_bbox[0]
    draw.text((cost_x + (cost_size - cp_w) // 2, cost_y + cost_size - 14 * SCALE), 
              "CP", fill=COLORS["text_gray"], font=fonts["small"])
    
    # Название и тип (справа от cost)
    text_x = cost_x + cost_size + 12 * SCALE
    draw.text((text_x, 10 * SCALE), name.upper(), fill=COLORS["text_white"], font=fonts["title"])
    draw.text((text_x, 34 * SCALE), type_str.upper(), fill=COLORS["text_gray"], font=fonts["small"])
    draw.text((text_x, 50 * SCALE), detachment_name, fill=COLORS["text_gray"], font=fonts["small"])
    
    current_y = header_height + card_padding
    
    # Секции с блоками
    for label, text in sections:
        if not text:
            continue
        
        # Заголовок секции
        draw.rectangle([card_padding, current_y, card_width - card_padding, current_y + 22 * SCALE],
                       fill=COLORS["stat_box"], outline=COLORS["border"])
        draw.text((card_padding + 8 * SCALE, current_y + 4 * SCALE), label + ":", 
                  fill=COLORS["text_white"], font=fonts["ability_bold"])
        current_y += 24 * SCALE
        
        # Блок текста
        block_start_y = current_y
        
        words = text.split()
        line = ""
        max_width = content_width - 20 * SCALE
        text_lines = []
        for word in words:
            test_line = f"{line} {word}".strip()
            if fonts["ability"].getbbox(test_line)[2] > max_width:
                text_lines.append(line)
                line = word
            else:
                line = test_line
        if line:
            text_lines.append(line)
        
        block_height = len(text_lines) * line_height + 14 * SCALE
        
        # Фон блока
        draw.rectangle([card_padding, block_start_y, card_width - card_padding, block_start_y + block_height],
                       fill=COLORS["table_row_even"], outline=COLORS["border"])
        
        # Текст
        text_y = block_start_y + 7 * SCALE
        for line in text_lines:
            draw.text((card_padding + 10 * SCALE, text_y), line, 
                      fill=COLORS["text_gray"], font=fonts["ability"])
            text_y += line_height
        
        current_y = block_start_y + block_height + 8 * SCALE
    
    output = io.BytesIO()
    img.save(output, format="PNG", quality=95)
    output.seek(0)
    return output.getvalue()


def generate_stratagems_cards(faction_data: dict, detachment_name: str) -> List[bytes]:
    """Сгенерировать карточки стратагем для детачмента"""
    cards = []
    
    if not faction_data:
        return cards
    
    # Стратагемы в корне JSON
    stratagems = faction_data.get("stratagems", [])
    
    for strat in stratagems:
        # Фильтруем по детачменту
        if strat.get("detachment", "").lower() == detachment_name.lower():
            try:
                card = generate_stratagem_card(strat, detachment_name)
                cards.append(card)
            except Exception as e:
                print(f"Error generating stratagem card: {e}")
                continue
    
    return cards


def generate_detachment_rules_card(faction_data: dict, detachment_name: str, enhancements: List[dict] = None) -> Optional[bytes]:
    """Сгенерировать объединённую карточку правил детачмента и энхансментов"""
    if not detachment_name:
        return None
    
    fonts = {
        "title": get_font(FONT_SIZE_TITLE, bold=True),
        "subtitle": get_font(FONT_SIZE_POINTS, bold=True),
        "ability": get_font(FONT_SIZE_ABILITY),
        "ability_bold": get_font(FONT_SIZE_ABILITY, bold=True),
        "small": get_font(FONT_SIZE_SMALL),
    }
    
    # Получаем правила детачмента из faction_data
    det_rules = []
    faction = ""
    if faction_data:
        rules = faction_data.get("rules", {})
        detachment_rules = rules.get("detachment", [])
        
        for det in detachment_rules:
            if det.get("detachment", "").lower() == detachment_name.lower():
                det_rules = det.get("rules", [])
                faction = det.get("faction", "")
                break
    
    # Рассчитываем высоту
    line_height = 18 * SCALE
    header_height = 110 * SCALE
    height = header_height + PADDING
    
    # Высота для правил детачмента
    for rule in det_rules:
        rule_items = rule.get("rules", [])
        height += 35 * SCALE  # Название правила
        for item in rule_items:
            text = item.get("text", "")
            lines = len(text) // 70 + 1
            height += lines * line_height + 10 * SCALE
    
    # Высота для энхансментов
    if enhancements:
        height += 40 * SCALE  # "ENHANCEMENTS IN USE:"
        height += len(enhancements) * 90 * SCALE
    
    height += 50 * SCALE  # Отступ снизу
    
    # Создаём изображение
    img = Image.new("RGB", (CARD_WIDTH, height), COLORS["background"])
    draw = ImageDraw.Draw(img)
    
    # Header
    draw.rectangle([0, 0, CARD_WIDTH, header_height], fill=COLORS["detachment_bg"])
    draw.rectangle([0, 0, CARD_WIDTH, header_height], outline=COLORS["detachment_border"], width=3)
    
    draw.text((PADDING + 10 * SCALE, 15 * SCALE), "[DETACHMENT]", fill=COLORS["text_gray"], font=fonts["small"])
    draw.text((PADDING + 10 * SCALE, 40 * SCALE), detachment_name.upper(), fill=COLORS["text_white"], font=fonts["title"])
    if faction:
        draw.text((PADDING + 10 * SCALE, 80 * SCALE), faction, fill=COLORS["text_gray"], font=fonts["subtitle"])
    
    current_y = header_height + PADDING
    content_width = CARD_WIDTH - 2 * PADDING
    
    # Detachment Rules
    for rule in det_rules:
        rule_name = rule.get("name", "")
        rule_items = rule.get("rules", [])
        
        # Название правила
        draw.rectangle([PADDING, current_y, CARD_WIDTH - PADDING, current_y + 30 * SCALE],
                       fill=COLORS["table_header"], outline=COLORS["border"])
        draw.text((PADDING + 10 * SCALE, current_y + 6 * SCALE), rule_name.upper(), 
                  fill=COLORS["text_white"], font=fonts["ability_bold"])
        current_y += 35 * SCALE
        
        # Элементы правила
        for item in rule_items:
            text = item.get("text", "")
            clean_text = text.replace("**", "").replace("*", "").replace("■", "•")
            
            words = clean_text.split()
            line = ""
            max_width = content_width - 20 * SCALE
            for word in words:
                test_line = f"{line} {word}".strip()
                if fonts["ability"].getbbox(test_line)[2] > max_width:
                    draw.text((PADDING + 10 * SCALE, current_y), line, 
                              fill=COLORS["text_gray"], font=fonts["ability"])
                    current_y += line_height
                    line = word
                else:
                    line = test_line
            if line:
                draw.text((PADDING + 10 * SCALE, current_y), line, 
                          fill=COLORS["text_gray"], font=fonts["ability"])
                current_y += line_height + 5 * SCALE
    
    # Enhancements section
    if enhancements:
        current_y += 15 * SCALE
        draw.text((PADDING, current_y), "ENHANCEMENTS IN USE:", fill=COLORS["text_white"], font=fonts["ability_bold"])
        current_y += 30 * SCALE
        
        for enh in enhancements:
            draw.rectangle([PADDING, current_y, CARD_WIDTH - PADDING, current_y + 80 * SCALE], 
                           fill=COLORS["enhancement_bg"], outline=COLORS["enhancement_border"])
            
            draw.text((PADDING + 10 * SCALE, current_y + 8 * SCALE), 
                      f"[+] {enh['name']} (+{enh['cost']} pts)", 
                      fill=COLORS["text_white"], font=fonts["ability_bold"])
            draw.text((PADDING + 10 * SCALE, current_y + 30 * SCALE), 
                      f"On: {enh['unit']}", 
                      fill=COLORS["text_gray"], font=fonts["ability"])
            
            # Краткое описание
            desc = enh.get("description", "")[:100]
            if len(enh.get("description", "")) > 100:
                desc += "..."
            draw.text((PADDING + 10 * SCALE, current_y + 50 * SCALE), 
                      desc, fill=COLORS["text_gray"], font=fonts["small"])
            
            current_y += 90 * SCALE
    
    output = io.BytesIO()
    img.save(output, format="PNG", quality=95)
    output.seek(0)
    return output.getvalue()
