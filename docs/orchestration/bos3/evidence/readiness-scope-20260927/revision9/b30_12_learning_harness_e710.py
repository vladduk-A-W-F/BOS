#!/usr/bin/env python3
"""One-run, fail-closed B30-12 learning contract harness.

Authoring this file authorizes no execution. It performs no work unless invoked
with --execute and a reviewed manifest whose exact exception ID is repeated on
the command line. It uses Django's CSRF-protected JSON login and in-process
test client; this is server-contract QA, never browser/E2E or network hosting.
"""
from __future__ import annotations

import argparse, hashlib, json, os, sys
import re
from pathlib import Path

E710 = "e710eb568717dfe3ede945feb899f030bd5ad1ab"
F55 = "f55a15de4006d10c0d7c65f8a2ca8499fbb99819"
ROOT = Path(r"D:\3\BOSDev\qa-runs\b30-12-learning-f55-r1")
SOURCE = Path(r"C:\Users\user\.codex\worktrees\bos3-learning-proof\repo")
DB = ROOT / "data" / "bos3-fasteners-f55-r1.sqlite3"
MEDIA = ROOT / "media"
EVIDENCE = ROOT / "evidence"
RUN_MARKER = ROOT / "RUN_MANIFEST.json"
PINS = {
 "erp/management/commands/seed_bos3_fasteners.py":"3b14d16e7f0c5289ce859418c84406a870a135e8",
 "erp/seed/bos3_fasteners_uk_v1.json":"ad2b54804a560e6e8b92affdb10b9bfb2859f9df",
 "training/access.py":"d533ee467172fe804215ff23826714d82c619612",
 "training/service.py":"f982fb72e17590dfd6380789f009bfb5ec4a6c86",
 "training/test_sessions.py":"c9e75afc4641830d9e4a849b49d32671c4a0b719",
 "erp/service.py":"a4b8e1d915c38f4abbe0ecb2aba192475d343c64",
 "erp/views.py":"df0c607e3645ba5bd0e231509a53ab3ca62f4ea7",
 "erp/urls.py":"e17a8263e7ebd9a58dd2656b1568a338dfdc5934",
 "operations/service.py":"64e74153947d47db19cba3bb370d3a078da412d4",
 "operations/urls.py":"3c0e8bc4f6623f48a82a15a361620a393b01f148",
 "crm/commands.py":"d5392bed7d7fc0305c896f62ab987ee1d2ab4a5a",
 "tasks/commands.py":"3031855111a1906004b0bf628e097520b181e6cd",
 "bos3_local_settings.py":"7e9a929fb381293371fcdc20208229d7df3a6c31",
}

class Stop(RuntimeError): pass
def fail(msg): raise Stop(msg)
def sha(p):
    h=hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()
def tree(root):
    root=Path(root); return {str(p.relative_to(root)).replace("\\","/"):sha(p)
      for p in sorted(root.rglob("*")) if p.is_file()}
def dump(path, value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2),encoding="utf-8")
def load(path): return json.loads(Path(path).read_text(encoding="utf-8"))

def parse():
    p=argparse.ArgumentParser()
    p.add_argument("--execute",action="store_true")
    p.add_argument("--manifest",type=Path)
    p.add_argument("--manifest-sha256")
    p.add_argument("--owner-exception-id")
    return p.parse_args()

