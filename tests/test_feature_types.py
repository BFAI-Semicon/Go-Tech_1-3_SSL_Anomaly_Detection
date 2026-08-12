import ast
from datetime import date
from pathlib import Path
from typing import get_type_hints

import numpy as np

from feature_extraction.model.layout import TilePlacement, TilePlan
from feature_extraction.model.types import (
    DatasetSplit,
    DomainTags,
    ImageLabel,
    ImageMetadata,
    InspectionImage,
    ProvenanceKeys,
)

_TYPES_PATH = Path("src/feature_extraction/model/types.py")
_LAYOUT_PATH = Path("src/feature_extraction/model/layout.py")
_FORBIDDEN_IMPORT_ROOTS = frozenset({"torch", "timm", "anomalib", "pydantic"})


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".", maxsplit=1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            roots.add(node.module.split(".", maxsplit=1)[0])
    return roots


def test_should_expose_only_train_and_test_dataset_split_members():
    assert {member.name for member in DatasetSplit} == {"TRAIN", "TEST"}
    assert {member.value for member in DatasetSplit} == {"train", "test"}
    assert DatasetSplit.TRAIN == "train"
    assert DatasetSplit.TEST == "test"
    assert not hasattr(DatasetSplit, "VAL")


def test_should_expose_image_label_values():
    assert ImageLabel.NORMAL == "normal"
    assert ImageLabel.ANOMALOUS == "anomalous"


def test_should_build_inspection_image_with_numpy_and_absent_mask():
    pixels = np.zeros((3, 4, 4), dtype=np.float32)
    image = InspectionImage(
        image_id="/data/sample.png",
        pixels=pixels,
        split=DatasetSplit.TRAIN,
        image_label=ImageLabel.NORMAL,
        ground_truth_mask=None,
        domain=DomainTags(process="etch", material="si", equipment=None),
        provenance=ProvenanceKeys(
            wafer_id="W1",
            lot_id=None,
            captured_on=date(2026, 8, 12),
        ),
    )

    assert image.ground_truth_mask is None
    assert image.pixels.dtype == np.float32
    assert image.pixels.shape == (3, 4, 4)
    assert image.split is DatasetSplit.TRAIN


def test_should_compose_image_metadata_from_domain_and_provenance():
    domain = DomainTags(process=None, material=None, equipment=None)
    provenance = ProvenanceKeys(wafer_id=None, lot_id=None, captured_on=None)
    metadata = ImageMetadata(domain=domain, provenance=provenance)

    assert metadata.domain is domain
    assert metadata.provenance is provenance


def test_should_build_tile_plan_from_tile_placements():
    placements = (
        TilePlacement(top=0, left=0),
        TilePlacement(top=0, left=224),
    )
    plan = TilePlan(
        image_height=512,
        image_width=768,
        tile_size=256,
        placements=placements,
    )

    assert plan.placements == placements
    assert plan.tile_size == 256


def test_should_keep_types_and_layout_free_of_framework_imports():
    assert _imported_roots(_TYPES_PATH).isdisjoint(_FORBIDDEN_IMPORT_ROOTS)
    assert _imported_roots(_LAYOUT_PATH).isdisjoint(_FORBIDDEN_IMPORT_ROOTS)


def test_should_compose_inspection_image_from_numpy_and_stdlib_types_only():
    hints = get_type_hints(InspectionImage)
    assert hints["image_id"] is str
    assert hints["pixels"] is np.ndarray
    assert hints["split"] is DatasetSplit
    assert hints["image_label"] is ImageLabel
    assert hints["ground_truth_mask"] == (np.ndarray | None)
    assert hints["domain"] == (DomainTags | None)
    assert hints["provenance"] == (ProvenanceKeys | None)
