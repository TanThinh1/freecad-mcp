"""Run with FreeCADCmd: import the DXF named in DXF_IN (texts on) and print one 'FCRESULT {json}' line."""
import collections
import json
import os
import sys
import traceback

res = {"ok": False}
try:
    import FreeCAD
    import importDXF

    FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/Draft").SetBool("dxftext", True)
    doc = importDXF.open(os.environ["DXF_IN"])
    objs = doc.Objects
    layers = [o.Label for o in objs if getattr(o, "Proxy", None).__class__.__name__ == "Layer"]
    texts = [t for o in objs if getattr(o, "Text", None) for t in o.Text]
    res.update(ok=True, objects=len(objs), types=dict(collections.Counter(o.TypeId for o in objs)), layers=layers, texts=texts)
except Exception:  # noqa: BLE001
    res["error"] = traceback.format_exc()
sys.stdout.write("\nFCRESULT " + json.dumps(res, ensure_ascii=True) + "\n")
sys.stdout.flush()
os._exit(0)
