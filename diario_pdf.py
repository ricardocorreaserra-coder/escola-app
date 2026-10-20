"""Geração do Diário de Classe em PDF (A4 paisagem) com ReportLab.

Recebe os mesmos dados que gerar_diario_workbook() usa para o .xlsx.
"""
import datetime
import html
from io import BytesIO

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak,
    KeepTogether, Image,
)
from xml.sax.saxutils import escape as _xml_escape

# --- Medidas (pt) -----------------------------------------------------------
MARGEM = 28
LARGURA_UTIL = landscape(A4)[0] - 2 * MARGEM   # ~786
W_NUM = 22
W_ALUNO = 130
W_DATA = 18
W_AVAL = 40
W_MEDIA = 38
W_FALTAS = 38

COR_BORDA = colors.HexColor("#777777")
COR_HEADER = colors.HexColor("#E2E8F0")
COR_ZEBRA = colors.HexColor("#F5F7FA")


def _t(valor):
    """Os textos vêm do banco já escapados por html.escape(); desfaz o escape."""
    return html.unescape(str(valor)) if valor is not None else ""


def _p(valor):
    """Texto seguro para usar dentro de Paragraph (XML)."""
    return _xml_escape(_t(valor))


def _fmt_data(data_str, fmt="%d/%m"):
    try:
        return datetime.datetime.strptime(data_str, "%Y-%m-%d").strftime(fmt)
    except (ValueError, TypeError):
        return _t(data_str)


def _fmt_num(v, casas):
    return f"{v:.{casas}f}".replace(".", ",")


def _cortar(texto, fonte, tamanho, largura):
    """Corta o texto com reticências para caber na largura."""
    texto = _t(texto)
    if stringWidth(texto, fonte, tamanho) <= largura:
        return texto
    while texto and stringWidth(texto + "…", fonte, tamanho) > largura:
        texto = texto[:-1]
    return texto.rstrip() + "…"


def _logo_flowable(logo_bytes, altura_max=48, largura_max=130):
    if not logo_bytes:
        return ""
    try:
        w, h = PILImage.open(BytesIO(logo_bytes)).size
        escala = min(altura_max / h, largura_max / w)
        return Image(BytesIO(logo_bytes), width=w * escala, height=h * escala)
    except Exception:
        return ""


def _cabecalho(instituicao, curso, materia, professor, turma, ano, logo_bytes, titulo):
    st_titulo = ParagraphStyle("titulo", fontName="Helvetica-Bold", fontSize=15,
                               alignment=TA_CENTER, leading=18)
    st_info = ParagraphStyle("info", fontName="Helvetica", fontSize=9, leading=13)

    topo = Table(
        [[_logo_flowable(logo_bytes), Paragraph(titulo, st_titulo), ""]],
        colWidths=[150, LARGURA_UTIL - 300, 150],
    )
    topo.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))

    esquerda = [
        Paragraph(f"<b>Instituição:</b> {_p(instituicao) or '—'}", st_info),
        Paragraph(f"<b>Disciplina:</b> {_p(materia)}", st_info),
        Paragraph(f"<b>Turma:</b> {_p(turma)}", st_info),
    ]
    direita = [
        Paragraph(f"Curso: <b>{_p(curso) or '—'}</b>", st_info),
        Paragraph(f"Professor(a): <b>{_p(professor) or '—'}</b>", st_info),
        Paragraph(f"Ano: {_p(ano)}", st_info),
    ]
    info = Table([[esquerda, direita]], colWidths=[LARGURA_UTIL * 0.55, LARGURA_UTIL * 0.45])
    info.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return [topo, Spacer(1, 8), info, Spacer(1, 10)]


