from openai import OpenAI

client = OpenAI(
    api_key="sk-N2OOLFzETy3KmZuFSnlFHQ8iko5vhnLYFbuwnKF47jiqE5fm",
    base_url="https://max.openai365.top/v1"  # add /v1 if your proxy requires it
)

try:
    response = client.chat.completions.create(
        model="gemini-3-pro-preview-thinking",
        messages=[
            {"role": "user", "content": "Hello, what your name?"}
        ]
    )

    print(response.choices[0].message.content)

except Exception as e:
    print(f"Request failed: {e}")