def preflight(a):
    if not a.execute: fail("REFUSED: --execute is required; preparation never executes.")
    if not a.manifest or not a.manifest.is_file() or not a.owner_exception_id or not a.manifest_sha256: fail("REFUSED: reviewed manifest, exact exception ID and manifest SHA-256 are required.")
    blocked=("REPLACE","PENDING","TBD","EXAMPLE","OWNER_EXCEPTION_NOT_GRANTED")
    if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}",a.owner_exception_id)
            or any(x in a.owner_exception_id.upper() for x in blocked)
            or not re.fullmatch(r"[0-9a-fA-F]{64}",a.manifest_sha256)
            or sha(a.manifest).lower()!=a.manifest_sha256.lower()): fail("REFUSED: placeholder exception ID or reviewed manifest SHA-256 mismatch.")
    m=load(a.manifest)
    if m.get("schema")!="bos.b30-12.learning-run.v1" or m.get("owner_exception_id")!=a.owner_exception_id: fail("REFUSED: manifest/exception binding mismatch.")
    if m.get("candidate")!=E710 or m.get("origin")!=F55 or m.get("blobs")!=PINS: fail("REFUSED: candidate or blob allowlist mismatch.")
    if m.get("automatic_retry") is not False or m.get("runs_authorized")!=1: fail("REFUSED: one-run/no-retry contract mismatch.")
    if m.get("root")!=str(ROOT) or m.get("db")!=str(DB) or m.get("media")!=str(MEDIA) or m.get("evidence")!=str(EVIDENCE): fail("REFUSED: isolated-path contract mismatch.")
    if any(p.exists() for p in (ROOT,DB,MEDIA,EVIDENCE,RUN_MARKER)): fail("REFUSED: target path exists; no reset or cleanup is permitted.")
    source=Path(m.get("source",""))
    if source.resolve()!=SOURCE.resolve() or not source.is_dir() or source.resolve()==ROOT.resolve(): fail("REFUSED: source must be the dedicated clean bos3-learning-proof checkout.")
    # Git is intentionally checked before importing Django or creating any path.
    import subprocess
    head=subprocess.run(["git","-C",str(source),"rev-parse","HEAD"],text=True,capture_output=True,check=True).stdout.strip()
    if head!=E710: fail("REFUSED: source HEAD is not immutable e710.")
    if subprocess.run(["git","-C",str(source),"status","--porcelain"],text=True,capture_output=True,check=True).stdout.strip(): fail("REFUSED: source checkout is dirty before any filesystem write or Django import.")
    for rel, expected in PINS.items():
        got=subprocess.run(["git","-C",str(source),"rev-parse",f"{E710}:{rel}"],text=True,capture_output=True,check=True).stdout.strip()
        if got!=expected: fail("REFUSED: blob pin mismatch: "+rel)
    if DB.name=="db.sqlite3" or "bos3-fasteners" not in DB.name: fail("REFUSED: training DB filename guard mismatch.")
    required={"BOS3_LOCAL_SECRET","B30_12_OWNER_PASSWORD","BOS3_TRAINING_OWNER_USERNAME","BOS3_TRAINING_INSTALLATION_ID"}
    if any(not os.environ.get(k) for k in required): fail("REFUSED: protected bootstrap secret/identity input absent.")
    return m,source

def setup(source):
    # This runs only after the preflight has accepted the owner exception.
    os.environ.update({"DJANGO_SETTINGS_MODULE":"bos3_local_settings","BOS3_LOCAL_SOURCE":str(source),"BOS3_LOCAL_ROOT":str(ROOT),"BOS3_LOCAL_DB":str(DB),"BOS3_LOCAL_MEDIA":str(MEDIA),"BOS3_TRAINING_ENABLED":"1","BOS3_TRAINING_PROFILE":"isolated-synthetic","BOS3_TRAINING_DB_MARKER":"bos3-fasteners-uk-v1","BOS_DATA_MODE":"demo"})
    sys.path.insert(0,str(source)); import django; django.setup()
    return django

def response(client, method, path, body=None, status=200, evidence=None):
    data=json.dumps(body,ensure_ascii=False) if body is not None else None
    headers={"content_type":"application/json"}
    token=client.cookies.get("csrftoken")
    if method=="POST": headers["HTTP_X_CSRFTOKEN"]=token.value if token else ""
    r=getattr(client,method.lower())(path,data,**headers) if data is not None else getattr(client,method.lower())(path)
    # Authentication is proven by status/role only; its password never reaches evidence.
    stored_body={k:("<redacted>" if k=="password" else v) for k,v in body.items()} if path=="/api/auth/login/" else body
    record={"method":method,"path":path,"status":r.status_code,"body":stored_body,"response":json.loads(r.content.decode("utf-8")) if r.content else None}
    evidence.append(record)
    if r.status_code!=status: fail(f"ASSERT: {method} {path} expected {status}, got {r.status_code}")
    return record["response"]

