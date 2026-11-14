import numpy as np
import pandas as pd
import torch
from tests.test_two_tower import fixture
from src.external_data.expansion_data import nested_users
from src.external_data.expansion_hm import ContentTower
from src.external_data.expansion_retail import observed_pairs,categories_asof,fit,predict,score
from src.recommendation.two_tower import TwoTower
from src.external_data.retailrocket import transition_counts


def test_optional_linux_memory_metric_does_not_block_other_platforms(monkeypatch):
    from src.external_data import expansion_hm
    monkeypatch.setattr(expansion_hm.sys,'platform','win32')
    assert expansion_hm.peak_rss_mib() is None


def test_nested_cohorts_keep_original_and_ignore_outcomes():
    ids=nested_users(['b','a'],list('abcdefghij'),[2,5,9],42)
    assert ids[:2]==['a','b'] and len(ids)==len(set(ids))==9
    assert ids==nested_users(['a','b'],list(reversed('abcdefghij')),[2,5,9],42)


def test_deduplicated_tower_preserves_padding_values_and_gradients(fixture):
    cfg,_,encoder,table,_=fixture
    original=TwoTower(encoder,table,cfg['recommend']['candidate'])
    optimized=ContentTower(encoder,table,cfg['recommend']['candidate'],'metadata')
    optimized.load_state_dict(original.state_dict())
    ids=torch.tensor([[0,1,2,1],[3,0,3,1]])
    a=original.encode_items(ids);b=optimized.encode_items(ids)
    assert torch.allclose(a,b,atol=1e-6) and b[0,0].abs().sum()==0
    a[...,0].sum().backward();b[...,0].sum().backward()
    assert all(torch.allclose(x.grad,y.grad,atol=1e-5) for x,y in zip(original.item_mlp.parameters(),optimized.item_mlp.parameters()))


def test_content_uses_distinct_features_and_retains_missing_images(fixture,tmp_path):
    cfg,_,encoder,table,_=fixture
    vectors=np.random.default_rng(3).normal(size=(len(table.ids),8)).astype(np.float32);vectors[0]=0
    np.save(tmp_path/'text_features.npy',vectors);images=vectors.copy();images[2]=0;np.save(tmp_path/'image_features.npy',images)
    model=ContentTower(encoder,table,cfg['recommend']['candidate'],'multimodal',tmp_path)
    values=model.encode_items(torch.tensor([0,1,2]))
    assert torch.isfinite(values).all() and values[0].abs().sum()==0
    assert torch.allclose(values[1:].norm(dim=1),torch.ones(2))
    values[1:,0].sum().backward()
    assert model.text_projection.weight.grad.abs().sum()>0 and model.image_projection.weight.grad.abs().sum()>0


def test_category_join_never_uses_same_timestamp_or_future_values():
    events=pd.DataFrame(dict(row_id=[0,1,2],itemid=[1,1,1],timestamp=pd.to_datetime(['2020-01-01','2020-01-02','2020-01-04'],utc=True)))
    props=pd.DataFrame(dict(itemid=[1,1],timestamp=pd.to_datetime(['2020-01-02','2020-01-03'],utc=True),value=['old','new']))
    assert categories_asof(events,props).sort_index().tolist()==['unknown','unknown','new']


def test_conditional_pairs_keep_global_tie_and_censor_contract():
    origin=pd.Timestamp('2020-01-01',tz='UTC')
    frame=pd.DataFrame(dict(visitorid=[1,1,1,1,2],event=['view','cart','purchase','view','view'],seconds=[0,5,5,60,999]))
    frame['timestamp']=origin+pd.to_timedelta(frame.seconds,unit='s');frame['row_id']=np.arange(len(frame))
    pairs=observed_pairs(frame,origin+pd.Timedelta(seconds=1000),100)
    counts,_=transition_counts(frame,origin+pd.Timedelta(seconds=1000),100)
    actual=pairs.groupby(['event','next']).size()
    assert all(actual.get((s,d),0)==n for s,row in counts.items() for d,n in row.items())


def test_unseen_markov_group_falls_back_without_deleting_observations():
    train=pd.DataFrame(dict(category=['one'],activity=[0],event=['view'],next=['cart']))
    valid=pd.DataFrame(dict(category=['unseen'],activity=[2],event=['view'],next=['exit']))
    prior=np.full((3,4),.25)
    p=predict(valid,'category',fit(train,'category'),prior,100)
    assert np.allclose(p,[prior[0]]) and score(valid,p)['observations']==1


