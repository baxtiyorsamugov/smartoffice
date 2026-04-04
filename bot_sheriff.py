from fpdf import FPDF
import requests
import os
from datetime import datetime

TOKEN = "8598018949:AAHh2uRX28g8Xji--blDzIfzYAD_R_JHWQw"
CHAT_ID = "372688693"


class SheriffPDF(FPDF):
    def header(self):
        if os.path.exists('yuksalish.png'):
            self.image('yuksalish.png', 10, 8, 30)
        self.add_font('ArialBold', '', 'C:/Windows/Fonts/arialbd.ttf', uni=True)
        self.set_font('ArialBold', '', 18)
        self.set_text_color(192, 57, 43)  # Красный
        self.cell(0, 10, 'ПРОТОКОЛ НАРУШЕНИЯ ПОРЯДКА', 0, 1, 'C')
        self.ln(10)


def send_fine_to_telegram(pdf_path, name):
    url = f"https://api.telegram.org/bot{TOKEN}/sendDocument"
    with open(pdf_path, "rb") as f:
        requests.post(url, data={"chat_id": CHAT_ID, "caption": f"🚨 ШТРАФ! {name} замечен за выбросом мусора!"},
                      files={"document": f})


def generate_fine_pdf(name, photo_path):
    pdf = SheriffPDF()
    pdf.add_page()
    pdf.add_font('Arial', '', 'C:/Windows/Fonts/arial.ttf', uni=True)
    pdf.set_font('Arial', '', 12)

    content = f"""
    Сотрудник: {name}
    Дата: {datetime.now().strftime('%d.%m.%Y')}
    Время: {datetime.now().strftime('%H:%M:%S')}
    Нарушение: Выброс мусора (бутылка/стакан) в неположенном месте.

    Данное нарушение зафиксировано ИИ-системой Smart Office. 
    На основании этого документа выносится дисциплинарное взыскание.
    """
    pdf.multi_cell(0, 10, content)
    pdf.ln(5)
    pdf.cell(0, 10, "ФОТОФИКСАЦИЯ НАРУШЕНИЯ:", ln=True)
    if os.path.exists(photo_path):
        pdf.image(photo_path, x=10, w=180)

    filename = f"Fine_{int(datetime.now().timestamp())}.pdf"
    pdf.output(filename)
    send_fine_to_telegram(filename, name)
    return filename