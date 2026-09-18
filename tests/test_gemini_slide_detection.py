from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cognitive_agent.adapters.outbound.documents.gemini_slide_detection import (
    GeminiSlideElementDetector,
    _extract_json_array,
    _normalise_detection,
)
from cognitive_agent.domain.services.pointed_element import element_at_point
from cognitive_agent.domain.services.slide_html_bboxes import annotate_html_with_bboxes

class _Vision:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    def describe(self, **_kwargs):
        self.calls += 1
        return type("Response", (), {"text": self.text})()


class GeminiSlideDetectionTests(unittest.TestCase):
    def test_parses_fenced_json_and_normalises_box(self) -> None:
        raw = _extract_json_array(
            '```json\n[{"descripcion":"Resultados","label":"Title",'
            '"box_2d":[50,100,180,900]}]\n```'
        )

        detection = _normalise_detection(raw[0])

        self.assertIsNotNone(detection)
        self.assertEqual(detection["bbox_norm"], (0.1, 0.05, 0.9, 0.18))
        self.assertEqual(detection["role"], "title")
        self.assertEqual(detection["text"], "Resultados")

    def test_detection_integrates_with_html_pointer_lookup(self) -> None:
        vision = _Vision(
            '[{"descripcion":"Resultados","label":"Title",'
            '"box_2d":[50,100,180,900]}]'
        )
        elements = GeminiSlideElementDetector(vision).detect(b"fake-image")
        html = annotate_html_with_bboxes(
            '<section><h2 data-element-id="t1">Resultados</h2></section>',
            elements,
            page_width=1000,
            page_height=700,
        )

        pointed = element_at_point(html, 0.5, 0.1)

        self.assertIsNotNone(pointed)
        self.assertEqual(pointed.element_id, "t1")
        self.assertEqual(pointed.role, "title")
        self.assertEqual(vision.calls, 1)

    def test_rejects_unknown_class_and_degenerate_box(self) -> None:
        self.assertIsNone(
            _normalise_detection(
                {"descripcion": "x", "label": "Unknown", "box_2d": [0, 0, 1, 1]}
            )
        )
        self.assertIsNone(
            _normalise_detection(
                {"descripcion": "x", "label": "Title", "box_2d": [1, 1, 1, 1]}
            )
        )
if __name__ == "__main__":
    unittest.main()