def login(password, evidence):
    from django.test import Client
    c=Client(enforce_csrf_checks=True)
    response(c,"GET","/api/auth/csrf/",evidence=evidence)
    username=os.environ["BOS3_TRAINING_OWNER_USERNAME"]
    who=response(c,"POST","/api/auth/login/",{"username":username,"password":password},evidence=evidence)
    if who.get("role")!="ceo": fail("ASSERT: protected login did not receive ceo role.")
    return c

def confirmed(client, payload, evidence, erp=False, assert_receipt=None):
    preview=response(client,"POST","/api/erp/preview/" if erp else "/api/operations/preview/",payload,evidence=evidence)
    if not preview.get("id"): fail("ASSERT: mutating preview lacks proposal ID.")
    receipt=response(client,"POST","/api/operations/confirm/",{"proposal_id":preview["id"],"confirmed":True},evidence=evidence)
    replay=response(client,"POST","/api/operations/confirm/",{"proposal_id":preview["id"],"confirmed":True},evidence=evidence)
    if replay!=receipt: fail("ASSERT: same-proposal replay differs from first receipt.")
    if assert_receipt: assert_receipt(receipt)
    return receipt
def tstart(c,case,e): return response(c,"POST",f"/api/training/sessions/{case}/start/",{},evidence=e)
def tcheck(c,case,step,value,e): return response(c,"POST",f"/api/training/sessions/{case}/check/",{"step_id":step,"answers":{"value":value}} if value is not None else {"step_id":step},evidence=e)
def handoff(c,session,case,e):
    draft=response(c,"GET",f"/api/crm/handoff/{session}/?case_id={case}",evidence=e)
    if draft.get("existing") or draft.get("schema")!="crm.handoff-draft.v1": fail("ASSERT: expected a new typed CRM handoff draft.")
    return confirmed(c,draft["payload"],e,erp=False)
def completed(c,case,session,steps,e):
    state=response(c,"GET",f"/api/training/sessions/{case}/",evidence=e)
    if state.get("session_id")!=session or state.get("status")!="completed": fail("ASSERT: case/session completion mismatch.")
    if {x["id"] for x in state["steps"] if x["status"]=="completed"}!=set(steps): fail("ASSERT: completed step set mismatch.")

