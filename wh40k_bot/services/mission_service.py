"""
Сервис для работы с миссиями
"""
import json
import random
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass


# Путь к папке с миссиями
# В Docker: /app/mission_pool
# Локально: рядом с wh40k_bot
import os

if os.path.exists("/app/mission_pool"):
    MISSION_POOL_DIR = Path("/app/mission_pool")
else:
    MISSION_POOL_DIR = Path(__file__).parent.parent.parent / "mission_pool"


@dataclass
class MissionResult:
    """Результат генерации миссии"""
    combination_letter: str
    primary_mission: str
    deployment: str
    terrain_layout: int
    
    def to_dict(self) -> dict:
        return {
            "combination_letter": self.combination_letter,
            "primary_mission": self.primary_mission,
            "deployment": self.deployment,
            "terrain_layout": self.terrain_layout
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "MissionResult":
        return cls(
            combination_letter=data["combination_letter"],
            primary_mission=data["primary_mission"],
            deployment=data["deployment"],
            terrain_layout=data["terrain_layout"]
        )


def load_mission_pool() -> Dict[str, Any]:
    """Загрузить пул миссий"""
    pool_file = MISSION_POOL_DIR / "mission_pool.json"
    
    if not pool_file.exists():
        return {}
    
    with open(pool_file, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_random_mission() -> Optional[MissionResult]:
    """Сгенерировать случайную миссию"""
    pool = load_mission_pool()
    
    if not pool:
        return None
    
    # Выбираем случайную комбинацию (букву)
    letter = random.choice(list(pool.keys()))
    combo = pool[letter]
    
    # Выбираем случайный terrain_layout из списка
    terrain_options = combo.get("terrain_layout", [1, 2, 3, 4, 5, 6, 7, 8])
    terrain = random.choice(terrain_options)
    
    return MissionResult(
        combination_letter=letter,
        primary_mission=combo["primary_mission"],
        deployment=combo["deployment"],
        terrain_layout=terrain
    )


def get_mission_images(mission: MissionResult) -> Tuple[Optional[bytes], Optional[bytes], Optional[bytes]]:
    """Получить изображения для миссии (primary, deployment, terrain)"""
    primary_image = None
    deployment_image = None
    terrain_image = None
    
    # Primary mission
    primary_path = MISSION_POOL_DIR / "primary_mission" / f"{mission.primary_mission}.png"
    if primary_path.exists():
        with open(primary_path, "rb") as f:
            primary_image = f.read()
    
    # Deployment
    deployment_path = MISSION_POOL_DIR / "deployment" / f"{mission.deployment}.png"
    if deployment_path.exists():
        with open(deployment_path, "rb") as f:
            deployment_image = f.read()
    
    # Terrain layout
    terrain_path = MISSION_POOL_DIR / "terrain_layout" / f"{mission.terrain_layout}.png"
    if terrain_path.exists():
        with open(terrain_path, "rb") as f:
            terrain_image = f.read()
    
    return primary_image, deployment_image, terrain_image


def format_mission_info(mission: MissionResult) -> str:
    """Форматировать информацию о миссии"""
    primary_name = mission.primary_mission.replace('_', ' ').title()
    deployment_name = mission.deployment.replace('_', ' ').title()
    
    return (
        f"🎲 <b>Миссия: Комбинация {mission.combination_letter}</b>\n\n"
        f"📋 <b>Primary Mission:</b> {primary_name}\n"
        f"🗺 <b>Deployment:</b> {deployment_name}\n"
        f"🏔 <b>Terrain Layout:</b> #{mission.terrain_layout}"
    )
