import json
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import main


ROOT = Path(__file__).resolve().parents[1]
OFFICE_AI_JS = ROOT / "assets" / "office_ai.js"


def run_prompt_builder(builder_name, values):
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("Node.js is unavailable for frontend rule tests")
    script = r"""
require(process.argv[1]);
const payload = JSON.parse(process.argv[2]);
const formData = {
  get(name) {
    const value = payload[name];
    return Array.isArray(value) ? (value[0] || null) : (value ?? null);
  },
  getAll(name) {
    const value = payload[name];
    if (value === undefined || value === null) return [];
    return Array.isArray(value) ? value : [value];
  },
};
process.stdout.write(globalThis.OfficeAIPromptBuilders.builders[process.argv[3]](formData));
"""
    completed = subprocess.run(
        [node, "-e", script, str(OFFICE_AI_JS), json.dumps(values, ensure_ascii=False), builder_name],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout


class OfficeAIWebTest(unittest.TestCase):
    def setUp(self):
        self.client = main.app.test_client()

    def test_office_ai_page_returns_six_task_types_without_model_call(self):
        with patch.object(main, "ask_gpt") as ask_gpt:
            response = self.client.get("/office-ai")

        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Office AI 工具箱", html)
        self.assertIn("不知道 Prompt 怎麼寫？選擇你要完成的工作，我們幫你組好。", html)
        self.assertEqual(html.count('class="task-card'), 6)
        for task in (
            "圖片轉 Excel",
            "PDF 文件整理",
            "會議紀錄整理",
            "Email / 商務文字",
            "Excel / 表格分析",
            "工程問題分析",
        ):
            with self.subTest(task=task):
                self.assertIn(task, html)
        self.assertIn("/assets/office_ai.css", html)
        self.assertIn("/assets/office_ai.js", html)
        ask_gpt.assert_not_called()

    def test_home_page_has_office_ai_entry(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('href="/office-ai"', html)
        self.assertIn("Office AI 工具箱", html)

    def test_office_ai_assets_are_served(self):
        self.assertEqual(self.client.get("/assets/office_ai.css").status_code, 200)
        self.assertEqual(self.client.get("/assets/office_ai.js").status_code, 200)

    def test_image_to_excel_prompt_changes_with_options(self):
        cctv_prompt = run_prompt_builder(
            "image-excel",
            {
                "image-data-type": "CCTV",
                "image-requirement": ["merge", "device", "xlsx"],
            },
        )
        access_prompt = run_prompt_builder(
            "image-excel",
            {
                "image-data-type": "門禁",
                "image-requirement": ["ip", "location"],
            },
        )

        self.assertNotEqual(cctv_prompt, access_prompt)
        self.assertIn("多張CCTV資料照片", cctv_prompt)
        self.assertIn("合併整理成單一資料表", cctv_prompt)
        self.assertIn("設備名稱", cctv_prompt)
        self.assertIn("Excel (.xlsx)", cctv_prompt)
        self.assertNotIn("IP Address", cctv_prompt)
        self.assertNotIn("Location", cctv_prompt)
        self.assertNotIn("Remark", cctv_prompt)

        self.assertIn("門禁資料照片", access_prompt)
        self.assertIn("IP Address與Location", access_prompt)
        self.assertNotIn("設備名稱", access_prompt)
        self.assertNotIn("Excel (.xlsx)", access_prompt)
        self.assertNotIn("合併整理成單一資料表", access_prompt)
        for principle in ("不要自行猜測", "待確認", "原始資料順序", "不要自行補造"):
            self.assertIn(principle, access_prompt)

    def test_engineering_prompt_separates_facts_and_inferences(self):
        prompt = run_prompt_builder(
            "engineering",
            {
                "engineering-system": "CCTV",
                "engineering-device": "NVR",
                "engineering-symptom": "部分攝影機離線",
                "engineering-checks": "已確認 NVR 電源正常",
            },
        )

        self.assertIn("已確認事實", prompt)
        self.assertIn("推測", prompt)
        self.assertIn("依優先順序", prompt)
        self.assertIn("不足資訊", prompt)
        self.assertIn("不可自行假設", prompt)

    def test_copy_flow_and_mobile_layout_hooks_are_present(self):
        source = OFFICE_AI_JS.read_text(encoding="utf-8")
        stylesheet = (ROOT / "assets" / "office_ai.css").read_text(encoding="utf-8")

        self.assertIn("navigator.clipboard.writeText(promptOutput.value)", source)
        self.assertIn('document.execCommand("copy")', source)
        self.assertIn("提示詞已複製，可以貼到 ChatGPT 使用。", source)
        self.assertIn('getElementById("regenerate-prompt")', source)
        self.assertIn('getElementById("back-builder")', source)
        self.assertIn("@media (max-width: 760px)", stylesheet)
        self.assertIn(".task-grid { grid-template-columns: 1fr; }", stylesheet)
        self.assertIn("@media (prefers-reduced-motion: reduce)", stylesheet)
        self.assertNotIn("/web-chat", source)
        self.assertNotIn("/answer", source)

    def test_existing_primary_pages_still_respond(self):
        for path in ("/", "/little-tree", "/ipas", "/ipas/net-zero-planner"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)


if __name__ == "__main__":
    unittest.main()