def cases(c,e):
    from operations.models import Configuration, Invoice
    from erp.models import Lot, Movement, Production
    marker=Configuration.objects.get(key="bos3_fixture").value; sm=marker["source_map"]
    # C1: source-derived IDs only.
    c1=tstart(c,"BOS3-CASE-01",e); s1=c1["session_id"]; tcheck(c,"BOS3-CASE-01","order",500,e); tcheck(c,"BOS3-CASE-01","supply",120,e)
    x=sm["BOS3-CASE-01"]; loc=sm["locations"]["production"]; people=sm["people"]
    r=confirmed(c,{"action":"erp_receive","purchase_id":x["purchase_id"],"code":"B3-C1-RCV-101","location_id":loc,"quantity":"120"},e,erp=True,assert_receipt=lambda q: q.get("code")=="B3-C1-RCV-101" and q.get("quality")=="pending" and q.get("lot_id") or fail("ASSERT: C1 receive receipt mismatch")); rec_lot=r["lot_id"]
    if str(__import__("erp.models",fromlist=["Purchase"]).Purchase.objects.get(pk=x["purchase_id"]).received)!="120.000": fail("ASSERT: C1 purchase received must equal 120.000")
    confirmed(c,{"action":"erp_quality","lot_id":rec_lot,"result":"approved","inspector_id":people["quality"],"note":"Навчальна перевірка приймання шайб."},e,erp=True); tcheck(c,"BOS3-CASE-01","receipt",None,e)
    for key,q in (("bolt","360"),("nut","720"),("washer","600")):
        confirmed(c,{"action":"erp_reserve","lot_id":x["component_lot_ids"][key],"production_id":x["production_id"],"quantity":q},e,erp=True,assert_receipt=lambda z, qty=q: z.get("reservation_id") and z.get("quantity")==qty or fail("ASSERT: C1 reserve receipt mismatch"))
    confirmed(c,{"action":"erp_reserve","lot_id":rec_lot,"production_id":x["production_id"],"quantity":"120"},e,erp=True,assert_receipt=lambda z: z.get("reservation_id") and z.get("quantity")=="120" or fail("ASSERT: C1 received-washer reserve mismatch"))
    confirmed(c,{"action":"erp_start","production_id":x["production_id"]},e,erp=True,assert_receipt=lambda z: z.get("production_id")==x["production_id"] and z.get("status")=="running" or fail("ASSERT: C1 start receipt mismatch"))
    job=Production.objects.get(pk=x["production_id"])
    for row in job.routing: confirmed(c,{"action":"erp_operator","production_id":job.pk,"operation":row["name"],"operator_id":job.owner_id,"result":"done","minutes":30,"defects":"0","note":"Навчальна операція виконана."},e,erp=True)
    r=confirmed(c,{"action":"erp_finish","production_id":job.pk,"quantity":"360","code":"B3-C1-FG-101","location_id":loc,"labor_cost":"288.00"},e,erp=True,assert_receipt=lambda z: z.get("production_id")==job.pk and z.get("lot_id") and z.get("cost")=="4320.00" or fail("ASSERT: C1 finish receipt mismatch"))
    job.refresh_from_db()
    if str(job.produced)!="360.000" or str(job.actual_cost)!="4320.00" or job.status!="done": fail("ASSERT: C1 final production state mismatch")
    confirmed(c,{"action":"erp_quality","lot_id":r["lot_id"],"result":"approved","inspector_id":job.owner_id,"note":"Навчальний допуск готових комплектів."},e,erp=True); tcheck(c,"BOS3-CASE-01","production",None,e); handoff(c,s1,"BOS3-CASE-01",e); tcheck(c,"BOS3-CASE-01","crm",None,e); completed(c,"BOS3-CASE-01",s1,["order","supply","receipt","production","crm"],e)
    # C2: blocked lot is an invariant, not an action target.
    c2=tstart(c,"BOS3-CASE-02",e); s2=c2["session_id"]; tcheck(c,"BOS3-CASE-02","order",250,e); tcheck(c,"BOS3-CASE-02","quality",20,e); x=sm["BOS3-CASE-02"]; blocked=Lot.objects.get(pk=x["blocked_lot_id"]); before=(str(blocked.quantity),blocked.quality)
    confirmed(c,{"action":"erp_reserve","lot_id":x["approved_lot_id"],"line_id":x["line_id"],"quantity":"250"},e,erp=True,assert_receipt=lambda z: z.get("reservation_id") and z.get("quantity")=="250" or fail("ASSERT: C2 reserve receipt mismatch")); tcheck(c,"BOS3-CASE-02","reservation",None,e)
    confirmed(c,{"action":"erp_ship","line_id":x["line_id"],"lot_id":x["approved_lot_id"],"quantity":"250","reference":x["shipment_reference"]},e,erp=True,assert_receipt=lambda z: z.get("line_id")==x["line_id"] and z.get("shipped")=="250" and z.get("reference")==x["shipment_reference"] or fail("ASSERT: C2 ship receipt mismatch")); tcheck(c,"BOS3-CASE-02","shipment",None,e); blocked.refresh_from_db()
    if (str(blocked.quantity),blocked.quality)!=before: fail("ASSERT: C2 blocked lot changed.")
    if not Movement.objects.filter(kind="shipment",reference=x["shipment_reference"],lot_id=x["approved_lot_id"]).exists(): fail("ASSERT: C2 shipment source mismatch.")
    from operations.models import ActionProposal
    handoff(c,s2,"BOS3-CASE-02",e); tcheck(c,"BOS3-CASE-02","crm",None,e); proposals=ActionProposal.objects.count(); existing=response(c,"GET",f"/api/crm/handoff/{s2}/?case_id=BOS3-CASE-02",evidence=e)
    if existing.get("existing") is not True or ActionProposal.objects.count()!=proposals: fail("ASSERT: C2 second handoff was not existing/no-new-proposal")
    completed(c,"BOS3-CASE-02",s2,["order","quality","reservation","shipment","crm"],e)
    # C3: historical payment must remain unchanged.
    c3=tstart(c,"BOS3-CASE-03",e); s3=c3["session_id"]; tcheck(c,"BOS3-CASE-03","invoice",6400,e); x=sm["BOS3-CASE-03"]; inv=Invoice.objects.get(pk=x["invoice_id"]); money=(str(inv.amount),str(inv.paid))
    task_receipt=confirmed(c,{"action":"create_task","title":"Узгодити оплату B3-C3","assignee_id":x["owner_id"],"deadline":"2026-10-01","order_id":x["order_id"],"category":"Фінанси","priority":"medium"},e,erp=False,assert_receipt=lambda z: z.get("state")=="succeeded" and z.get("task_id") and z.get("audit_id") or fail("ASSERT: C3 task receipt mismatch"))
    from tasks.models import Task
    task=Task.objects.get(pk=task_receipt["task_id"])
    if task.sales_order_id!=x["order_id"] or task.assignee_employee_id!=x["owner_id"]: fail("ASSERT: C3 task source references mismatch")
    tcheck(c,"BOS3-CASE-03","followup",None,e); handoff(c,s3,"BOS3-CASE-03",e); tcheck(c,"BOS3-CASE-03","crm",None,e); inv.refresh_from_db()
    if (str(inv.amount),str(inv.paid))!=money or money!=("16400.00","10000.00"): fail("ASSERT: C3 historical invoice/payment changed.")
    completed(c,"BOS3-CASE-03",s3,["invoice","followup","crm"],e)
    return [("BOS3-CASE-01",s1),("BOS3-CASE-02",s2),("BOS3-CASE-03",s3)]