def _dividir_datas(datas, n_avals):
    """Divide as datas em blocos; só o último bloco leva avaliações/média/faltas."""
    cap_cheio = max(1, int((LARGURA_UTIL - W_NUM - W_ALUNO) // W_DATA))
    resto_larg = LARGURA_UTIL - W_NUM - W_ALUNO - n_avals * W_AVAL - W_MEDIA - W_FALTAS
    cap_ultimo = max(1, int(resto_larg // W_DATA))
    blocos, resto = [], list(datas)
    while len(resto) > cap_ultimo:
        blocos.append(resto[:cap_cheio])
        resto = resto[cap_cheio:]
    blocos.append(resto)  # pode ser [] (sem datas)
    return blocos


def _tabela_frente(alunos, bloco, ultimo, avals, chamadas, notas, datas_total):
    n_d, n_a = len(bloco), len(avals) if ultimo else 0
    col_d0 = 2
    col_a0 = col_d0 + n_d
    col_media = col_a0 + n_a
    col_faltas = col_media + 1
    n_cols = (col_faltas + 1) if ultimo else col_a0

    fn, fs = "Helvetica", 8
    # Linha 0: rótulos de seção; linha 1: cabeçalhos das colunas
    r0 = [""] * n_cols
    r1 = [""] * n_cols
    r0[0], r0[1] = "Nº", "Aluno"   # células mescladas (linhas 0-1) usam o texto da linha 0
    if n_d:
        r0[col_d0] = "FREQUÊNCIA"
    for i, d in enumerate(bloco):
        r1[col_d0 + i] = _fmt_data(d)
    if ultimo:
        if n_a:
            r0[col_a0] = "AVALIAÇÕES"
        for i, av in enumerate(avals):
            r1[col_a0 + i] = _cortar(av, "Helvetica-Bold", 8, W_AVAL - 4)
        r0[col_media], r0[col_faltas] = "Média", "Faltas"

    linhas = [r0, r1]
    for idx, (mat, a) in enumerate(alunos, start=1):
        linha = [""] * n_cols
        linha[0] = str(idx)
        linha[1] = _cortar(a["nome"], fn, fs, W_ALUNO - 8)
        ch = chamadas.get(mat, {})
        for i, d in enumerate(bloco):
            p = ch.get(d)
            linha[col_d0 + i] = "P" if p is True else ("F" if p is False else "")
        if ultimo:
            na = notas.get(mat, {})
            vals = []
            for i, av in enumerate(avals):
                v = na.get(av)
                if isinstance(v, (int, float)):
                    linha[col_a0 + i] = _fmt_num(v, 1)
                    vals.append(v)
            linha[col_media] = _fmt_num(sum(vals) / len(vals), 2) if vals else ""
            linha[col_faltas] = str(sum(1 for d in datas_total if ch.get(d) is False))
        linhas.append(linha)

    larguras = [W_NUM, W_ALUNO] + [W_DATA] * n_d
    if ultimo:
        larguras += [W_AVAL] * n_a + [W_MEDIA, W_FALTAS]

    tab = Table(linhas, colWidths=larguras, repeatRows=2)
    estilo = [
        ("FONTNAME", (0, 0), (-1, -1), fn),
        ("FONTSIZE", (0, 0), (-1, -1), fs),
        ("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, COR_BORDA),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (1, 2), (1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, 1), COR_HEADER),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1),
        ("LEFTPADDING", (1, 2), (1, -1), 4),
        ("SPAN", (0, 0), (0, 1)),
        ("SPAN", (1, 0), (1, 1)),
        ("ROWBACKGROUNDS", (0, 2), (-1, -1), [colors.white, COR_ZEBRA]),
    ]
    if n_d:
        estilo.append(("FONTSIZE", (col_d0, 1), (col_a0 - 1, 1), 6))  # datas dd/mm
        estilo.append(("SPAN", (col_d0, 0), (col_a0 - 1, 0)))
    if ultimo:
        if n_a:
            estilo.append(("SPAN", (col_a0, 0), (col_media - 1, 0)))
        estilo += [("SPAN", (col_media, 0), (col_media, 1)),
                   ("SPAN", (col_faltas, 0), (col_faltas, 1))]
    tab.setStyle(TableStyle(estilo))
    return tab


def _verso(datas, conteudos, professor):
    st_titulo = ParagraphStyle("t2", fontName="Helvetica-Bold", fontSize=14,
                               alignment=TA_CENTER, leading=18)
    st_cel = ParagraphStyle("cel", fontName="Helvetica", fontSize=9, leading=11.5)
    st_head = ParagraphStyle("hd", fontName="Helvetica-Bold", fontSize=9, leading=11)

    story = [Paragraph("LANÇAMENTO DA MATÉRIA LECIONADA", st_titulo), Spacer(1, 12)]

    w_data = 70
    linhas = [[Paragraph("Data", st_head), Paragraph("Conteúdo lecionado", st_head)]]
    for d in datas:
        linhas.append([
            Paragraph(_fmt_data(d, "%d/%m/%Y"), st_cel),
            Paragraph(_p(conteudos.get(d, "")).replace("\n", "<br/>"), st_cel),
        ])
    if not datas:
        linhas.append(["", ""])
    tab = Table(linhas, colWidths=[w_data, LARGURA_UTIL - w_data], repeatRows=1)
    tab.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, COR_BORDA),
        ("BACKGROUND", (0, 0), (-1, 0), COR_HEADER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story += [tab, Spacer(1, 16)]

    st_res = ParagraphStyle("res", fontName="Helvetica", fontSize=9, leading=12)
    resumo = Table(
        [[Paragraph("<b>RESUMO DO BIMESTRE</b>", st_res), "", "", ""],
         [Paragraph("<b>Aulas previstas:</b> ______", st_res),
          Paragraph(f"<b>Aulas dadas:</b> {len(datas)}", st_res),
          Paragraph("<b>Encerrado em:</b> ____/____/________", st_res),
          Paragraph(f"<b>Professor(a):</b> {_p(professor)}", st_res)]],
        colWidths=[LARGURA_UTIL * 0.20, LARGURA_UTIL * 0.20,
                   LARGURA_UTIL * 0.25, LARGURA_UTIL * 0.35],
    )
    resumo.setStyle(TableStyle([
        ("SPAN", (0, 0), (-1, 0)),
        ("BACKGROUND", (0, 0), (-1, 0), COR_HEADER),
        ("GRID", (0, 0), (-1, -1), 0.4, COR_BORDA),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(KeepTogether([resumo]))
    return story


def gerar_diario_pdf(instituicao, curso, materia, professor, turma, ano,
                     alunos, datas, chamadas, avals, notas, conteudos,
                     logo_bytes=None):
    """Retorna um BytesIO com o PDF (Frente + Verso), pronto para send_file."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        leftMargin=MARGEM, rightMargin=MARGEM, topMargin=MARGEM, bottomMargin=MARGEM,
        title=f"Diário de Classe - {_t(materia)} - {_t(turma)}",
        author=_t(instituicao) or "Sistema Escolar",
    )
    st_legenda = ParagraphStyle("leg", fontName="Helvetica-Oblique", fontSize=8,
                                textColor=colors.HexColor("#475569"))

    story = []
    blocos = _dividir_datas(datas, len(avals))
    for i, bloco in enumerate(blocos):
        ultimo = i == len(blocos) - 1
        titulo = "DIÁRIO DE CLASSE" + ("" if i == 0 else " (continuação)")
        story += _cabecalho(instituicao, curso, materia, professor, turma, ano,
                            logo_bytes, titulo)
        story.append(_tabela_frente(alunos, bloco, ultimo, avals, chamadas, notas, datas))
        story += [Spacer(1, 8),
                  Paragraph("Legenda: P = presente &nbsp;&nbsp; F = falta", st_legenda),
                  PageBreak()]

    story += _verso(datas, conteudos, professor)
    doc.build(story)
    buf.seek(0)
    return buf
