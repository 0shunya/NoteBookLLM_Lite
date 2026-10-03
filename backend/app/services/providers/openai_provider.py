from openai import OpenAI

from app.services.providers.base import ModelProvider


class OpenAIProvider(ModelProvider):
    """
    OpenAI implementation of the ModelProvider interface.

    This class is responsible only for communicating with OpenAI.
    It does not know anything about:
        - RAG
        - conversations
        - citations
        - FastAPI
        - databases

    The ModelGateway handles provider selection.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
    ):
        if not api_key:
            raise ValueError("OpenAI API key is required.")

        if not model:
            raise ValueError("OpenAI model is required.")

        self.model = model

        self.client = OpenAI(
            api_key=api_key,
        )

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0,
    ) -> str:
        """
        Generate a response using OpenAI.
        """

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            temperature=temperature,
        )

        answer = response.choices[0].message.content

        if not answer:
            raise RuntimeError(
                "The OpenAI model returned an empty answer."
            )

        return answer.strip()