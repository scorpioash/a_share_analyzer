import os
from datetime import datetime
from fpdf import FPDF

class ReportExporter:
    """研报导出工具 — 极致兼容版"""

    def __init__(self):
        # 优先查找 msyh.ttf (单字体文件), 再尝试 simsun.ttc, 最后回退 helvetica
        self.font_name = None
        self.font_path = None
        candidates = [
            ("msyh", "C:\\Windows\\Fonts\\msyh.ttf"),
            ("msyh", "C:\\Windows\\Fonts\\msyhbd.ttf"),
            ("simsun", "C:\\Windows\\Fonts\\simsun.ttc"),
        ]
        for name, path in candidates:
            if os.path.exists(path):
                self.font_name = name
                self.font_path = path
                break

    def generate_markdown(self, name: str, code: str, result: str) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        md_header = f"# 【{name} - {code}】深度分析研报\n"
        md_header += f"生成时间: {timestamp}\n\n"
        md_header += "---\n\n"
        return md_header + result

    def generate_pdf(self, name: str, code: str, result: str) -> bytes:
        """生成 PDF 字节流，多重容错确保永远返回有效 bytes"""
        try:
            pdf = FPDF()
            pdf.add_page()

            # 字体处理：尝试加载中文字体
            font_loaded = False
            if self.font_path:
                try:
                    pdf.add_font(self.font_name, "", self.font_path)
                    pdf.set_font(self.font_name, size=12)
                    font_loaded = True
                except Exception:
                    pass

            if not font_loaded:
                pdf.set_font("helvetica", size=12)

            active_font = self.font_name if font_loaded else "helvetica"

            # 标题渲染
            pdf.set_font(active_font, size=16)
            title = f"Analysis Report: {name} ({code})"
            pdf.cell(0, 10, title, ln=True, align='C')
            pdf.ln(5)

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            pdf.set_font(active_font, size=9)
            pdf.cell(0, 6, f"Generated: {timestamp}", ln=True, align='C')
            pdf.ln(8)

            # 正文渲染
            pdf.set_font(active_font, size=11)

            # 清洗内容：移除可能导致 PDF 崩溃的特殊字符
            safe_result = result.encode('utf-8', 'ignore').decode('utf-8')
            # 移除 Markdown 格式符号
            for ch in ['**', '__', '> ', '> [!', '```', '---']:
                safe_result = safe_result.replace(ch, '')

            lines = safe_result.split('\n')
            for line in lines:
                if not line.strip():
                    pdf.ln(3)
                    continue
                if line.startswith('##') or line.startswith('#'):
                    pdf.set_font(active_font, size=13)
                    pdf.multi_cell(0, 8, line.lstrip('#').strip())
                    pdf.set_font(active_font, size=11)
                else:
                    try:
                        pdf.multi_cell(0, 7, line)
                    except Exception:
                        # 跳过无法渲染的行
                        continue

            return bytes(pdf.output())

        except Exception as e:
            # 最终兜底：即使一切都失败，也返回一个极简 PDF
            try:
                fail_pdf = FPDF()
                fail_pdf.add_page()
                fail_pdf.set_font("helvetica", size=12)
                fail_pdf.cell(0, 10, f"PDF Generation Error: {str(e)[:80]}", ln=True)
                fail_pdf.cell(0, 10, f"Report: {name} ({code})", ln=True)
                return bytes(fail_pdf.output())
            except Exception:
                return b""  # 绝对不能返回 None
