from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from ...application.settings import ApplicationSettings
from ...application.use_cases import (
    ChangeCurrentSlide,
    DetectDeicticExpression,
    EndClassroomSession,
    ExportNotes,
    GenerateClarification,
    GetCurrentSlide,
    GetLatestClarification,
    GetSession,
    InsertClarificationIntoNotes,
    JumpToSlideNotes,
    ListenClarification,
    LoadDeck,
    NotifyClarification,
    ProcessTranscriptFragment,
    RenameClassroomSession,
    ScheduleSlideTagInsertion,
    StartClassroomSession,
    UpdateStudentNotes,
)
from ...application.use_cases.transcript import ClarificationDebouncer
from ...domain.policies import (
    ClarificationInsertionPolicy,
    NoteTaggingPolicy,
    SlideTransitionPolicy,
)
from ...domain.services.clarification_context_builder import ClarificationContextBuilder
from ...domain.services.clarification_validator import ClarificationValidator
from ...domain.services.deictic_detection_service import DeicticDetectionService
from ..config.settings import Settings, load_settings

logger = logging.getLogger(__name__)

@dataclass
class Container:

    settings: Settings
    app_settings: ApplicationSettings
    clock: Any
    events: Any
    scheduler: Any
    telemetry: Any
    notifications: Any
    deictic_log: Any
    prompts: Any
    sessions: Any
    notes: Any
    clarifications: Any
    descriptions: Any
    detector: Any
    generator: Any
    stt: Any
    tts: Any
    notes_processor: Any
    exporters: dict
    start_session: StartClassroomSession
    end_session: EndClassroomSession
    rename_session: RenameClassroomSession
    load_deck: LoadDeck
    change_slide: ChangeCurrentSlide
    process_fragment: ProcessTranscriptFragment
    detect_deixis: DetectDeicticExpression
    generate_clarification: GenerateClarification
    notify_clarification: NotifyClarification
    get_latest_clarification: GetLatestClarification
    listen_clarification: ListenClarification
    update_notes: UpdateStudentNotes
    insert_clarification: InsertClarificationIntoNotes
    jump_to_slide_notes: JumpToSlideNotes
    export_notes: ExportNotes
    schedule_tag: ScheduleSlideTagInsertion
    get_current_slide: GetCurrentSlide
    get_session: GetSession
    chat_model: Any = None
    clarification_chat_model: Any = None
    notes_chat_model: Any = None
    detection_chat_model: Any = None
    description_chat_model: Any = None
    deictic_chat_model: Any = None

    def shutdown(self) -> None:

        try:
            self.scheduler.shutdown(wait=False)
        except Exception:
            logger.warning("El planificador no se cerro limpiamente.", exc_info=True)
        close = getattr(self.descriptions, "close", None)
        if callable(close):
            close()

    def health(self) -> dict:

        checks = {
            "config": {"ok": not self.settings.validate(), "detail": self.settings.validate()},
            "prompts": {"ok": True, "detail": sorted(self.prompts.available())},
            "llm": {
                "ok": all(
                    bool(getattr(model, "is_available", True))
                    for model in {
                        id(self.chat_model): self.chat_model,
                        id(self.clarification_chat_model): self.clarification_chat_model,
                        id(self.notes_chat_model): self.notes_chat_model,
                        id(self.detection_chat_model): self.detection_chat_model,
                        id(self.description_chat_model): self.description_chat_model,
                        id(self.deictic_chat_model): self.deictic_chat_model,
                    }.values()
                    if model is not None
                ),
                "detail": {
                    "default": self.settings.llm.provider,
                    "detection": (
                        self.settings.llm.detection_provider or self.settings.llm.provider
                    ),
                    "clarification": (
                        self.settings.llm.clarification_provider
                        or self.settings.llm.provider
                    ),
                    "notes": self.settings.llm.notes_provider or self.settings.llm.provider,
                    "deixis": self.settings.llm.deixis_provider or self.settings.llm.provider,
                },
            },
            "stt": {
                "ok": bool(getattr(self.stt, "is_available", True)) if self.stt else False,
                "detail": self.settings.stt.provider,
            },
            "deixis_classifier": {
                "ok": bool(getattr(self.deictic_classifier, "is_available", True)),
                "detail": (
                    str(self.settings.deixis_classifier_model)
                    if self.deictic_classifier is not None
                    else "no utilizado"
                ),
            },
            "persistence": {"ok": True, "detail": self.settings.persistence.backend},
        }
        return {"ok": all(entry["ok"] for entry in checks.values()), "checks": checks}

    documents: Any = None

    description_generator: Any = None
    precompute: Any = None
    live_region: Any = None

    pointer_resolver: Any = None

    deictic_classifier: Any = None

