from __future__ import annotations

class DomainError(Exception):
    pass

class InvalidSlideIndex(DomainError):
    pass

class SessionNotFound(DomainError):
    pass

class SessionAlreadyEnded(DomainError):
    pass

class NoActiveDeck(DomainError):
    pass

class SlideDescriptionUnavailable(DomainError):
    pass

class ClarificationNotFound(DomainError):
    pass

class NoClarificationAvailable(DomainError):
    pass

class ClarificationGenerationFailed(DomainError):
    pass

class ClarificationTimedOut(ClarificationGenerationFailed):
    pass

class NotesNotFound(DomainError):
    pass

class ProtectedNoteEntry(DomainError):
    pass

class PromptNotFound(DomainError):
    pass
