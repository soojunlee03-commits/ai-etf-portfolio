"""Build printable Korean manuals from the same Markdown displayed in the app.

Optional authoring dependencies: reportlab, Pillow; Korean TrueType font required.
Set MANUAL_FONT and MANUAL_BOLD_FONT outside Windows. No app data is read.
"""
import os
import re
from html import escape
from pathlib import Path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether, PageBreak
from PIL import Image as PILImage

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output'/'pdf'
OUT.mkdir(parents=True,exist_ok=True)
pdfmetrics.registerFont(TTFont('Korean',os.environ.get('MANUAL_FONT','C:/Windows/Fonts/malgun.ttf')))
pdfmetrics.registerFont(TTFont('KoreanBold',os.environ.get('MANUAL_BOLD_FONT','C:/Windows/Fonts/malgunbd.ttf')))
pdfmetrics.registerFontFamily('Korean',normal='Korean',bold='KoreanBold',italic='Korean',boldItalic='KoreanBold')
TEAL=colors.HexColor('#126C70'); INK=colors.HexColor('#203238')
styles={
    'body':ParagraphStyle('body',fontName='Korean',fontSize=9.4,leading=15.7,spaceAfter=8,wordWrap='CJK',textColor=INK),
    'title':ParagraphStyle('title',fontName='KoreanBold',fontSize=23,leading=32,spaceAfter=16,wordWrap='CJK',textColor=TEAL),
    'h2':ParagraphStyle('h2',fontName='KoreanBold',fontSize=14,leading=21,spaceBefore=17,spaceAfter=8,wordWrap='CJK',textColor=TEAL,keepWithNext=True),
    'h3':ParagraphStyle('h3',fontName='KoreanBold',fontSize=11,leading=17,spaceBefore=9,spaceAfter=6,wordWrap='CJK',keepWithNext=True),
    'cell':ParagraphStyle('cell',fontName='Korean',fontSize=8.4,leading=13.5,wordWrap='CJK',textColor=INK),
    'caption':ParagraphStyle('caption',fontName='Korean',fontSize=8,leading=12,textColor=colors.HexColor('#52686D'),spaceAfter=12,wordWrap='CJK'),
}

def inline(text):
    text=text.replace('—','-').replace('–','-').replace('\u2011','-')
    text=escape(text)
    text=re.sub(r'\*\*(.+?)\*\*',r'<b>\1</b>',text)
    text=re.sub(r'`([^`]+)`',r'<font color="#126C70">\1</font>',text)
    def link(m):
        label,url=m.groups()
        return f'<link href="{url}" color="#126C70">{label}</link>' if url.startswith('http') else label
    return re.sub(r'\[([^\]]+)\]\(([^)]+)\)',link,text)

def footer(canvas,doc):
    canvas.saveState();w,h=A4
    canvas.setStrokeColor(colors.HexColor('#D4E4E5'));canvas.line(43,38,w-43,38)
    canvas.setFont('Korean',8);canvas.setFillColor(colors.HexColor('#52686D'))
    canvas.drawString(43,25,'AI ETF Portfolio Competition | 한국어 사용설명서 | 2026-09-19')
    canvas.drawRightString(w-43,25,str(doc.page));canvas.restoreState()

def build(name):
    source=ROOT/'docs'/f'{name}.md';lines=source.read_text(encoding='utf-8-sig').splitlines()
    width=A4[0]-86;story=[];i=0
    while i<len(lines):
        line=lines[i].strip();i+=1
        if not line:continue
        if line.startswith('!['):
            match=re.match(r'!\[([^\]]*)\]\(([^)]+)\)',line)
            if match:
                caption,path=match.groups();path=source.parent/path
                with PILImage.open(path) as im:iw,ih=im.size
                ratio=min(width/iw,265/ih)
                story.append(KeepTogether([Image(str(path),width=iw*ratio,height=ih*ratio),Spacer(1,5),Paragraph(inline(caption),styles['caption'])]))
            continue
        if line.startswith('|'):
            group=[line]
            while i<len(lines) and lines[i].strip().startswith('|'):
                group.append(lines[i].strip());i+=1
            data=[]
            for row in group:
                cells=[v.strip() for v in row.strip('|').split('|')]
                if all(re.fullmatch(r'[-: ]+',v) for v in cells):continue
                data.append([Paragraph(inline(v),styles['cell']) for v in cells])
            n=len(data[0]);fractions=([.31,.69] if n==2 else [.26,.37,.37] if n==3 else [1/n]*n)
            table=Table(data,colWidths=[width*f for f in fractions],repeatRows=1,hAlign='LEFT')
            table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#DCECEE')),
                ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F4F8F8')]),
                ('VALIGN',(0,0),(-1,-1),'TOP'),('BOX',(0,0),(-1,-1),.4,colors.HexColor('#CEDDDF')),
                ('LINEBELOW',(0,0),(-1,0),.7,TEAL),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),
                ('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
            story.extend([table,Spacer(1,10)]);continue
        if line.startswith('```'):
            code=[]
            while i<len(lines) and not lines[i].startswith('```'):code.append(lines[i]);i+=1
            i+=1;story.append(Paragraph('<br/>'.join(escape(c) for c in code),styles['body']));continue
        if line.startswith('# '):style='title';line=line[2:]
        elif line.startswith('## '):style='h2';line=line[3:]
        elif line.startswith('### '):style='h3';line=line[4:]
        else:
            style='body'
            if line.startswith('* ') or line.startswith('- '):line='• '+line[2:]
        formatted=inline(line)
        if style=='title' and line.startswith('AI ETF Portfolio Competition '):
            formatted='AI ETF Portfolio Competition<br/>'+inline(line.removeprefix('AI ETF Portfolio Competition '))
        if line.startswith('13. 자주 묻는 문제'):story.append(PageBreak())
        para=Paragraph(formatted,styles[style])
        if line.startswith('**메뉴 경로:'):para.keepWithNext=True
        story.append(para)
    target=OUT/f'{name}.pdf'
    doc=SimpleDocTemplate(str(target),pagesize=A4,rightMargin=43,leftMargin=43,topMargin=42,bottomMargin=53,
                         title=lines[0].lstrip('# '),author='AI ETF Portfolio Competition',pageCompression=1)
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    print(target.name)

if __name__=='__main__':
    for name in ['Student_Manual_KO','Admin_Manual_KO']:build(name)
