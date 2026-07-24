from openai import OpenAI

client = OpenAI(
  base_url = "https://integrate.api.nvidia.com/v1",
  api_key = "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"
)


completion = client.chat.completions.create(
  model="deepseek-ai/deepseek-v4-pro",
  messages=[{"role":"user","content":"Write a python file that has a hardcoded string and returns vowels and numeric count"}],
  temperature=1,
  top_p=0.95,
  max_tokens=16384,
  extra_body={"chat_template_kwargs":{"thinking":False}},
  stream=False
)

print(completion.choices[0].message.content)