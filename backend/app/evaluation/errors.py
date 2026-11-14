class LLMError(RuntimeError):
    def __init__(self, message: str, *, model: str, provider: str):
        self.model = model
        self.provider = provider
        super().__init__(f"{message} (provider={provider}, model={model})")


class LLMConfigurationError(LLMError):
    pass


class LLMRequestError(LLMError):
    pass


class LLMResponseError(LLMError):
    pass
