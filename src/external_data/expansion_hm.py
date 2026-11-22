"""Memory-bounded, matched H&M learning curves and content feature ablations."""
from __future__ import annotations
import argparse,copy,gc,json,sys,time,multiprocessing
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.nn import functional as F
from src.common.artifacts import file_hash,fingerprint,write_json
from src.common.seed import set_seed
from src.external_data.expansion_common import plan,frozen_sources
from src.external_data.hm_evaluate import metrics,rank
from src.external_data.hm_revisit import exact_lists,rerank_blend
from src.recommendation.datasets import TrainingDataset,read_data
from src.recommendation.features import FeatureEncoder, ItemTable
from src.recommendation.two_tower import TwoTower,weighted_loss
from src.recommendation.deepfm import DeepFM
from src.recommendation.eval_candidate import Evaluation
from src.recommendation.ranking_features import RankingEncoder,HistoryIndex,DENSE_FIELDS


class ContentTower(TwoTower):
    text_vectors: torch.Tensor
    image_vectors: torch.Tensor

    def __init__(self, encoder: FeatureEncoder, table: ItemTable, spec: dict, variant: str, embeddings: Path | None = None) -> None:
        super().__init__(encoder,table,spec);self.variant=variant
        if variant!='metadata':
            if embeddings is None:
                raise ValueError('content variants require an embeddings directory')
            self.register_buffer('text_vectors',torch.from_numpy(np.load(embeddings/'text_features.npy',mmap_mode='c')),persistent=False)
            self.text_projection=nn.Linear(self.text_vectors.shape[1],spec['dim'],bias=False)
            if variant=='multimodal':
                self.register_buffer('image_vectors',torch.from_numpy(np.load(embeddings/'image_features.npy',mmap_mode='c')),persistent=False)
                self.image_projection=nn.Linear(self.image_vectors.shape[1],spec['dim'],bias=False)

    def encode_items(self, indices: torch.Tensor) -> torch.Tensor:
        # Compute repeated history IDs once per call; preserve gradients and padding.
        unique,inverse=torch.unique(indices,return_inverse=True)
        values=super().encode_items(unique)
        if self.variant!='metadata':values=values+self.text_projection(self.text_vectors[unique])
        if self.variant=='multimodal':values=values+self.image_projection(self.image_vectors[unique])
        values=F.normalize(values,dim=-1)*unique.ne(0).unsqueeze(-1)
        return values[inverse]


def peak_rss_mib() -> float | None:
    # This metric was measured on Linux; other platforms remain unmeasured.
    if not sys.platform.startswith('linux'):return None
    import resource
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024


def context(spec: dict) -> tuple[dict, dict, FeatureEncoder, ItemTable]:
    cfg=json.loads((Path(spec['source_work'])/'hm_models/two_tower/external_config.json').read_text())['config']
    cfg['recommend']['candidate'].update(epochs=spec['candidate_epochs'],patience=spec['patience'],threads=spec['threads'],batch_size=spec['batch_size'])
    cfg['recommend']['ranking'].update(epochs=spec['ranking_epochs'],threads=spec['threads'])
    data=read_data(Path(spec['source_work'])/'hm','valid')
    encoder=FeatureEncoder.from_dict(json.loads((Path(spec['source_work'])/'hm_models/two_tower/feature_vocab_scalers.json').read_text()))
    table=encoder.item_table(data['products'])
    return cfg,data,encoder,table


