"""Nested H&M training cohorts with the original 2,000 evaluation users held fixed."""
from pathlib import Path
import json,time
import numpy as np
import pandas as pd
from src.common.artifacts import file_hash,fingerprint,write_json
from src.external_data.expansion_common import plan
from src.recommendation.datasets import read_data


def nested_users(original, all_ids, sizes, seed):
    first=sorted(original)
    if len(first)!=sizes[0] or sizes!=sorted(sizes) or sizes[-1]>len(all_ids):raise ValueError('invalid nested cohort sizes')
    rest=np.array(sorted(set(all_ids)-set(first)))
    chosen=np.random.default_rng(seed).choice(rest,sizes[-1]-len(first),replace=False).tolist()
    return first+chosen


def run():
    spec,work,results=plan();out=work/'hm_data';out.mkdir(exist_ok=True)
    if (results/'hm_data.json').exists():
        report=json.loads((results/'hm_data.json').read_text())
        if all(file_hash(Path(p))==h for p,h in report['hashes'].items()):print('H&M cohort cache verified');return
        raise ValueError('changed prepared cohorts')
    source=Path(spec['source_work']);data=read_data(source/'hm','valid')
    original=data['users'].user_id.str.removeprefix('HM-').tolist()
    all_ids=pd.read_csv(source/'hm_raw/customers.csv',usecols=['customer_id'],dtype=str).customer_id.tolist()
    ids=nested_users(original,all_ids,spec['training_sizes'],spec['seed']+1)
    write_json(out/'users.json',ids)
    selected=set(ids); cutoff=pd.Timestamp(data['manifest']['boundaries']['train']['end'])
    picked=[];started=time.perf_counter();seen=0
    raw=source/'hm_raw/transactions_train.csv'
    expected=json.loads((Path(spec['source_results'])/'hm_data.json').read_text())['source_members']['transactions_train.csv']['sha256']
    if file_hash(raw)!=expected:raise ValueError('changed H&M transactions')
    for frame in pd.read_csv(raw,usecols=['t_dat','customer_id','article_id'],dtype=str,chunksize=500000):
        rows=frame[(frame.t_dat<=str(cutoff.date())) & frame.customer_id.isin(selected)].copy()
        rows['event_id']=['HM-E'+str(i) for i in rows.index];picked.append(rows);seen+=len(frame)
        if seen%5000000==0:print('H&M source rows',seen,flush=True)
    tx=pd.concat(picked,ignore_index=True);del picked
    group_map={uid:i//spec['shard_users'] for i,uid in enumerate(ids)}
    tx['_shard']=tx.customer_id.map(group_map)
    hashes={str(out/'users.json'):file_hash(out/'users.json')};shards=[]
    for shard,frame in tx.groupby('_shard',sort=True):
        events=pd.DataFrame(dict(event_id=frame.event_id,user_id='HM-'+frame.customer_id,
            product_id='HM-'+frame.article_id,event_type='purchase',timestamp=pd.to_datetime(frame.t_dat,utc=True),
            session_id='HM-DAY-'+frame.customer_id+'-'+frame.t_dat,query=None,impression_id=None,position=None))
        path=out/f'shard-{int(shard):03d}.parquet';events.to_parquet(path,index=False)
        hashes[str(path)]=file_hash(path);shards.append(dict(number=int(shard),rows=len(events),path=str(path)))
    first=pd.concat([pd.read_parquet(s['path']) for s in shards if s['number']<2],ignore_index=True)
    assert set(first.event_id)==set(data['train'].event_id) and len(first)==len(data['train'])
    counts={str(size):sum(s['rows'] for s in shards if s['number']<size//spec['shard_users']) for size in spec['training_sizes']}
    write_json(results/'hm_data.json',dict(status='PASS',acceptance='UNMEASURED',source_sha256=expected,
        training_users=spec['training_sizes'],training_events=counts,shards=shards,hashes=hashes,
        original_data_fingerprint=data['manifest']['generation_fingerprint'],eval_users=2000,products=len(data['products']),
        cohort_policy='original uniform 2000 plus fixed seeded uniform additional customers; nested; no outcome filtering',
        scope='train only expansion; original valid/test users and truth/catalog retained',seconds=time.perf_counter()-started))
    print('H&M preparation complete',counts,flush=True)

if __name__=='__main__':run()
