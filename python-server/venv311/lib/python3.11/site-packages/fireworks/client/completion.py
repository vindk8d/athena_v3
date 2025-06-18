from .api import CompletionResponse, CompletionStreamResponse
from .base_completion import BaseCompletion
from .api_client import FireworksClient


class Completion(BaseCompletion):
    """
    Class for handling text completions.
    """

    endpoint = "completions"
    response_class = CompletionResponse
    stream_response_class = CompletionStreamResponse

    @classmethod
    def _get_data_key(cls) -> str:
        return "prompt"


class CompletionV2(Completion):
    """
    Class for handling text completions.
    """

    def __init__(self, client: FireworksClient, stream: bool):
        super().__init__(client, stream)

    def create(
        self,
        model,
        prompt_or_messages=None,
        request_timeout=600,
        stream=False,
        **kwargs,
    ):
        return super().create(
            model,
            prompt_or_messages,
            request_timeout,
            stream=self._stream,
            client=self._client,
            **kwargs,
        )
