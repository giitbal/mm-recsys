"""Temporal category/activity-conditioned Markov models with train-only shrinkage."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from src.common.artifacts import file_hash,write_json,fingerprint
from src.external_data.expansion_common import plan
from src.external_data.retailrocket import transition_counts

STATES=['view','cart','purchase','exit']


def observed_pairs(events: pd.DataFrame, end: pd.Timestamp, seconds: int) -> pd.DataFrame:
    frame=events.sort_values(['visitorid','timestamp','row_id'],kind='stable').copy()
    group=frame.groupby('visitorid',sort=False);nxt=group.timestamp.shift(-1)
    gap=nxt-frame.timestamp;window=pd.Timedelta(seconds=seconds)
    tied=frame.duplicated(['visitorid','timestamp'],keep=False)
    next_tied=tied.groupby(frame.visitorid).shift(-1,fill_value=False)
    linked=gap.gt(pd.Timedelta(0)) & gap.le(window) & ~tied & ~next_tied
    exited=(gap.gt(window)|nxt.isna()) & (frame.timestamp+window<=end) & ~tied
    frame['next']=group.event.shift(-1);frame.loc[exited,'next']='exit'
    return frame.loc[linked|exited].copy()


def categories_asof(events: pd.DataFrame, properties: pd.DataFrame) -> pd.Series:
    if properties.duplicated(['itemid','timestamp']).any():
        conflicts=properties.groupby(['itemid','timestamp']).value.nunique()
        if (conflicts>1).any():raise ValueError('ambiguous property timestamps')
        properties=properties.drop_duplicates(['itemid','timestamp'])
    left=events.sort_values('timestamp',kind='stable')
    right=properties.sort_values('timestamp',kind='stable')
    merged=pd.merge_asof(left,right,on='timestamp',by='itemid',direction='backward',allow_exact_matches=False)
    return merged.set_index('row_id').value.fillna('unknown')


def keys(frame: pd.DataFrame, kind: str) -> pd.Series:
    if kind=='global':return pd.Series('all',index=frame.index)
    if kind=='category':return frame.category.astype(str)
    if kind=='activity':return frame.activity.astype(str)
    return frame.category.astype(str)+'/'+frame.activity.astype(str)


def fit(frame: pd.DataFrame, kind: str) -> pd.Series:
    counts=frame.assign(key=keys(frame,kind)).groupby(['key','event','next']).size()
    return counts


def predict(frame: pd.DataFrame, kind: str, counts: pd.Series, global_probs: np.ndarray, alpha: float) -> np.ndarray:
    group_key=keys(frame,kind).to_numpy();origin=frame.event.map(dict(zip(STATES,range(4)))).to_numpy()
    unique,inverse=np.unique(np.array([f'{k}|{o}' for k,o in zip(group_key,frame.event)]),return_inverse=True)
    matrices=np.empty((len(unique),4))
    for i,key in enumerate(unique):
        name,state=key.rsplit('|',1);row=np.array([counts.get((name,state,d),0) for d in STATES],float)
        prior=global_probs[STATES.index(state)]
        matrices[i]=(row+alpha*prior)/(row.sum()+alpha)
    return matrices[inverse]


def score(frame: pd.DataFrame, probabilities: np.ndarray) -> dict:
    target=frame.next.map(dict(zip(STATES,range(4)))).to_numpy()
    if not np.isfinite(probabilities).all() or not np.allclose(probabilities.sum(axis=1),1):raise ValueError('invalid Markov probabilities')
    p=probabilities[np.arange(len(frame)),target]
    return dict(observations=len(frame),nll=float(-np.log(p).mean()),
        brier=float(((probabilities-np.eye(4)[target])**2).sum(axis=1).mean()))


def run() -> None:
    spec,work,results=plan();root=Path(spec['source_work'])/'retailrocket_raw'
    old=json.loads((Path(spec['source_results'])/'retailrocket.json').read_text())
    for name,record in old['source_members'].items():
        if file_hash(root/name)!=record['sha256']:raise ValueError('changed Retailrocket source')
    events=pd.read_csv(root/'events.csv',usecols=['timestamp','visitorid','event','itemid'])
    events.timestamp=pd.to_datetime(events.timestamp,unit='ms',utc=True);events.event=events.event.map({'view':'view','addtocart':'cart','transaction':'purchase'})
    events['row_id']=np.arange(len(events));events=events.sort_values(['visitorid','timestamp','row_id'],kind='stable')
    previous=events.groupby('visitorid').cumcount()-events.groupby(['visitorid','timestamp']).cumcount()
    events['activity']=np.digitize(previous,spec['retailrocket']['activity_thresholds'])
    property_frames=[]
    for name in ['item_properties_part1.csv','item_properties_part2.csv']:
        for chunk in pd.read_csv(root/name,dtype={'property':str,'value':str},chunksize=500000):
            property_frames.append(chunk.loc[chunk.property=='categoryid',['timestamp','itemid','value']])
    properties=pd.concat(property_frames,ignore_index=True);properties.timestamp=pd.to_datetime(properties.timestamp,unit='ms',utc=True)
    category=categories_asof(events[['row_id','timestamp','itemid']],properties)
    events['category']=events.row_id.map(category)
    tree=pd.read_csv(Path(spec['source_dir'])/'category_tree.csv');known=set(tree.categoryid.astype(str))
    diagnostics=dict(events=len(events),property_category_rows=len(properties),unknown_category_events=int(events.category.eq('unknown').sum()),
        categories=int(events.category.nunique()),tree_categories=len(known),events_with_category_outside_tree=int((~events.category.isin(known|{'unknown'})).sum()))
    a=pd.Timestamp(old['split_boundaries']['train_end']);b=pd.Timestamp(old['split_boundaries']['valid_end'])
    splits={'train':events[events.timestamp<=a],'valid':events[(events.timestamp>a)&(events.timestamp<=b)],'test':events[events.timestamp>b]}
    pairs={k:observed_pairs(v,v.timestamp.max(),spec['retailrocket']['session_seconds']) for k,v in splits.items()}
    # Exact agreement with the existing global transition definition is required.
    for split,frame in splits.items():
        reference,_=transition_counts(frame,frame.timestamp.max(),spec['retailrocket']['session_seconds'])
        actual=pairs[split].groupby(['event','next']).size()
        assert all(int(actual.get((s,d),0))==n for s,row in reference.items() for d,n in row.items())
    train_counts=pairs['train'].groupby(['event','next']).size()
    matrix=np.array([[train_counts.get((s,d),0)+1 for d in STATES] for s in STATES[:3]],float);matrix/=matrix.sum(axis=1,keepdims=True)
    methods=['global','category','activity','category_activity'];models={k:fit(pairs['train'],k) for k in methods}
    trials: list[dict] = []
    origins=pairs['valid'].event.map(dict(zip(STATES,range(4)))).to_numpy()
    trials.append(dict(method='global',alpha=0,valid=score(pairs['valid'],matrix[origins])))
    for method in methods[1:]:
        for alpha in spec['retailrocket']['smoothing_strengths']:
            trials.append(dict(method=method,alpha=alpha,valid=score(pairs['valid'],predict(pairs['valid'],method,models[method],matrix,alpha))))
    best=min(trials,key=lambda v:v['valid']['nll'])
    write_json(results/'retail_selection.json',dict(status='FROZEN',trials=trials,selected=best,spec_fingerprint=fingerprint(spec),
        source_hashes={str(root/k):v['sha256'] for k,v in old['source_members'].items()},
        policy='category last observed strictly before origin event; activity counts strictly earlier events; train-only fit; unknown groups shrink to global'))
    test=[]
    for method in methods:
        chosen=min((t for t in trials if t['method']==method),key=lambda t:t['valid']['nll'])
        frame=pairs['test'];origins=frame.event.map(dict(zip(STATES,range(4)))).to_numpy()
        predicted=matrix[origins] if method=='global' else predict(frame,method,models[method],matrix,chosen['alpha'])
        test.append(dict(method=method,alpha=chosen['alpha'],metrics=score(frame,predicted)))
    cache=work/'retail_conditional';cache.mkdir(exist_ok=True)
    for method,counts in models.items():counts.rename('count').reset_index().to_parquet(cache/f'{method}.parquet',index=False)
    write_json(results/'retail_conditional.json',dict(status='PASS',acceptance='UNMEASURED',diagnostics=diagnostics,selected=best,
        test=test,global_matrix=matrix.tolist(),counts={k:len(v) for k,v in pairs.items()},
        model_hashes={str(p):file_hash(p) for p in cache.glob('*.parquet')},
        limitations=['observed transitions only; same-timestamp ambiguity and boundary censoring retained',
        'category hierarchy inventory checked; models condition on observed property category IDs, not assumed hierarchy levels or semantic labels',
        'no search or persona labels; no causal or production claim']))
    print('Retailrocket selected',best,'test',test,flush=True)

if __name__=='__main__':run()
