"""S1: A3 template (frame 390x277 + TCVN 5571 title block 180x65) -> TechDraw page -> Vietnamese text -> PDF/SVG.

Run: powershell -NoProfile -File scripts\\spike\\run_spike.ps1 -Name s1_titleblock
Then check the PDF geometry/fonts with: python -I scripts\\spike\\pdf_probe.py out\\spike\\s1_titleblock.pdf
"""
import os
import sys

sys.path.insert(0, os.environ.get("SPIKE_DIR", os.path.dirname(os.path.abspath(__file__))))
import _common as C  # noqa: E402

TEXTS = {
    "cell1_l1": "CÔNG TY TNHH THIẾT KẾ",
    "cell1_l2": "ắằẳẵặ ếềểễệ ốồổỗộ ớờởỡợ ứừửữự",   # glyph test (all tone marks on Ă Â Ê Ô Ơ Ư)
    "cell2_l1": "CÔNG TRÌNH: NHÀ XƯỞNG SẢN XUẤT",
    "cell2_l2": "CHỦ ĐẦU TƯ: CÔNG TY CP ĐẦU TƯ XÂY DỰNG",
    "cell3_l1": "MẶT BẰNG LƯỚI TRỤC VÀ CỘT",
    "cell3_l2": "NHÀ THÉP TIỀN CHẾ",
    "cell4": "KC-01",
    "cell5": "BVTC",
    "cell6": "18/11/2026",
    "cell7": "1:100",
    "cell15": "01",
}


def main():
    C.start("s1_titleblock")
    import FreeCAD
    import TechDrawGui  # noqa: F401  (GUI layer must be present)

    C.white_paper()
    tpl = C.write_template(os.path.join(C.OUT, "A3_TCVN5571_template.svg"))
    C.log("template written:", tpl, os.path.getsize(tpl), "bytes")
    doc = FreeCAD.newDocument("S1")
    page, tmpl = C.new_page(doc, tpl)
    C.log("editable fields found in template:", sorted(tmpl.EditableTexts.keys()) if hasattr(tmpl, "EditableTexts") else "n/a")
    tmpl.EditableTexts = TEXTS
    doc.recompute()
    out = C.export_page(page, "s1_titleblock")
    doc.saveAs(os.path.join(C.OUT, "s1_titleblock.FCStd"))
    C.log("EditableTexts after fill:", dict(tmpl.EditableTexts))
    C.log("outputs:", out)
    return os.path.isfile(out["pdf"]) and os.path.getsize(out["pdf"]) > 0


C.run(main)
