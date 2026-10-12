import os

from app.services.providers.openai_provider import OpenAIProvider


def main():
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY environment variable is not set."
        )

    provider = OpenAIProvider(
        api_key=api_key,
        model="gpt-4o-mini",
    )

    answer = provider.generate(
        system_prompt="You are a helpful assistant.",
        user_prompt="Explain what RAG means in one sentence.",
        temperature=0,
    )

    print("\nOpenAI response:")
    print(answer.answer)


if __name__ == "__main__":
    main()
