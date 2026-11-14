class LLMError(RuntimeError):
    def __init__(self, message: str, *, model: str, provider: str):
        self.model = model
        self.provider = provider
        super().__init__(f"{message} (provider={provider}, model={model})")


class LLMConfigurationError(LLMError):
    pass


class LLMRequestError(LLMError):
    def __init__(
        self,
        message: str,
        *,
        model: str,
        provider: str,
        retryable: bool = False,
    ):
        self.retryable = retryable
        super().__init__(message, model=model, provider=provider)


class LLMResponseError(LLMError):
    pass