def main():
    a=parse(); m,source=preflight(a); ROOT.mkdir(parents=True); DB.parent.mkdir(); MEDIA.mkdir(); EVIDENCE.mkdir()
    # Manifest is copied before bootstrap; passwords are never serialised.
    safe={k:v for k,v in m.items() if "secret" not in k.lower() and "password" not in k.lower()}; dump(RUN_MARKER,safe)
    try:
        setup(source)
        from django.core.management import call_command
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Group
        from django.db import connection
        call_command("migrate",verbosity=0,interactive=False)
        owner=get_user_model().objects.create_user(username=os.environ["BOS3_TRAINING_OWNER_USERNAME"],password=os.environ["B30_12_OWNER_PASSWORD"]); owner.groups.add(Group.objects.get_or_create(name="ceo")[0])
        call_command("seed_bos3_fasteners",owner_username=owner.username,verbosity=0)
        baseline={"database_sha256":sha(DB),"media":tree(MEDIA),"candidate":E710,"origin":F55}
        e=[]; c=login(os.environ["B30_12_OWNER_PASSWORD"],e); sessions=cases(c,e)
        # Protected relogin uses password auth again, never force_login.
        c2=login(os.environ["B30_12_OWNER_PASSWORD"],e)
        for case,sid in sessions: completed(c2,case,sid,[x["id"] for x in response(c2,"GET",f"/api/training/sessions/{case}/",evidence=e)["steps"]],e)
        dump(EVIDENCE/"requests.json",e); dump(EVIDENCE/"db-before-after.json",{"before_learning":baseline,"after_learning":{"database_sha256":sha(DB),"media":tree(MEDIA)},"candidate":E710,"origin":F55,"result":"PASS_SCOPED"})
    except Exception as exc:
        if EVIDENCE.exists(): dump(EVIDENCE/"STOP.json",{"result":"STOPPED","error":type(exc).__name__,"message":str(exc)})
        raise
if __name__=="__main__":
    try: main()
    except Stop as exc: raise SystemExit(str(exc))