def build_container(settings: Settings | None = None, **load_kwargs) -> Container:
    from ...adapters.outbound.clock import SystemClock
    from ...adapters.outbound.classification import (
        RulesThenClassifierDeicticDetector,
        SklearnDeicticClassifier,
    )
    from ...adapters.outbound.deictic_log import (
        FileDeicticDetectionLog,
        NullDeicticDetectionLog,
    )
    from ...adapters.outbound.events import InProcessEventBus
    from ...adapters.outbound.export import MarkdownNotesExporter, PlainTextNotesExporter
    from ...adapters.outbound.llm import (
        FakeChatModel,
        GeminiChatModel,
        LlmDeicticDetector,
        OllamaChatModel,
        PassthroughNotesProcessor,
        PromptedClarificationGenerator,
        PromptedNotesProcessor,
        RuleBasedDeicticDetector,
        RulesThenLlmDeicticDetector,
    )
    from ...adapters.outbound.notifications import (
        CompositeNotificationPort,
        LiveRegionNotificationHub,
    )
    from ...adapters.outbound.persistence import (
        FileClarificationRepository,
        FileNotesRepository,
        FileSessionRepository,
        InMemoryClarificationRepository,
        InMemoryNotesRepository,
        InMemorySessionRepository,
        InMemorySlideDescriptionRepository,
        SqliteSlideDescriptionRepository,
    )
    from ...adapters.outbound.prompts import FileSystemPromptRepository
    from ...adapters.outbound.scheduler import ThreadTaskScheduler
    from ...adapters.outbound.speech_to_text import (
        FakeSpeechToText,
        GeminiSpeechToText,
        WhisperSpeechToText,
    )
    from ...adapters.outbound.telemetry import (
        CompositeTelemetry,
        JsonlTelemetry,
        LoggingTelemetry,
        NullTelemetry,
    )
    from ...adapters.outbound.text_to_speech import (
        BrowserTextToSpeech,
        LocalTextToSpeech,
        NullTextToSpeech,
    )

    settings = settings or load_settings(**load_kwargs)
    problems = settings.validate()
    for problem in problems:
        logger.error("Configuracion invalida: %s", problem)

    app_settings = settings.application()

    clock = SystemClock()
    events = InProcessEventBus()
    scheduler = ThreadTaskScheduler(workers=settings.scheduler.workers)
    if not settings.telemetry.enabled or settings.telemetry.sink == "null":
        telemetry = NullTelemetry()
    elif settings.telemetry.sink == "jsonl":
        telemetry = JsonlTelemetry(
            settings.telemetry_file, redact_content=settings.telemetry.redact_content
        )
    elif settings.telemetry.sink == "both":
        telemetry = CompositeTelemetry(
            LoggingTelemetry(redact_content=settings.telemetry.redact_content),
            JsonlTelemetry(
                settings.telemetry_file, redact_content=settings.telemetry.redact_content
            ),
        )
    else:
        telemetry = LoggingTelemetry(redact_content=settings.telemetry.redact_content)
    live_region = LiveRegionNotificationHub()
    notifications = CompositeNotificationPort(live_region)
    deictic_log = (
        FileDeicticDetectionLog(settings.data_dir)
        if settings.persistence.backend == "file"
        else NullDeicticDetectionLog()
    )

    prompts = FileSystemPromptRepository(
        root=settings.prompts_dir, registry_path=settings.prompts_registry
    )

    if settings.persistence.backend == "file":
        data_dir = settings.data_dir
        sessions = FileSessionRepository(data_dir)
        notes_repo = FileNotesRepository(
            data_dir,
            slide_tag_template=settings.notes.slide_tag_template,
            clarification_tag_template=settings.notes.clarification_tag_template,
        )
        clarifications = FileClarificationRepository(data_dir)
        descriptions = SqliteSlideDescriptionRepository(settings.slide_knowledge_db)
    else:
        sessions = InMemorySessionRepository()
        notes_repo = InMemoryNotesRepository(
            slide_tag_template=settings.notes.slide_tag_template,
            clarification_tag_template=settings.notes.clarification_tag_template,
        )
        clarifications = InMemoryClarificationRepository()
        descriptions = InMemorySlideDescriptionRepository()

    provider = settings.llm.provider

    def build_chat_model(model_provider: str, *, role: str) -> Any:
        if model_provider == "gemini":
            if role == "detection":
                model_id = settings.llm.detection_model
            elif role == "description":
                model_id = settings.llm.description_model
            elif role == "deixis":
                model_id = settings.llm.deixis_model
            elif role == "notes":
                model_id = settings.llm.notes_model
            else:
                model_id = settings.llm.clarification_model
            return GeminiChatModel(
                model_id=model_id,
                project=settings.llm.gcp_project,
                location=settings.llm.gcp_location,
                default_timeout=settings.llm.request_timeout_seconds,
            )
        if model_provider == "ollama":
            if role in {"description", "detection"}:
                model_id = settings.llm.ollama_vision_model
            elif role == "notes":
                model_id = settings.llm.notes_model
            else:
                model_id = settings.llm.ollama_router_model
            return OllamaChatModel(
                model_id=model_id,
                base_url=settings.llm.ollama_base_url,
                num_gpu=settings.llm.ollama_num_gpu,
                default_timeout=settings.llm.request_timeout_seconds,
            )
        return FakeChatModel()

    clarification_provider = settings.llm.clarification_provider or provider
    detection_provider = settings.llm.detection_provider or provider
    notes_provider = settings.llm.notes_provider or provider
    deixis_provider = settings.llm.deixis_provider or provider
    chat_model: Any = build_chat_model(provider, role="default")
    clarification_chat_model: Any = build_chat_model(
        clarification_provider, role="clarification"
    )
    notes_chat_model: Any = build_chat_model(notes_provider, role="notes")
    detection_chat_model: Any = build_chat_model(detection_provider, role="detection")
    description_chat_model: Any = build_chat_model(provider, role="description")
    deictic_chat_model: Any = build_chat_model(deixis_provider, role="deixis")

    rule_service = (
        DeicticDetectionService(
            suppressors=(), min_confidence=settings.deixis.min_confidence
        )
        if settings.deixis.detector in {"rules_then_llm", "rules_then_classifier"}
        else DeicticDetectionService(min_confidence=settings.deixis.min_confidence)
    )
    rules_detector = RuleBasedDeicticDetector(rule_service)
    deictic_classifier: Any = None
    if settings.deixis.detector == "llm":
        detector: Any = LlmDeicticDetector(
            chat=deictic_chat_model, prompts=prompts, fallback=rules_detector
        )
    elif settings.deixis.detector == "rules_then_llm":
        detector = RulesThenLlmDeicticDetector(
            rules=rules_detector,
            llm=LlmDeicticDetector(
                chat=deictic_chat_model, prompts=prompts, fallback=rules_detector
            ),
        )
    elif settings.deixis.detector == "rules_then_classifier":
        threshold = (
            None
            if settings.deixis.classifier_threshold < 0
            else settings.deixis.classifier_threshold
        )
        deictic_classifier = SklearnDeicticClassifier(
            settings.deixis_classifier_model,
            threshold=threshold,
        )
        if not deictic_classifier.is_available:
            logger.warning("El clasificador local de deixis no esta disponible al arrancar.")
        detector = RulesThenClassifierDeicticDetector(
            rules=rules_detector,
            classifier=deictic_classifier,
        )
    else:
        detector = rules_detector

    generator = PromptedClarificationGenerator(
        chat=clarification_chat_model,
        prompts=prompts,
        timeout_seconds=settings.clarification.timeout_seconds,
        temperature=settings.llm.temperature,
    )
    notes_processor = (
        PassthroughNotesProcessor()
        if notes_provider == "fake"
        else PromptedNotesProcessor(chat=notes_chat_model, prompts=prompts)
    )

    if settings.stt.provider == "gemini":
        stt: Any = GeminiSpeechToText(
            model_id=settings.stt.model,
            project=settings.llm.gcp_project,
            location=settings.llm.gcp_location,
            prompts=prompts,
            language=settings.stt.language,
        )
    elif settings.stt.provider == "whisper_local":
        stt = WhisperSpeechToText(
            model_size=settings.stt.whisper_model,
            device=settings.stt.whisper_device,
            language=settings.stt.language,
        )
    else:
        stt = FakeSpeechToText()

    if settings.tts.provider == "pyttsx3":
        tts: Any = LocalTextToSpeech(rate=settings.tts.rate)
    elif settings.tts.provider == "null":
        tts = NullTextToSpeech()
    else:
        tts = BrowserTextToSpeech()

    exporters = {
        "markdown": MarkdownNotesExporter(),
        "text": PlainTextNotesExporter(),
    }
    try:
        from ...adapters.outbound.export import pdf_exporter

        exporters["pdf"] = pdf_exporter()
    except ImportError:
        logger.info("PyMuPDF no disponible: la exportacion a PDF queda desactivada.")

    transitions = SlideTransitionPolicy(idle_seconds=settings.notes.slide_tag_idle_seconds)
    tagging = NoteTaggingPolicy(
        template=settings.notes.slide_tag_template,
        announce=settings.notes.announce_tag_insertion,
    )
    insertion = ClarificationInsertionPolicy(
        template=settings.notes.clarification_tag_template,
        auto_insert=settings.notes.auto_insert_clarifications,
    )
    context_builder = ClarificationContextBuilder(max_words=settings.clarification.max_words)
    validator = ClarificationValidator(max_words=settings.clarification.max_words)

    schedule_tag = ScheduleSlideTagInsertion(
        sessions=sessions,
        notes=notes_repo,
        clock=clock,
        events=events,
        scheduler=scheduler,
        transitions=transitions,
        tagging=tagging,
        notifications=notifications,
        settings=app_settings,
    )
    notify = NotifyClarification(notifications=notifications, settings=app_settings)
    generate = GenerateClarification(
        sessions=sessions,
        clarifications=clarifications,
        descriptions=descriptions,
        generator=generator,
        context_builder=context_builder,
        validator=validator,
        clock=clock,
        events=events,
        telemetry=telemetry,
        settings=app_settings,
        notifier=notify,
    )
    process_fragment = ProcessTranscriptFragment(
        sessions=sessions,
        clarifications=clarifications,
        detector=detector,
        stt=stt,
        clock=clock,
        events=events,
        scheduler=scheduler,
        telemetry=telemetry,
        prompts=prompts,
        settings=app_settings,
        deictic_log=deictic_log,
        generate_callback=generate,
        debouncer=ClarificationDebouncer(
            min_interval_seconds=settings.clarification.min_seconds_between
        ),
    )

    container = Container(
        settings=settings,
        app_settings=app_settings,
        clock=clock,
        events=events,
        scheduler=scheduler,
        telemetry=telemetry,
        notifications=notifications,
        deictic_log=deictic_log,
        prompts=prompts,
        sessions=sessions,
        notes=notes_repo,
        clarifications=clarifications,
        descriptions=descriptions,
        detector=detector,
        generator=generator,
        stt=stt,
        tts=tts,
        notes_processor=notes_processor,
        exporters=exporters,
        start_session=StartClassroomSession(
            sessions=sessions,
            notes=notes_repo,
            clock=clock,
            events=events,
            settings=app_settings,
        ),
        end_session=EndClassroomSession(
            sessions=sessions, clarifications=clarifications, clock=clock, events=events
        ),
        rename_session=RenameClassroomSession(
            sessions=sessions, clarifications=clarifications, descriptions=descriptions
        ),
        load_deck=LoadDeck(
            sessions=sessions, descriptions=descriptions, clock=clock, events=events
        ),
        change_slide=ChangeCurrentSlide(
            sessions=sessions,
            descriptions=descriptions,
            clock=clock,
            events=events,
            notifications=notifications,
            schedule_tag=schedule_tag,
            settings=app_settings,
        ),
        process_fragment=process_fragment,
        detect_deixis=DetectDeicticExpression(
            detector=detector, clock=clock, telemetry=telemetry
        ),
        generate_clarification=generate,
        notify_clarification=notify,
        get_latest_clarification=GetLatestClarification(
            sessions=sessions, clarifications=clarifications
        ),
        listen_clarification=ListenClarification(
            sessions=sessions,
            clarifications=clarifications,
            tts=tts,
            clock=clock,
            events=events,
            telemetry=telemetry,
        ),
        update_notes=UpdateStudentNotes(
            sessions=sessions,
            notes=notes_repo,
            clock=clock,
            events=events,
            transitions=transitions,
            tagging=tagging,
            telemetry=telemetry,
            settings=app_settings,
        ),
        insert_clarification=InsertClarificationIntoNotes(
            sessions=sessions,
            notes=notes_repo,
            clarifications=clarifications,
            clock=clock,
            events=events,
            insertion=insertion,
            notifications=notifications,
            telemetry=telemetry,
            settings=app_settings,
        ),
        jump_to_slide_notes=JumpToSlideNotes(
            sessions=sessions,
            notes=notes_repo,
            notifications=notifications,
            settings=app_settings,
        ),
        export_notes=ExportNotes(
            notes=notes_repo,
            sessions=sessions,
            clock=clock,
            events=events,
            exporters=exporters,
            processor=notes_processor,
            telemetry=telemetry,
        ),
        schedule_tag=schedule_tag,
        get_current_slide=GetCurrentSlide(sessions=sessions, descriptions=descriptions),
        get_session=GetSession(
            sessions=sessions, descriptions=descriptions, clarifications=clarifications
        ),
        chat_model=chat_model,
        clarification_chat_model=clarification_chat_model,
        notes_chat_model=notes_chat_model,
        detection_chat_model=detection_chat_model,
        description_chat_model=description_chat_model,
        deictic_chat_model=deictic_chat_model,
        deictic_classifier=deictic_classifier,
    )
    container.live_region = live_region

    try:
        from ...adapters.outbound.documents import (
            DescriptionAwarePointerResolver,
            GeminiSlideElementDetector,
            PyMuPdfDocumentSource,
        )
        from ...adapters.outbound.llm import PromptedSlideDescriptionGenerator
        from ...application.use_cases.precompute import PrecomputeDeck, PrecomputePolicy
        from ...domain.value_objects.slide_description import DescriptionFormat

        element_detector = GeminiSlideElementDetector(
            vision=detection_chat_model,
            timeout_seconds=settings.llm.request_timeout_seconds,
        )
        documents = PyMuPdfDocumentSource(
            element_detector=element_detector,
            processing_profile=(
                f"detect={settings.llm.detection_model};"
                f"describe={settings.llm.description_model}"
            ),
        )
        description_generator = PromptedSlideDescriptionGenerator(
            vision=description_chat_model,
            prompts=prompts,
            fmt=DescriptionFormat.HTML,
        )
        container.documents = documents
        container.description_generator = description_generator

        pointer_resolver = DescriptionAwarePointerResolver(
            descriptions=descriptions, fallback=documents
        )
        container.pointer_resolver = pointer_resolver
        process_fragment.pointer_resolver = pointer_resolver
        container.precompute = PrecomputeDeck(
            descriptions=descriptions,
            generator=description_generator,
            documents=documents,
            scheduler=scheduler,
            clock=clock,
            telemetry=telemetry,
            policy=PrecomputePolicy(use_pdf_page=provider != "ollama"),
        )
    except ImportError:
        logger.info(
            "PyMuPDF o Pillow no disponibles: preprocesado de presentaciones desactivado."
        )

    return container
