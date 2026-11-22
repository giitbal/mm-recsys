"""Four calibration conditions and three matched seeds, with fresh model fits."""
import copy,json
from pathlib import Path
import numpy as np
import pandas as pd
import yaml
from src.common.artifacts import file_hash,fingerprint,write_json
from src.common.config import load_config
from src.external_data.calibration import calibrated_config
from src.external_data.expansion_common import plan
from src.external_data.retailrocket import transition_counts,probabilities
from src.recommendation.train_two_tower import train as train_candidate
from src.recommendation.train_deepfm import train as train_ranking
from src.recommendation.eval_ranking import evaluate
from src.recommendation.datasets import read_data
from src.recommendation.train_two_tower import load_bundle
from src.recommendation.eval_candidate import Evaluation
from src.simulator.generate import generate


def conditions(base: dict, hm: dict, retail: dict) -> dict[str, dict]:
    combined=calibrated_config(base,hm,retail,.5)
    hm_only=copy.deepcopy(base);retail_only=copy.deepcopy(base)
    for key in ['personas','category_price_ranges']:hm_only['simulator'][key]=copy.deepcopy(combined['simulator'][key])
    for key in ['transitions','cart_reference_cvr']:retail_only['simulator'][key]=copy.deepcopy(combined['simulator'][key])
    return dict(original=copy.deepcopy(base),hm=hm_only,retailrocket=retail_only,both=combined)


def distribution(cfg: dict, hm: dict, retail: dict) -> dict:
    root=Path(cfg['paths']['data_dir']);events=pd.read_parquet(root/'events.parquet');products=pd.read_parquet(root/'products.parquet')
    purchases=events[events.event_type=='purchase'].merge(products[['product_id','category_l1','price']],on='product_id',how='left')
    categories=list(hm['category_purchase_shares']);observed=purchases.category_l1.value_counts(normalize=True)
    shares={k:float(observed.get(k,0)) for k in categories}
    relative=(purchases.groupby('category_l1').price.mean()/purchases.price.mean()).to_dict()
    state=events[events.event_type.isin(['view','cart','purchase'])].rename(columns={'user_id':'visitorid','event_type':'event'}).copy();state['row_id']=np.arange(len(state))
    counts,diagnostics=transition_counts(state,events.timestamp.max(),1800);rates=probabilities(counts,0)
    return dict(category_purchase_shares=shares,relative_category_price=relative,
        category_total_variation=sum(abs(shares[k]-hm['category_purchase_shares'][k]) for k in categories)/2,
        relative_price_mae=float(np.mean([abs(relative[k]-hm['relative_category_price'][k]) for k in categories])),
        transitions=rates,transition_total_variation={s:sum(abs(rates[s][d]-retail['fitted_transitions'][s][d]) for d in rates[s])/2 for s in rates},
        diagnostics=diagnostics)


def run() -> None:
    spec,work,results=plan();hm=json.loads((Path(spec['source_results'])/'hm_data.json').read_text())['calibration']
    retail=json.loads((Path(spec['source_results'])/'retailrocket.json').read_text());base=load_config();summary=[]
    for seed in spec['simulator']['seeds']:
        for name,cfg in conditions(base,hm,retail).items():
            tag=f'{seed}-{name}';root=work/'simulator'/tag;output=results/'simulator'/tag;output.mkdir(parents=True,exist_ok=True)
            complete=output/'comparison.json'
            if complete.exists():summary.append(json.loads(complete.read_text()));continue
            cfg['seed']=seed;cfg['scale']='dev'
            cfg['simulator'].update(n_products=spec['simulator']['products'],n_users=spec['simulator']['users'],n_events=spec['simulator']['events'])
            cfg['paths'].update(data_dir=str(root/'data'),model_dir=str(root/'models'),results_dir=str(output),split_dir=str(root/'data/split'))
            cfg['recommend']['candidate'].update(epochs=spec['simulator']['candidate_epochs'],threads=spec['threads'],batch_size=spec['batch_size'])
            cfg['recommend']['ranking'].update(epochs=spec['simulator']['ranking_epochs'],threads=spec['threads'])
            root.mkdir(parents=True,exist_ok=True);(root/'config.yaml').write_text(yaml.safe_dump(cfg,sort_keys=False))
            manifest=generate(cfg);observed=distribution(cfg,hm,retail)
            if not (root/'models/v1.0/meta.json').exists():train_candidate(cfg,output/'candidate_training.json',root/'models/v1.0')
            if not (output/'ranking_selection_dev.json').exists():train_ranking(cfg)
            valid=evaluate(cfg,'valid',output=output/'ranking_valid.json')
            write_json(output/'selection.json',dict(status='FROZEN',config_fingerprint=fingerprint(cfg),
                model_hashes={str(p):file_hash(p) for p in (root/'models').rglob('*.pt')},
                data_fingerprint=manifest['generation_fingerprint']))
            data=read_data(root/'data','test');model,encoder,table,_=load_bundle(root/'models/v1.0',data,cfg)
            recall=Evaluation(data,encoder,table,cfg,'test').model(model)
            test=evaluate(cfg,'test',output=output/'ranking_test.json')
            record=dict(status='PASS',acceptance='UNMEASURED',condition=name,seed=seed,distribution=observed,
                test_candidate=recall,test_ranking=test['metrics'],classification=test['classification'],
                data_fingerprint=manifest['generation_fingerprint'],config_fingerprint=fingerprint(cfg))
            write_json(complete,record);summary.append(record);print('Simulator condition complete',tag,flush=True)
    aggregates={}
    for name in ['original','hm','retailrocket','both']:
        rows=[r for r in summary if r['condition']==name]
        values={'category_tv':[r['distribution']['category_total_variation'] for r in rows],
            'relative_price_mae':[r['distribution']['relative_price_mae'] for r in rows],
            'recall_at_300':[r['test_candidate']['recall_at_300'] for r in rows],
            'deepfm_ndcg_at_50':[r['test_ranking']['deepfm']['ndcg_at_50'] for r in rows]}
        for state in ['view','cart','purchase']:values[f'{state}_tv']=[r['distribution']['transition_total_variation'][state] for r in rows]
        aggregates[name]={k:dict(mean=float(np.mean(v)),std=float(np.std(v,ddof=1)),values=v) for k,v in values.items()}
    write_json(results/'simulator_comparison.json',dict(status='PASS',acceptance='UNMEASURED',seeds=spec['simulator']['seeds'],conditions=aggregates,
        scale=spec['simulator'],runs=len(summary),
        interpretation='distribution closeness and synthetic recommendation difficulty are separate; each condition has its own generated truth; no real-world lift claim'))

if __name__=='__main__':run()