def test_simulator_conditions_change_only_the_designated_parameters():
    import copy
    from src.common.config import load_config
    from src.external_data.expansion_simulator import conditions
    base=load_config();before=copy.deepcopy(base);names=list(base['simulator']['taxonomy'])
    hm={'category_purchase_shares':{k:1/len(names) for k in names},'relative_category_price':{k:1.2 for k in names}}
    retail={'fitted_transitions':{s:dict(view=.2,cart=.3,purchase=.1,exit=.4) for s in ['view','cart','purchase']}}
    rows=conditions(base,hm,retail)
    assert base==before and rows['original']==before
    assert rows['hm']['simulator']['transitions']==before['simulator']['transitions']
    assert rows['retailrocket']['simulator']['personas']==before['simulator']['personas']
    assert rows['both']['simulator']['personas']==rows['hm']['simulator']['personas']
    assert rows['both']['simulator']['transitions']==rows['retailrocket']['simulator']['transitions']


def test_deepfashion_nested_sample_keeps_all_previous_queries():
    from src.external_data.expansion_deepfashion import nested_selection
    parts=[(f'{s}{i}',s) for s in ['train','val','test'] for i in range(10)]
    old={s:[f'{s}2',f'{s}0'] for s in ['train','val','test']}
    result=nested_selection(parts,old,{s:5 for s in old},42)
    for s,rows in result.items():
        assert rows[:2]==old[s] and len(set(rows))==5 and all(r.startswith(s) for r in rows)


def test_image_retrieval_excludes_duplicates_and_retains_no_truth_query():
    from src.external_data.expansion_deepfashion import retrieval
    # The only relevant gallery item is an exact duplicate, so this query remains zero.
    assert retrieval(np.array([1.,.8,.7]),np.array([1,2,2]),1,np.array([True,False,False]))==(0.,0.,0)
    mrr,ndcg,count=retrieval(np.array([.9,1.,.8]),np.array([1,2,1]),1,np.zeros(3,dtype=bool))
    assert mrr==.5 and 0<ndcg<1 and count==2


def test_content_projection_fits_only_train_available_nonmissing_products(fixture,tmp_path,monkeypatch):
    import json
    from src.common.artifacts import file_hash,write_json
    from src.external_data import expansion_hm
    cfg,data,encoder,table,_=fixture
    monkeypatch.setattr(expansion_hm,'context',lambda spec:(cfg,data,encoder,table))
    root=tmp_path/'hm_embeddings';root.mkdir();results=tmp_path/'results';results.mkdir()
    raw=np.random.default_rng(4).normal(size=(len(table.ids),80)).astype(np.float32);raw[0]=0;raw[-1]=1e6
    np.save(root/'text.npy',raw);images=raw.copy();images[2]=0;np.save(root/'image.npy',images)
    write_json(root/'ids.json',table.ids)
    write_json(results/'hm_embeddings.json',{'hashes':{str(root/f'{k}.npy'):file_hash(root/f'{k}.npy') for k in ['text','image']},'ids_sha256':file_hash(root/'ids.json')})
    value=expansion_hm.content_projection({'seed':42},tmp_path,results)
    assert value['modes']['text']['fit_products']==400 and value['modes']['image']['fit_products']==399
    assert np.allclose(np.load(root/'text_projection.npz')['mean'],raw[1:-1].mean(axis=0),atol=1e-5)
    assert not np.load(root/'image_features.npy')[2].any()
    assert np.isfinite(np.load(root/'text_features.npy')).all()
    assert expansion_hm.content_projection({'seed':42},tmp_path,results)==value
    import pytest
    changed=list(table.ids);changed[1],changed[2]=changed[2],changed[1]
    write_json(root/'ids.json',changed)
    source=json.loads((results/'hm_embeddings.json').read_text());source['ids_sha256']=file_hash(root/'ids.json')
    write_json(results/'hm_embeddings.json',source)
    with pytest.raises(ValueError,match='row order'):
        expansion_hm.content_projection({'seed':42},tmp_path,results)
    write_json(root/'ids.json',table.ids);source['ids_sha256']=file_hash(root/'ids.json')
    images[3]*=2;np.save(root/'image.npy',images)
    source['hashes'][str(root/'image.npy')]=file_hash(root/'image.npy');write_json(results/'hm_embeddings.json',source)
    with pytest.raises(ValueError,match='projection source changed'):
        expansion_hm.content_projection({'seed':42},tmp_path,results)
