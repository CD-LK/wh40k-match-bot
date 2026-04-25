import copy
import json
import os
import re
import pytest

import wh40k_bot.services.datasource_service as svc

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def load(rel_path: str) -> dict:
    with open(os.path.join(DATA_DIR, rel_path), encoding="utf-8") as f:
        return json.load(f)


# ── file discovery helpers ─────────────────────────────────────────────────────

def _all_army_files() -> list[str]:
    """Все JSON в tests/data (рекурсивно)."""
    result = []
    for root, _, files in os.walk(DATA_DIR):
        for fname in sorted(files):
            if fname.endswith(".json"):
                result.append(os.path.relpath(os.path.join(root, fname), DATA_DIR))
    return sorted(result)


def _file_id(rel_path: str) -> str:
    """Читаемый pytest-ID: version/Faction/fmt/stem (таймстамп GDC обрезается)."""
    parts = rel_path.replace("\\", "/").split("/")
    stem = re.sub(r"-\d{4}-\d{2}-\d{2}T[\w._]+$", "", os.path.splitext(parts[-1])[0])
    return "/".join(parts[:-1] + [stem])


def _latest_version() -> str:
    """Возвращает имя папки с самой новой версией данных (формат N.N.N)."""
    versions = [
        e.name for e in os.scandir(DATA_DIR)
        if e.is_dir() and re.fullmatch(r"\d+\.\d+\.\d+", e.name)
    ]
    return max(versions, key=lambda v: tuple(int(x) for x in v.split(".")))


def _units_from_file(data: dict) -> list:
    """Извлекает список юнитов из GDC или datasource JSON."""
    fmt = svc.detect_army_format(data)
    if fmt == "gdc":
        return [c for c in data["category"].get("cards", []) if c.get("cardType") == "DataCard"]
    if fmt == "datasource":
        return data.get("data", [{}])[0].get("datasheets", [])
    return []


def _pick_file(fmt: str, *, min_enhancements: int = 0, skip_invalid: bool = False) -> str:
    """Возвращает первый подходящий JSON из самой новой версии.

    fmt              — 'gdc' или 'datasource'
    min_enhancements — минимум юнитов с selectedEnhancement
    skip_invalid     — пропускать файлы, не прошедшие validate_army_list
    """
    base = os.path.join(DATA_DIR, _latest_version())
    for faction in sorted(os.listdir(base)):
        fmt_dir = os.path.join(base, faction, fmt)
        if not os.path.isdir(fmt_dir):
            continue
        for fname in sorted(os.listdir(fmt_dir)):
            if not fname.endswith(".json"):
                continue
            rel = os.path.relpath(os.path.join(fmt_dir, fname), DATA_DIR)
            data = load(rel)
            if min_enhancements:
                count = sum(1 for u in _units_from_file(data) if u.get("selectedEnhancement"))
                if count < min_enhancements:
                    continue
            if skip_invalid and not svc.validate_army_list(data).valid:
                continue
            return rel
    raise FileNotFoundError(
        f"No {fmt!r} file matching criteria (min_enhancements={min_enhancements}, "
        f"skip_invalid={skip_invalid}) in {_latest_version()}"
    )


ALL_FILES = _all_army_files()


# ── detect_army_format ─────────────────────────────────────────────────────────

class TestDetectArmyFormat:
    def test_gdc_format_detected(self):
        assert svc.detect_army_format({"category": {"cards": []}}) == "gdc"

    def test_datasource_format_detected(self):
        assert svc.detect_army_format({"data": [{}]}) == "datasource"

    def test_empty_dict_is_unknown(self):
        assert svc.detect_army_format({}) == "unknown"

    def test_arbitrary_keys_is_unknown(self):
        assert svc.detect_army_format({"foo": "bar"}) == "unknown"

    def test_category_without_cards_key_is_unknown(self):
        assert svc.detect_army_format({"category": {"name": "x"}}) == "unknown"

    def test_real_gdc_file_detected(self):
        assert svc.detect_army_format(load(_pick_file("gdc"))) == "gdc"

    def test_real_datasource_file_detected(self):
        assert svc.detect_army_format(load(_pick_file("datasource"))) == "datasource"


# ── normalize_gdc_format ────────────────────────────────────────────────────────

