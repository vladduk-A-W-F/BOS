from pathlib import Path
import importlib.util,hashlib,json
s=Path('/workspace/scratch/c7b51e996a9f');r=Path('/workspace/sites/bos-original-refined');p=r/'finance/statement_csv.py';spec=importlib.util.spec_from_file_location('statement_csv',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
csv=s/'tmp/d03_final_candidate/docs/examples/BoS_Statement_Demo.csv';data=csv.read_bytes();result=m.parse(data)
assert result['row_count']==3 and {x['currency']:x['amount'] for x in result['rows']}=={'EUR':'17.39','USD':'123.45','UAH':'9801.07'}
assert all(x['booking_date']=='2026-09-12' and x['direction']=='in' and x['counterparty_external_id']==x['invoice_reference']=='' for x in result['rows'])
assert m.account('demo_guide','DEMO_ACCOUNT')==('demo_guide','DEMO_ACCOUNT')
assert len({x['external_id'] for x in result['rows']})==3
out={'complete':True,'scope':'Фактичний чистий CSV parser без Django setup, API, БД або проведення грошей.','parser_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'file_sha256':hashlib.sha256(data).hexdigest(),'row_count':result['row_count'],'source_totals':result['source_totals'],'source_system':'demo_guide','account_ref':'DEMO_ACCOUNT','empty_counterparty_and_invoice_references':True}
(s/'tmp/D03_CSV_ACTUAL.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out,ensure_ascii=False,indent=2))
