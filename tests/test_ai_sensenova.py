import unittest

import httpx

from bot.ai.client import AIClient, AIClientConfig


class SenseNovaAIClientTest(unittest.IsolatedAsyncioTestCase):
    async def test_sensenova_chat_completion_uses_v1_url_and_content_only(self):
        requests = []

        async def transport_handler(request):
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": "最终摘要",
                                "reasoning_content": "内部推理不应返回给用户",
                            }
                        }
                    ]
                },
                request=request,
            )

        client = AIClient(
            AIClientConfig(
                base_url="https://token.sensenova.cn/v1",
                api_key="test-key",
                model="deepseek-v4-flash",
                timeout=1.0,
                max_output_tokens=2000,
            ),
            transport=transport_handler,
        )

        try:
            text = await client.complete([{"role": "user", "content": "总结"}])
        finally:
            await client.aclose()

        self.assertEqual(text, "最终摘要")
        self.assertEqual(requests[0].url.path, "/v1/chat/completions")
        self.assertIn(b"deepseek-v4-flash", requests[0].content)
        self.assertNotIn("内部推理", text)


if __name__ == "__main__":
    unittest.main()