class TestNormalizeGdcFormat:
    def test_name_taken_from_category(self):
        data = {"category": {"name": "My Army", "cards": []}}
        assert svc.normalize_gdc_format(data)["name"] == "My Army"

    def test_missing_name_defaults_to_placeholder(self):
        data = {"category": {"cards": []}}
        assert svc.normalize_gdc_format(data)["name"] == "Без названия"

    def test_datacards_become_datasheets(self):
        cards = [
            {"cardType": "DataCard", "name": "Unit A"},
            {"cardType": "DataCard", "name": "Unit B"},
        ]
        result = svc.normalize_gdc_format({"category": {"name": "x", "cards": cards}})
        assert result["data"][0]["datasheets"] == cards

    def test_non_datacard_entries_filtered_out(self):
        cards = [
            {"cardType": "DataCard", "name": "Good"},
            {"cardType": "EnhancementCard", "name": "Bad"},
            {"cardType": "SomeOther", "name": "AlsoBad"},
        ]
        result = svc.normalize_gdc_format({"category": {"name": "x", "cards": cards}})
        datasheets = result["data"][0]["datasheets"]
        assert len(datasheets) == 1
        assert datasheets[0]["name"] == "Good"

    def test_empty_cards_produces_empty_datasheets(self):
        data = {"category": {"name": "Empty", "cards": []}}
        result = svc.normalize_gdc_format(data)
        assert result["data"][0]["datasheets"] == []

    def test_real_gdc_file_produces_valid_structure(self):
        result = svc.normalize_gdc_format(load(_pick_file("gdc")))
        assert "name" in result
        assert "data" in result
        assert "datasheets" in result["data"][0]
        assert len(result["data"][0]["datasheets"]) > 0


# ── validate_army_list – все тестовые файлы ────────────────────────────────────

@pytest.mark.parametrize("path", ALL_FILES, ids=[_file_id(p) for p in ALL_FILES])
def test_army_file(path):
    """Каждый файл из tests/data должен успешно проходить валидацию."""
    result = svc.validate_army_list(load(path))
    assert result.valid, "validation failed:\n" + "\n".join(result.errors)


# ── validate_army_list – строковый ввод ───────────────────────────────────────

def test_accepts_json_string_input():
    result = svc.validate_army_list(json.dumps(load(_pick_file("gdc", skip_invalid=True))))
    assert result.valid


# ── validate_army_list – структурные ошибки ───────────────────────────────────

class TestStructuralErrors:
    def test_invalid_json_string(self):
        result = svc.validate_army_list("{not_valid_json")
        assert not result.valid
        assert any("JSON" in e for e in result.errors)

    def test_unknown_format_returns_error(self):
        result = svc.validate_army_list({"foo": "bar"})
        assert not result.valid
        assert result.errors

    def test_empty_datasheets_is_error(self):
        result = svc.validate_army_list({"name": "x", "data": [{"datasheets": []}]})
        assert not result.valid

    def test_missing_data_key_is_error(self):
        result = svc.validate_army_list({"name": "test"})
        assert not result.valid

    def test_gdc_with_no_datacards_is_error(self):
        result = svc.validate_army_list({"category": {"name": "Empty", "cards": []}})
        assert not result.valid


# ── validate_army_list – правила построения армии ─────────────────────────────

