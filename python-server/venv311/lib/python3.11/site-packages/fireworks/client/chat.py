from .chat_completion import ChatCompletionV2
from .api_client import FireworksClient


class Chat:
    def __init__(self, client: FireworksClient, stream: bool):
        self.completions = ChatCompletionV2(client, stream)
