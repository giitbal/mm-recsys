import base64
import json
from pathlib import Path
import pandas as pd
import requests

root = Path('data/full-v44')
out = Path('docs/results/experiments/A/pdf_audit_20261115')
products = pd.read_parquet(root / 'products.parquet').set_index('product_id')
bag = products[(products.category_l2 == 'bags') & (products.color == 'brown')].iloc[0]
encoded = base64.b64encode((root / bag.image_path).read_bytes()).decode()
queries = {
    'text_pdf': dict(query_text='검정 오버핏 후드티'),
    'image_pdf': dict(query_image=encoded),
    'hybrid_pdf': dict(query_text='가방', query_image=encoded),
}
client = requests.Session()
client.trust_env = False
result = {'scope': 'Actual PDF example semantic checks against catalog attributes; no tuning', 'queries': {}}
for name, payload in queries.items():
    response = client.post('http://127.0.0.1:18000/api/search', json=payload, timeout=60)
    response.raise_for_status()
    body = response.json()
    rows = products.loc[[r['product_id'] for r in body['results']]]
    matching = ((rows.category_l3 == 'hoodie') & (rows.color == 'black') & (rows['style'] == 'oversized')) if name == 'text_pdf' else ((rows.category_l2 == 'bags') & (rows.color == 'brown'))
    result['queries'][name] = dict(response=body, default_top10=len(rows)==10, matching=int(matching.sum()), attributes=rows[['name','category_l2','category_l3','color','style']].reset_index().to_dict('records'))
result['status'] = 'PASS' if all(q['matching'] == 10 and q['default_top10'] for q in result['queries'].values()) else 'FAIL'
(out / 'semantic_examples.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(result['status'], {k:v['matching'] for k,v in result['queries'].items()})
