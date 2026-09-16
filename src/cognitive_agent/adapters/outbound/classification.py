from __future__ import annotations

import logging
from pathlib import Path
from threading import Lock
from typing import Any
from ...application.ports.outbound.classification import DeicticClassification
from ...domain.value_objects.deictic import DeicticDetection
from ...domain.value_objects.subject import Subject
from .llm.detector import RuleBasedDeicticDetector

logger = logging.getLogger(__name__)

class ClassifierUnavailable(RuntimeError):
    pass

class SklearnDeicticClassifier:

    name = "tfidf_text_classifier"

    def __init__(self, model_path: str | Path, *, threshold: float | None = None) -> None:
        self._path = Path(model_path)
        self._threshold_override = threshold
        self._artifact: dict[str, Any] | None = None
        self._lock = Lock()

    def _load(self) -> dict[str, Any]:
        if self._artifact is not None:
            return self._artifact
        with self._lock:
            if self._artifact is not None:
                return self._artifact
            if not self._path.is_file():
                raise ClassifierUnavailable(f"No se encuentra el modelo: {self._path}")
            try:
                import joblib

                artifact = joblib.load(self._path)
            except Exception as exc:
                raise ClassifierUnavailable(
                    f"No se pudo cargar el modelo {self._path}: {type(exc).__name__}: {exc}"
                ) from exc
            if not isinstance(artifact, dict) or "pipeline" not in artifact:
                raise ClassifierUnavailable("El artefacto no contiene un pipeline compatible.")
            self._artifact = artifact
            return artifact

    def classify(
        self, text: str, *, subject: Subject = Subject.GENERIC
    ) -> DeicticClassification:
        artifact = self._load()
        pipeline = artifact["pipeline"]
        try:
            probabilities = pipeline.predict_proba([text])[0]
            classes = list(pipeline.classes_)
            positive_index = classes.index(1)
            probability = float(probabilities[positive_index])
        except Exception as exc:
            raise ClassifierUnavailable(f"Fallo la inferencia: {type(exc).__name__}: {exc}") from exc

        trained_threshold = float(artifact.get("threshold", 0.5))
        threshold = (
            self._threshold_override
            if self._threshold_override is not None
            else trained_threshold
        )
        return DeicticClassification(
            needs_clarification=probability >= threshold,
            probability=probability,
            threshold=threshold,
            model_version=str(artifact.get("model_version", "desconocida")),
        )

    @property
    def is_available(self) -> bool:
        try:
            self._load()
        except ClassifierUnavailable:
            return False
        return True

class RulesThenClassifierDeicticDetector:

    name = "rules_then_classifier"

    def __init__(
        self,
        *,
        rules: RuleBasedDeicticDetector,
        classifier: SklearnDeicticClassifier,
    ) -> None:
        self._rules = rules
        self._classifier = classifier

    def detect(self, text: str, *, subject: Subject = Subject.GENERIC) -> DeicticDetection:
        candidate = self._rules.detect(text, subject=subject)
        if not candidate.detected:
            return candidate

        try:
            decision = self._classifier.classify(text, subject=subject)
        except ClassifierUnavailable as exc:

            logger.warning("Clasificador de deixis no disponible; se aceptan las reglas: %s", exc)
            return DeicticDetection(
                expressions=candidate.expressions,
                detector="rules_then_classifier_fallback",
            )

        logger.info(
            "Clasificador de deixis | probabilidad=%.4f umbral=%.4f decision=%s modelo=%s",
            decision.probability,
            decision.threshold,
            decision.needs_clarification,
            decision.model_version,
        )
        if not decision.needs_clarification:
            return DeicticDetection.none(
                "el clasificador local considera que no necesita aclaracion",
                detector=self.name,
                decision_probability=decision.probability,
                decision_threshold=decision.threshold,
            )
        return DeicticDetection(
            expressions=candidate.expressions,
            detector=self.name,
            decision_probability=decision.probability,
            decision_threshold=decision.threshold,
        )

__all__ = [
    "ClassifierUnavailable",
    "RulesThenClassifierDeicticDetector",
    "SklearnDeicticClassifier",
]