class TestArmyRuleErrors:
    def test_missing_warlord_gdc(self):
        data = copy.deepcopy(load(_pick_file("gdc", skip_invalid=True)))
        for card in data["category"]["cards"]:
            card["isWarlord"] = False
        result = svc.validate_army_list(data)
        assert not result.valid
        assert any("warlord" in e.lower() for e in result.errors)

    def test_missing_warlord_datasource(self):
        data = copy.deepcopy(load(_pick_file("datasource", skip_invalid=True)))
        for unit in data["data"][0]["datasheets"]:
            unit["isWarlord"] = False
        result = svc.validate_army_list(data)
        assert not result.valid
        assert any("warlord" in e.lower() for e in result.errors)

    def test_unknown_faction_is_error(self):
        data = copy.deepcopy(load(_pick_file("gdc", skip_invalid=True)))
        for card in data["category"]["cards"]:
            card["factions"] = ["Totally Unknown Faction XYZ"]
        result = svc.validate_army_list(data)
        assert not result.valid

    def test_unknown_unit_name_is_error(self):
        data = copy.deepcopy(load(_pick_file("gdc", skip_invalid=True)))
        original_name = data["category"]["cards"][0]["name"]
        data["category"]["cards"][0]["name"] = f"FAKE_UNIT_{original_name}"
        result = svc.validate_army_list(data)
        assert not result.valid
        assert any("FAKE_UNIT" in e for e in result.errors)

    def test_duplicate_enhancements_are_rejected(self):
        data = copy.deepcopy(load(_pick_file("gdc", min_enhancements=2, skip_invalid=True)))
        enh_cards = [c for c in data["category"]["cards"] if c.get("selectedEnhancement")]
        enh_cards[1]["selectedEnhancement"] = copy.deepcopy(enh_cards[0]["selectedEnhancement"])
        result = svc.validate_army_list(data)
        assert not result.valid
        assert any("дублир" in e.lower() for e in result.errors)

    def test_enhancements_from_different_detachments_are_rejected(self):
        data = copy.deepcopy(load(_pick_file("gdc", min_enhancements=2, skip_invalid=True)))
        enh_cards = [c for c in data["category"]["cards"] if c.get("selectedEnhancement")]
        enh_cards[1]["selectedEnhancement"]["detachment"] = "Completely Different Detachment"
        enh_cards[1]["selectedEnhancement"]["name"] = "Unique Enhancement Omega"
        result = svc.validate_army_list(data)
        assert not result.valid
        assert any("detachment" in e.lower() for e in result.errors)

    def test_stats_mismatch_produces_error_message(self):
        data = copy.deepcopy(load(_pick_file("datasource", skip_invalid=True)))
        unit_name = data["data"][0]["datasheets"][0]["name"]
        data["data"][0]["datasheets"][0]["stats"][0]["t"] = "99"
        result = svc.validate_army_list(data)
        assert not result.valid
        assert any(unit_name in e for e in result.errors)


# ── подсчёт очков с энхансментами ─────────────────────────────────────────────

class TestEnhancementCostAccounting:
    def test_enhancement_costs_included_in_total(self):
        path = _pick_file("gdc", min_enhancements=1, skip_invalid=True)
        data = load(path)
        expected = sum(
            int((u.get("unitSize") or {}).get("cost") or 0)
            + int((u.get("selectedEnhancement") or {}).get("cost") or 0)
            for u in _units_from_file(data)
        )
        assert svc.validate_army_list(data).total_points == expected

    def test_removing_enhancement_reduces_total_by_its_cost(self):
        path = _pick_file("datasource", min_enhancements=1, skip_invalid=True)
        baseline = svc.validate_army_list(load(path)).total_points
        data = copy.deepcopy(load(path))
        enh_cost = None
        for unit in _units_from_file(data):
            enh = unit.get("selectedEnhancement")
            if enh:
                enh_cost = int(enh["cost"])
                unit["selectedEnhancement"] = None
                break
        assert enh_cost is not None
        assert svc.validate_army_list(data).total_points == baseline - enh_cost

    def test_detachment_taken_from_enhancement(self):
        path = _pick_file("gdc", min_enhancements=1, skip_invalid=True)
        data = load(path)
        expected = next(
            u["selectedEnhancement"]["detachment"]
            for u in _units_from_file(data)
            if u.get("selectedEnhancement") and u["selectedEnhancement"].get("detachment")
        )
        assert svc.validate_army_list(data).detachment == expected

    def test_no_enhancements_means_no_detachment(self):
        data = copy.deepcopy(load(_pick_file("gdc", min_enhancements=1, skip_invalid=True)))
        for card in data["category"]["cards"]:
            card["selectedEnhancement"] = None
        assert svc.validate_army_list(data).detachment is None

    def test_multiple_enhancements_same_detachment_is_valid(self):
        path = _pick_file("gdc", min_enhancements=2, skip_invalid=True)
        data = load(path)
        detachments = {
            u["selectedEnhancement"]["detachment"]
            for u in _units_from_file(data)
            if u.get("selectedEnhancement") and u["selectedEnhancement"].get("detachment")
        }
        assert len(detachments) == 1, f"test file must have 1 detachment, got {detachments}"
        result = svc.validate_army_list(data)
        assert result.valid
        assert result.detachment == next(iter(detachments))
