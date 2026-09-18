from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cognitive_agent.domain.value_objects.identifiers import (
    DeckId,
    SessionId,
    SlideIdentifier,
)
from cognitive_agent.domain.value_objects.transcript import TranscriptContext, TranscriptFragment


class TranscriptContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
        self.session = SessionId.new()
        self.slide_1 = SlideIdentifier(DeckId("deck"), 0)
        self.slide_2 = SlideIdentifier(DeckId("deck"), 1)

    def fragment(self, text: str, seconds_ago: float, slide: SlideIdentifier):
        return TranscriptFragment(
            text=text,
            received_at=self.now - timedelta(seconds=seconds_ago),
            session_id=self.session,
            slide=slide,
        )

    def test_context_filters_by_slide_age_and_fragment_count(self) -> None:
        context = TranscriptContext(max_size=6)
        for fragment in (
            self.fragment("demasiado antigua", 40, self.slide_1),
            self.fragment("otra diapositiva", 8, self.slide_2),
            self.fragment("primera relevante", 7, self.slide_1),
            self.fragment("segunda relevante", 5, self.slide_1),
            self.fragment("tercera relevante", 3, self.slide_1),
            self.fragment("frase actual", 0, self.slide_1),
        ):
            context = context.append(fragment)

        result = context.preceding_text(
            slide=self.slide_1,
            now=self.now,
            max_age_seconds=30,
            max_fragments=2,
            max_chars=1000,
        )

        self.assertEqual(result, "segunda relevante tercera relevante")

    def test_context_respects_character_budget_and_keeps_most_recent_text(self) -> None:
        context = TranscriptContext(
            fragments=(
                self.fragment("contenido antiguo que debe quedar fuera", 3, self.slide_1),
                self.fragment("contenido reciente importante", 2, self.slide_1),
                self.fragment("frase actual", 0, self.slide_1),
            ),
            max_size=6,
        )

        result = context.preceding_text(max_chars=20)

        self.assertLessEqual(len(result), 20)
        self.assertTrue(result.endswith("reciente importante"))

    def test_retain_latest_preserves_capacity_and_filters_slide(self) -> None:
        context = TranscriptContext(
            fragments=(
                self.fragment("anterior", 4, self.slide_1),
                self.fragment("otra", 3, self.slide_2),
                self.fragment("reciente uno", 2, self.slide_1),
                self.fragment("reciente dos", 1, self.slide_1),
            ),
            max_size=6,
        )

        retained = context.retain_latest(2, slide=self.slide_1)

        self.assertEqual(retained.as_text(), "reciente uno reciente dos")
        self.assertEqual(retained.max_size, 6)

if __name__ == "__main__":
    unittest.main()
