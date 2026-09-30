import csv
import io
import json
import zipfile
from collections import defaultdict, deque
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree as ET

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ..extensions import db
from ..models.food_reference import (
    FdcCategory,
    FdcFood,
    FdcFoodNutrient,
    FdcFoodPortion,
    FdcNutrient,
    FoodOnCategory,
)


RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
OWL = "{http://www.w3.org/2002/07/owl#}"
RDFS = "{http://www.w3.org/2000/01/rdf-schema#}"
XML = "{http://www.w3.org/XML/1998/namespace}"
FOODON_ROOT = "FOODON_00001002"


def _as_int(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_decimal(value):
    if value in (None, ""):
        return None
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


def _member(archive, filename):
    matches = [name for name in archive.namelist() if Path(name).name.casefold() == filename.casefold()]
    return matches[0] if matches else None


def _rows(archive, filename):
    member = _member(archive, filename)
    if member is None:
        return
    with archive.open(member) as raw:
        reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
        yield from reader


def _upsert(model, records):
    if not records:
        return
    table = model.__table__
    dialect = db.engine.dialect.name
    if dialect == "sqlite":
        statement = sqlite_insert(table)
    elif dialect == "postgresql":
        statement = pg_insert(table)
    else:
        raise RuntimeError("USDA imports are supported on SQLite and PostgreSQL only.")

    primary_keys = [column.name for column in table.primary_key.columns]
    update_columns = {column.name: getattr(statement.excluded, column.name) for column in table.columns
                      if column.name not in primary_keys}
    statement = statement.on_conflict_do_update(index_elements=primary_keys, set_=update_columns)
    db.session.execute(statement, records)


def _database_size_bytes():
    connection = db.session.connection()
    if db.engine.dialect.name == "sqlite":
        page_count = connection.exec_driver_sql("PRAGMA page_count").scalar() or 0
        page_size = connection.exec_driver_sql("PRAGMA page_size").scalar() or 0
        logical_size = page_count * page_size
        path = db.engine.url.database
        file_size = 0
        if path and Path(path).exists():
            file_size = Path(path).stat().st_size
            for suffix in ("-wal", "-shm"):
                sidecar = Path(f"{path}{suffix}")
                if sidecar.exists():
                    file_size += sidecar.stat().st_size
        return max(logical_size, file_size)
    return connection.execute(text("SELECT pg_database_size(current_database())")).scalar_one()


def _enforce_size_limit(max_bytes):
    size = _database_size_bytes()
    if size > max_bytes:
        raise RuntimeError(
            f"Database size limit reached ({size / (1024 * 1024):.1f} MiB > "
            f"{max_bytes / (1024 * 1024):.0f} MiB). The current import transaction was rolled back."
        )


def _execute_batches(model, rows, batch_size, max_bytes, counts, label):
    batch = []
    count = 0
    for row in rows:
        batch.append(row)
        if len(batch) >= batch_size:
            _upsert(model, batch)
            count += len(batch)
            batch.clear()
            _enforce_size_limit(max_bytes)
            if count % 20000 < batch_size:
                print(f"Imported {count:,} {label} rows", flush=True)
    if batch:
        _upsert(model, batch)
        count += len(batch)
        _enforce_size_limit(max_bytes)
    counts[label] = count


def import_fdc_archive(zip_path, release, max_bytes=400 * 1024 * 1024, batch_size=2000):
    """Stream USDA CSV members into normalized reference tables; never create menu products."""
    zip_path = Path(zip_path)
    if not zip_path.is_file():
        raise ValueError(f"USDA archive not found: {zip_path}")

    counts = {}
    try:
        archive = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as error:
        raise ValueError("The USDA dataset file is not a valid ZIP archive.") from error

    try:
        names = {Path(name).name.casefold() for name in archive.namelist()}
        if "food.csv" not in names or "food_nutrient.csv" not in names:
            raise ValueError("This archive must contain USDA food.csv and food_nutrient.csv files.")

        db.session.rollback()
        try:
            def category_rows():
                sources = (
                    ("food_category.csv", "id", "description"),
                    ("wweia_food_category.csv", "wweia_food_category", "wweia_food_category_description"),
                )
                for filename, id_column, name_column in sources:
                    for row in _rows(archive, filename):
                        category_id = _as_int(row.get(id_column))
                        name = (row.get(name_column) or "").strip()
                        if category_id is not None and name:
                            yield {"id": category_id, "name": name[:180]}

            _execute_batches(FdcCategory, category_rows(), batch_size, max_bytes, counts, "categories")

            nutrient_number_to_id = {}
            nutrient_ids = set()

            def nutrient_rows():
                for row in _rows(archive, "nutrient.csv"):
                    nutrient_id = _as_int(row.get("id"))
                    name = (row.get("name") or "").strip()
                    if nutrient_id is None or not name:
                        continue
                    nutrient_ids.add(nutrient_id)
                    nutrient_number = (row.get("nutrient_nbr") or "").strip()
                    if nutrient_number:
                        nutrient_number_to_id[nutrient_number] = nutrient_id
                    yield {
                        "id": nutrient_id,
                        "name": name[:180],
                        "unit_name": (row.get("unit_name") or "").strip()[:32],
                        "nutrient_nbr": nutrient_number[:16] or None,
                        "rank": _as_int(row.get("rank")),
                    }

            _execute_batches(FdcNutrient, nutrient_rows(), batch_size, max_bytes, counts, "nutrients")

            food_rows = (
                {
                    "fdc_id": _as_int(row.get("fdc_id")),
                    "data_type": (row.get("data_type") or "unknown").strip()[:40],
                    "description": (row.get("description") or "Unnamed food").strip()[:500],
                    "category_id": _as_int(row.get("food_category_id")),
                    "food_code": None,
                    "start_date": None,
                    "end_date": None,
                    "publication_date": (row.get("publication_date") or "").strip()[:10] or None,
                    "source_release": release[:24],
                }
                for row in _rows(archive, "food.csv")
                if _as_int(row.get("fdc_id")) is not None
            )
            _execute_batches(FdcFood, food_rows, batch_size, max_bytes, counts, "foods")

            input_food_rows = (
                {
                    "fdc_id": _as_int(row.get("fdc_id")),
                    "data_type": "Survey input food",
                    "description": (row.get("sr_description") or "").strip()[:500],
                    "category_id": _as_int(row.get("food_category_id")),
                    "food_code": None,
                    "start_date": None,
                    "end_date": None,
                    "publication_date": None,
                    "source_release": release[:24],
                }
                for row in _rows(archive, "input_food.csv")
                if _as_int(row.get("fdc_id")) is not None
                and (row.get("sr_description") or "").strip()
            )
            _execute_batches(FdcFood, input_food_rows, batch_size, max_bytes, counts, "input foods")

            survey_rows = (
                {
                    "fdc_id": _as_int(row.get("fdc_id")),
                    "data_type": "Survey (FNDDS)",
                    "description": "",
                    "category_id": _as_int(row.get("wweia_category_number")),
                    "food_code": (row.get("food_code") or "").strip()[:24] or None,
                    "start_date": (row.get("start_date") or "").strip()[:10] or None,
                    "end_date": (row.get("end_date") or "").strip()[:10] or None,
                    "publication_date": None,
                    "source_release": release[:24],
                }
                for row in _rows(archive, "survey_fndds_food.csv")
                if _as_int(row.get("fdc_id")) is not None
            )
            # Do not replace the food description with the blank supplied by the linking table.
            _execute_survey_food_batches(survey_rows, batch_size, max_bytes, counts)

            unmapped_nutrient_ids = set()

            def nutrient_observations():
                for row in _rows(archive, "food_nutrient.csv"):
                    source_nutrient_id = _as_int(row.get("nutrient_id"))
                    if source_nutrient_id is None:
                        continue
                    # FDC observation files refer to nutrient_nbr; map it to the
                    # stable nutrient table primary key used by the import schema.
                    nutrient_id = nutrient_number_to_id.get(str(source_nutrient_id))
                    if nutrient_id is None and source_nutrient_id in nutrient_ids:
                        nutrient_id = source_nutrient_id
                    if nutrient_id is None:
                        # Some FDC releases contain observations for a source
                        # component without a row in nutrient.csv. Preserve the
                        # value and mark its definition explicitly as unmapped.
                        nutrient_id = -abs(source_nutrient_id)
                        if source_nutrient_id not in unmapped_nutrient_ids:
                            _upsert(
                                FdcNutrient,
                                [{
                                    "id": nutrient_id,
                                    "name": f"Unmapped FDC nutrient {source_nutrient_id}",
                                    "unit_name": "",
                                    "nutrient_nbr": str(source_nutrient_id),
                                    "rank": None,
                                }],
                            )
                            unmapped_nutrient_ids.add(source_nutrient_id)
                    source_id = _as_int(row.get("id"))
                    fdc_id = _as_int(row.get("fdc_id"))
                    if source_id is None or fdc_id is None:
                        continue
                    yield {
                        "id": source_id,
                        "fdc_id": fdc_id,
                        "nutrient_id": nutrient_id,
                        "amount": _as_decimal(row.get("amount")),
                        "data_points": _as_int(row.get("data_points")),
                        "derivation_id": _as_int(row.get("derivation_id")),
                        "min_value": _as_decimal(row.get("min")),
                        "max_value": _as_decimal(row.get("max")),
                        "median_value": _as_decimal(row.get("median")),
                        "min_year_acquired": _as_int(row.get("min_year_acquired")),
                    }
            _execute_batches(
                FdcFoodNutrient, nutrient_observations(), batch_size, max_bytes, counts, "food nutrients"
            )
            counts["unmapped nutrient identifiers"] = len(unmapped_nutrient_ids)

            portion_rows = (
                {
                    "id": _as_int(row.get("id")),
                    "fdc_id": _as_int(row.get("fdc_id")),
                    "sequence_number": _as_int(row.get("seq_num")),
                    "amount": _as_decimal(row.get("amount")),
                    "measure_unit_id": _as_int(row.get("measure_unit_id")),
                    "description": (row.get("portion_description") or "").strip()[:240] or None,
                    "modifier": (row.get("modifier") or "").strip()[:120] or None,
                    "gram_weight": _as_decimal(row.get("gram_weight")),
                    "data_points": _as_int(row.get("data_points")),
                }
                for row in _rows(archive, "food_portion.csv")
                if _as_int(row.get("id")) is not None and _as_int(row.get("fdc_id")) is not None
            )
            _execute_batches(FdcFoodPortion, portion_rows, batch_size, max_bytes, counts, "portions")

            _enforce_size_limit(max_bytes)
            db.session.commit()
            _enforce_size_limit(max_bytes)
        except Exception:
            db.session.rollback()
            raise
    finally:
        archive.close()
    return counts


def _execute_survey_food_batches(rows, batch_size, max_bytes, counts):
    """Apply survey category metadata while retaining each food's original description."""
    batch = []
    count = 0
    for row in rows:
        batch.append(row)
        if len(batch) >= batch_size:
            _upsert_survey_food(batch)
            count += len(batch)
            batch.clear()
            _enforce_size_limit(max_bytes)
    if batch:
        _upsert_survey_food(batch)
        count += len(batch)
        _enforce_size_limit(max_bytes)
    counts["survey category links"] = count


def _upsert_survey_food(rows):
    table = FdcFood.__table__
    dialect = db.engine.dialect.name
    statement = sqlite_insert(table) if dialect == "sqlite" else pg_insert(table)
    statement = statement.on_conflict_do_update(
        index_elements=[table.c.fdc_id],
        set_={
            "category_id": statement.excluded.category_id,
            "food_code": statement.excluded.food_code,
            "start_date": statement.excluded.start_date,
            "end_date": statement.excluded.end_date,
            "source_release": statement.excluded.source_release,
        },
    )
    db.session.execute(statement, rows)


def import_foodon_ontology(owl_path, max_bytes=400 * 1024 * 1024, batch_size=2000):
    """Import labeled descendants of FoodOn's generic food-product root."""
    owl_path = Path(owl_path)
    if not owl_path.is_file():
        raise ValueError(f"FoodOn ontology not found: {owl_path}")

    terms = {}
    for _, element in ET.iterparse(owl_path, events=("end",)):
        if element.tag != f"{OWL}Class":
            continue
        uri = element.attrib.get(f"{RDF}about") or element.attrib.get(f"{RDF}ID")
        term_id = _local_term_id(uri)
        if not term_id or not term_id.startswith("FOODON_"):
            element.clear()
            continue
        deprecated = any(
            child.tag == f"{OWL}deprecated" and (child.text or "").strip().lower() == "true"
            for child in element
        )
        if deprecated:
            element.clear()
            continue
        labels = [child for child in element if child.tag == f"{RDFS}label" and (child.text or "").strip()]
        label = next((child.text.strip() for child in labels if child.attrib.get(f"{XML}lang") == "en"), None)
        label = label or (labels[0].text.strip() if labels else None)
        if not label:
            element.clear()
            continue
        parents = [
            _local_term_id(child.attrib.get(f"{RDF}resource"))
            for child in element
            if child.tag == f"{RDFS}subClassOf" and child.attrib.get(f"{RDF}resource")
        ]
        terms[term_id] = {"name": label[:240], "parents": [parent for parent in parents if parent]}
        element.clear()

    if FOODON_ROOT not in terms:
        raise ValueError(f"FoodOn root {FOODON_ROOT} was not found in this ontology file.")

    children = defaultdict(list)
    for term_id, details in terms.items():
        for parent in details["parents"]:
            children[parent].append(term_id)

    selected = {FOODON_ROOT}
    queue = deque([FOODON_ROOT])
    while queue:
        parent = queue.popleft()
        for child in children.get(parent, ()):
            if child not in selected:
                selected.add(child)
                queue.append(child)

    counts = {}
    category_rows = (
        {
            "term_id": term_id,
            "name": terms[term_id]["name"],
            "parent_term_ids": json.dumps(
                [parent for parent in terms[term_id]["parents"] if parent in selected],
                separators=(",", ":"),
            ),
        }
        for term_id in sorted(selected)
        if term_id in terms
    )

    db.session.rollback()
    try:
        _execute_batches(FoodOnCategory, category_rows, batch_size, max_bytes, counts, "FoodOn categories")
        _enforce_size_limit(max_bytes)
        db.session.commit()
        _enforce_size_limit(max_bytes)
    except Exception:
        db.session.rollback()
        raise
    return counts.get("FoodOn categories", 0)


def _local_term_id(uri):
    if not uri:
        return None
    value = uri.rsplit("/", 1)[-1].rsplit("#", 1)[-1]
    if value.startswith("FOODON_"):
        return value
    return None