def shards(spec: dict, results: Path, size: int) -> list[dict]:
    return [s for s in json.loads((results/'hm_data.json').read_text())['shards'] if s['number']<size//spec['shard_users']]


def training_users(frame: pd.DataFrame, ids: list[str]) -> pd.DataFrame:
    users=pd.DataFrame({'user_id':['HM-'+i for i in ids]})
    users['signup_at']=users.user_id.map(frame.groupby('user_id').timestamp.min()).fillna(pd.Timestamp('2100-01-01',tz='UTC'))
    users['age_group']='unknown';users['gender']='unknown';users['persona']='unobserved'
    return users


def prepare_tensors(spec: dict, work: Path, results: Path) -> None:
    cfg,data,encoder,table=context(spec);root=work/'hm_tensors';root.mkdir(exist_ok=True)
    ids=json.loads((work/'hm_data/users.json').read_text());hashes={};records=[];started=time.perf_counter()
    for s in shards(spec,results,max(spec['training_sizes'])):
        path=root/f"{s['number']:03d}.pt"
        frame=pd.read_parquet(s['path']);subids=ids[s['number']*spec['shard_users']:(s['number']+1)*spec['shard_users']]
        if not path.exists():
            local=copy.deepcopy(cfg);local['seed']=spec['seed']+s['number']*1000
            dataset=TrainingDataset(frame,training_users(frame,subids),encoder,table,local)
            tensors={k:getattr(dataset,k) for k in ['history','demographics','profile','items','weights']}
            tensors['timestamps']=torch.from_numpy(dataset.timestamps)
            user_map={uid:i for i,uid in enumerate(subids)}
            event_users=frame.set_index('event_id').user_id.str.removeprefix('HM-')
            tensors['users']=torch.tensor([user_map[u] for u in event_users.loc[dataset.event_ids]],dtype=torch.int64)
            torch.save(tensors,path);del dataset,tensors
        hashes[str(path)]=file_hash(path);records.append(dict(path=str(path),shard=s['number'],rows=len(frame)))
        print('H&M tensors',s['number']+1,'/',len(ids)//spec['shard_users'],flush=True)
    write_json(results/'hm_tensors.json',dict(status='PASS',hashes=hashes,records=records,seconds=time.perf_counter()-started,
        sampling='existing timestamp-safe TrainingDataset; 1:4 negatives, deterministic per-shard seed, reused across scales/variants'))


def tensor_records(spec: dict, results: Path, size: int) -> list[dict]:
    report=json.loads((results/'hm_tensors.json').read_text())
    records=[r for r in report['records'] if r['shard']<size//spec['shard_users']]
    for r in records:
        if file_hash(Path(r['path']))!=report['hashes'][r['path']]:raise ValueError('training tensor changed')
    return records


def content_projection(spec: dict, work: Path, results: Path) -> dict:
    from sklearn.decomposition import PCA
    cfg,data,encoder,table=context(spec);root=work/'hm_embeddings'
    source=json.loads((results/'hm_embeddings.json').read_text())
    source_hashes={**source['hashes'],str(root/'ids.json'):source['ids_sha256']}
    if not all(file_hash(Path(p))==h for p,h in source_hashes.items()):raise ValueError('changed original CLIP vectors')
    if json.loads((root/'ids.json').read_text())!=table.ids:raise ValueError('CLIP product row order differs from candidate catalog')
    path=results/'hm_content_projection.json'
    if path.exists():
        value=json.loads(path.read_text())
        if value['source_hashes']!=source_hashes:raise ValueError('content projection source changed')
        if not all(file_hash(Path(p))==h for p,h in value['hashes'].items()):raise ValueError('changed content projection')
        return value
    eligible=table.eligible(pd.Timestamp(encoder.fit_cutoff));reports={};hashes={}
    for mode in ['text','image']:
        values=np.load(root/f'{mode}.npy',mmap_mode='r');present=np.linalg.norm(values,axis=1)>0
        fit_rows=eligible[present[eligible]]
        projection=PCA(n_components=cfg['recommend']['candidate']['dim'],svd_solver='randomized',random_state=spec['seed'])
        projection.fit(values[fit_rows])
        transformed=projection.transform(values).astype(np.float32)
        transformed[~present]=0
        norms=np.linalg.norm(transformed,axis=1,keepdims=True)
        transformed/=np.maximum(norms,1e-12)
        feature_path=root/f'{mode}_features.npy';np.save(feature_path,transformed)
        model_path=root/f'{mode}_projection.npz';np.savez(model_path,mean=projection.mean_,components=projection.components_)
        hashes[str(feature_path)]=file_hash(feature_path);hashes[str(model_path)]=file_hash(model_path)
        reports[mode]=dict(fit_products=len(fit_rows),components=projection.n_components_,explained_variance=float(projection.explained_variance_ratio_.sum()))
    value=dict(status='PASS',fit_cutoff=encoder.fit_cutoff,modes=reports,hashes=hashes,source_hashes=source_hashes,
        scope='train-available catalog only, no outcome labels; frozen 512D CLIP projected to the configured 64D candidate space for CPU training; full original vectors retained')
    write_json(path,value);return value


def train_candidate(spec: dict, work: Path, results: Path, size: int, variant: str) -> None:
    tag=f'{size}-{variant}';root=work/'hm_models'/tag;root.mkdir(parents=True,exist_ok=True)
    report_path=results/f'hm_train_{tag}.json'
    if report_path.exists():
        r=json.loads(report_path.read_text())
        if r['model_sha256']!=file_hash(root/'candidate.pt'):raise ValueError('changed candidate checkpoint')
        return
    cfg,data,encoder,table=context(spec);evaluation=Evaluation(data,encoder,table,cfg)
    records=tensor_records(spec,results,size)
    set_seed(spec['seed']);torch.set_num_threads(spec['threads'])
    model=ContentTower(encoder,table,cfg['recommend']['candidate'],variant,work/'hm_embeddings')
    opt=torch.optim.AdamW(model.parameters(),lr=cfg['recommend']['candidate']['learning_rate'],weight_decay=cfg['recommend']['candidate']['weight_decay'])
    best=-1.;stale=0;epochs=[];started=time.perf_counter()
    for epoch in range(1,spec['candidate_epochs']+1):
        model.train();total=0.;n=0
        rng=np.random.default_rng(spec['seed']+epoch)
        for j in rng.permutation(len(records)):
            tensors=torch.load(records[j]['path'],weights_only=True)
            order=torch.randperm(len(tensors['items']),generator=torch.Generator().manual_seed(spec['seed']+epoch*1000+int(j)))
            for start in range(0,len(order),spec['batch_size']):
                ix=order[start:start+spec['batch_size']]
                batch={k:tensors[k][ix] for k in ['history','demographics','profile','items','weights']}
                opt.zero_grad(set_to_none=True);logits,_,_=model(batch);loss=weighted_loss(logits,batch['weights'])
                if not torch.isfinite(loss):raise ValueError('nonfinite candidate loss')
                loss.backward();grad=torch.nn.utils.clip_grad_norm_(model.parameters(),10.)
                if not torch.isfinite(grad):raise ValueError('nonfinite candidate gradient')
                opt.step();total+=float(loss.detach())*len(ix);n+=len(ix)
            del tensors
        rows=exact_lists(model,table,evaluation);score=evaluation.measure(rows)
        epochs.append(dict(epoch=epoch,loss=total/n,valid=score,elapsed_seconds=time.perf_counter()-started))
        print('H&M candidate',tag,'epoch',epoch,'valid',score['recall_at_300'],flush=True)
        if score['recall_at_300']>best:
            best=score['recall_at_300'];stale=0;torch.save(model.state_dict(),root/'candidate.pt')
            write_json(root/'valid_candidates.json',rows);best_epoch=epoch
        else:stale+=1
        if stale>=spec['patience']:break
    write_json(report_path,dict(status='PASS',acceptance='UNMEASURED',training_users=size,variant=variant,
        training_events=sum(r['rows'] for r in records),epochs=epochs,best_epoch=best_epoch,
        best_valid_recall=best,model_sha256=file_hash(root/'candidate.pt'),feature_fingerprint=encoder.digest,
        data_fingerprint=data['manifest']['generation_fingerprint'],elapsed_seconds=time.perf_counter()-started,
        process_peak_rss_mib=peak_rss_mib(),
        evaluation='original 2000 users, full eligible catalog, unchanged v1 truth; exact retrieval',
        training='nested train-only cohorts; shared per-shard samples; same hyperparameters and epochs budget'))


def item_times(spec: dict, results: Path, size: int) -> dict[str, np.ndarray]:
    frames=[pd.read_parquet(s['path'],columns=['product_id','timestamp']) for s in shards(spec,results,size)]
    frame=pd.concat(frames,ignore_index=True)
    return {str(pid):g.timestamp.astype('int64').sort_values().to_numpy() for pid,g in frame.groupby('product_id',sort=False)}


def ranking_features(spec: dict, work: Path, results: Path, size: int, encoder: FeatureEncoder, table: ItemTable) -> dict:
    root=work/'hm_ranking'/str(size);root.mkdir(parents=True,exist_ok=True)
    manifest=root/'features.json'
    if manifest.exists():
        value=json.loads(manifest.read_text())
        if not all(file_hash(Path(p))==h for p,h in value['hashes'].items()):raise ValueError('changed rank training features')
        return value
    times=item_times(spec,results,size); ids=json.loads((work/'hm_data/users.json').read_text())
    transform=RankingEncoder(encoder,np.zeros(len(DENSE_FIELDS),np.float32),np.ones(len(DENSE_FIELDS),np.float32),True)
    total=np.zeros(len(DENSE_FIELDS));square=total.copy();n=0;paths=[];hashes={}
    for s in shards(spec,results,size):
        frame=pd.read_parquet(s['path']);subids=ids[s['number']*spec['shard_users']:(s['number']+1)*spec['shard_users']]
        t=torch.load(work/'hm_tensors'/f"{s['number']:03d}.pt",weights_only=True)
        labels=pd.DataFrame(dict(user_id=np.repeat(np.array(['HM-'+i for i in subids])[t['users'].numpy()],5),
            product_id=np.array(table.ids)[t['items'].numpy().reshape(-1)],exposed_at=pd.to_datetime(np.repeat(t['timestamps'].numpy(),5),utc=True)))
        history=HistoryIndex(frame,table);history.item_times=times
        sparse,dense=transform.transform(labels,training_users(frame,subids),table,history)
        total+=dense.sum(axis=0,dtype=np.float64);square+=(dense.astype(np.float64)**2).sum(axis=0);n+=len(dense)
        path=root/f"{s['number']:03d}.pt";torch.save(dict(sparse=torch.from_numpy(sparse),dense=torch.from_numpy(dense),
            target=torch.from_numpy(np.tile(np.array([1,0,0,0,0],np.float32),len(t['items'])))),path)
        paths.append(str(path));hashes[str(path)]=file_hash(path)
        print('H&M ranking features',size,s['number']+1,flush=True)
    value=dict(paths=paths,hashes=hashes,mean=(total/n).tolist(),std=np.maximum(np.sqrt(np.maximum(0,square/n-(total/n)**2)),1e-6).tolist(),samples=n)
    write_json(manifest,value);return value


def evaluation_inputs(data: dict, evaluation: Evaluation, table: ItemTable, encoder: RankingEncoder, candidates: list[list[str]], times: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    history_events=data['train'] if evaluation.split=='valid' else pd.concat([data['train'],data['valid']],ignore_index=True)
    history=HistoryIndex(history_events,table);history.item_times=times
    labels=pd.DataFrame([(uid,pid,evaluation.cutoff) for uid,row in zip(evaluation.user_ids,candidates) for pid in row],columns=['user_id','product_id','exposed_at'])
    return encoder.transform(labels,data['users'],table,history,freeze_at=evaluation.cutoff)


def train_ranker(spec: dict, work: Path, results: Path, size: int) -> None:
    root=work/'hm_models'/f'{size}-metadata';report_path=results/f'hm_ranking_{size}.json'
    if report_path.exists():
        if json.loads(report_path.read_text())['model_sha256']!=file_hash(root/'ranker.pt'):raise ValueError('changed ranker')
        return
    cfg,data,metadata,table=context(spec);evaluation=Evaluation(data,metadata,table,cfg)
    features=ranking_features(spec,work,results,size,metadata,table)
    encoder=RankingEncoder(metadata,np.array(features['mean'],np.float32),np.array(features['std'],np.float32),True)
    candidates=json.loads((root/'valid_candidates.json').read_text());times=item_times(spec,results,size)
    inputs=evaluation_inputs(data,evaluation,table,encoder,candidates,times)
    set_seed(spec['seed']+100);model=DeepFM(encoder.cardinalities,len(DENSE_FIELDS),cfg['recommend']['ranking'])
    opt=torch.optim.AdamW(model.parameters(),lr=cfg['recommend']['ranking']['learning_rate'],weight_decay=cfg['recommend']['ranking']['weight_decay'])
    best=-1.;epochs=[];started=time.perf_counter()
    for epoch in range(1,spec['ranking_epochs']+1):
        model.train();total=0.;n=0
        for j in np.random.default_rng(spec['seed']+epoch).permutation(len(features['paths'])):
            tensors=torch.load(features['paths'][j],weights_only=True)
            order=torch.randperm(len(tensors['target']),generator=torch.Generator().manual_seed(spec['seed']+epoch*1000+int(j)))
            for start in range(0,len(order),spec['batch_size']):
                ix=order[start:start+spec['batch_size']];dense=(tensors['dense'][ix]-torch.from_numpy(encoder.mean))/torch.from_numpy(encoder.std)
                opt.zero_grad(set_to_none=True);logits=model(tensors['sparse'][ix],dense)[:,0]
                loss=F.binary_cross_entropy_with_logits(logits,tensors['target'][ix])
                if not torch.isfinite(loss):raise ValueError('nonfinite ranking loss')
                loss.backward();grad=torch.nn.utils.clip_grad_norm_(model.parameters(),10.)
                if not torch.isfinite(grad):raise ValueError('nonfinite ranking gradient')
                opt.step();total+=float(loss.detach())*len(ix);n+=len(ix)
        ranked,_=rank(model,inputs,candidates,spec['batch_size']);score=metrics(ranked,evaluation)
        epochs.append(dict(epoch=epoch,loss=total/n,valid=score));print('H&M ranker',size,epoch,score['ndcg_at_50'],flush=True)
        if score['ndcg_at_50']>best:best=score['ndcg_at_50'];best_epoch=epoch;torch.save(model.state_dict(),root/'ranker.pt')
    write_json(root/'ranking_features.json',encoder.to_dict())
    write_json(report_path,dict(status='PASS',acceptance='UNMEASURED',training_users=size,samples=features['samples'],epochs=epochs,
        best_epoch=best_epoch,model_sha256=file_hash(root/'ranker.pt'),seconds=time.perf_counter()-started,
        objective='purchase vs random unobserved, 1:4; not CTR/CVR',feature_sha256=file_hash(root/'ranking_features.json')))


def stage_metrics(spec: dict, work: Path, results: Path, size: int, variant: str, split: str) -> None:
    cfg,data,metadata,table=context(spec)
    if split=='test':data=read_data(Path(spec['source_work'])/'hm','test')
    evaluation=Evaluation(data,metadata,table,cfg,split);root=work/'hm_models'/f'{size}-{variant}'
    model=ContentTower(metadata,table,cfg['recommend']['candidate'],variant,work/'hm_embeddings')
    model.load_state_dict(torch.load(root/'candidate.pt',weights_only=True));model.eval()
    candidates=exact_lists(model,table,evaluation)
    rankroot=work/'hm_models'/f'{size}-metadata';encoder=RankingEncoder.from_dict(json.loads((rankroot/'ranking_features.json').read_text()))
    ranker=DeepFM(encoder.cardinalities,len(DENSE_FIELDS),cfg['recommend']['ranking'])
    ranker.load_state_dict(torch.load(rankroot/'ranker.pt',weights_only=True));ranker.eval()
    times=item_times(spec,results,size);inputs=evaluation_inputs(data,evaluation,table,encoder,candidates,times)
    learned,_=rank(ranker,inputs,candidates,spec['batch_size'])
    pop=np.array([len(times.get(pid,[])) for pid in table.ids],np.float32);pop/=max(1,pop.max())
    popular=[sorted(row,key=lambda p:(-pop[table.id_to_index[p]],p)) for row in candidates]
    final,diagnostics=rerank_blend(candidates,learned,1.,evaluation,cfg,data['products'],pop)
    report=dict(status='PASS',acceptance='UNMEASURED',size=size,variant=variant,split=split,
        candidate=evaluation.measure(candidates),stages={name:metrics(rows,evaluation) for name,rows in
            [('two_tower',candidates),('same_candidates_popularity',popular),('deepfm',learned),('reranked',final)]},
        reranking=diagnostics,evaluation_users=len(evaluation.user_ids),empty_target_users=evaluation.empty_users,
        data_fingerprint=data['manifest']['generation_fingerprint'],
        model_hashes={str(p):file_hash(p) for p in [root/'candidate.pt',rankroot/'ranker.pt',rankroot/'ranking_features.json']},
        ranking_scope='metadata purchase DeepFM shared across content variants at the same training size',
        test_scope='same previously inspected v1 interval; exploratory follow-up')
    write_json(results/f'hm_{split}_{size}_{variant}.json',report)


def fit_feature(spec: dict, work: Path, results: Path, size: int, variant: str) -> None:
    train_candidate(spec,work,results,size,variant)
    stage_metrics(spec,work,results,size,variant,'valid')


def main() -> None:
    parser=argparse.ArgumentParser();parser.add_argument('--task',choices=['tensors','scales','features','test'],required=True);args=parser.parse_args()
    spec,work,results=plan();torch.set_num_threads(spec['threads'])
    if args.task=='tensors':prepare_tensors(spec,work,results);return
    if args.task=='scales':
        for size in spec['training_sizes']:
            train_candidate(spec,work,results,size,'metadata');train_ranker(spec,work,results,size)
            stage_metrics(spec,work,results,size,'metadata','valid');gc.collect()
    elif args.task=='features':
        size=max(spec['training_sizes'],key=lambda n:json.loads((results/f'hm_train_{n}-metadata.json').read_text())['best_valid_recall'])
        if not (results/'hm_embeddings.json').exists():raise ValueError('full H&M embeddings not complete')
        projection=content_projection(spec,work,results)
        # Separate CPU workers share read-only input files, and write distinct bundles.
        # Spawn avoids inheriting the parent's initialized OpenMP thread pools.
        with ProcessPoolExecutor(max_workers=2,mp_context=multiprocessing.get_context('spawn')) as pool:
            futures=[pool.submit(fit_feature,spec,work,results,size,variant) for variant in ['text','multimodal']]
            for future in futures:future.result()
        reports=sorted(results.glob('hm_valid_*.json'))
        choice=max(reports,key=lambda p:json.loads(p.read_text())['stages']['reranked']['ndcg_at_50'])
        write_json(results/'hm_selection.json',dict(status='FROZEN',feature_training_size=size,selected_report=str(choice),
            spec_fingerprint=fingerprint(spec),source_hashes=frozen_sources(),
            report_hashes={str(p):file_hash(p) for p in reports},
            model_hashes={str(p):file_hash(p) for p in sorted((work/'hm_models').rglob('*.pt'))},
            embedding_hashes={**projection['source_hashes'],**projection['hashes']}))
    else:
        selection=json.loads((results/'hm_selection.json').read_text())
        for key in ['source_hashes','report_hashes','model_hashes','embedding_hashes']:
            if not all(file_hash(Path(p))==h for p,h in selection[key].items()):raise ValueError('changed after valid freeze')
        if selection['spec_fingerprint']!=fingerprint(spec):raise ValueError('changed plan')
        if list(results.glob('hm_test_*.json')):raise ValueError('test already started; preserve results')
        for size in spec['training_sizes']:stage_metrics(spec,work,results,size,'metadata','test')
        for variant in ['text','multimodal']:stage_metrics(spec,work,results,selection['feature_training_size'],variant,'test')

if __name__=='__main__':main()
