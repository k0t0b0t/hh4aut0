class BotError(Exception):
    pass


class LLMValidationError(BotError):
    pass


class StageExecutionError(BotError):
    pass
