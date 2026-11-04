'use strict';
const assert = require('node:assert/strict');
const {test} = require('node:test');
const API = require('../assisted_review_core.js');
function fixture() {
  const blank=()=>({label:'',confidence:'',evidence_codes:[],evidence:'',uncertain_reason:'',reviewed:false,reviewed_at:'',media_review_confirmed:false,viewed_media_refs:[],remote_media_statuses:{},remote_open_attempts:{}});
  const original={synthetic_1:{...blank(),label:'非广',confidence:'0.8',evidence:'Original synthetic note',reviewed:true},synthetic_2:blank()};
  const records=API.copy(original);
  Object.assign(records.synthetic_2,{label:'非广',confidence:'0.7',evidence:'Synthetic AI note'});
  return {source_snapshot_sha256:'synthetic-source-hash',manifest_sha256:'synthetic-manifest',guide_sha256:'synthetic-guide',source_sha256:'synthetic-input',
    reviewer:{reviewer_id:'B',reviewer_name:'SYNTHETIC REVIEWER'},media_inspection:{synthetic_fixture:true},original_records:original,records,
    items:[{ordinal:1,post_id:'synthetic_1',ai_filled_fields:[],editable_fields:[],evidence_code_scheme:'synthetic',ai_suggestion:null,review_note:''},
           {ordinal:2,post_id:'synthetic_2',ai_filled_fields:['label','confidence','evidence'],editable_fields:['label','confidence','evidence','uncertain_reason','evidence_codes'],evidence_code_scheme:'synthetic',ai_suggestion:{label:'非广'},review_note:'Synthetic fixture'}]};
}
test('filled user fields and viewing flags are retained',()=>{
  const seed=fixture(),state=API.createState(seed);
  assert.deepEqual(state.records.synthetic_1,seed.original_records.synthetic_1);
  assert.equal(state.records.synthetic_2.reviewed,false);
  assert.equal(state.records.synthetic_2.media_review_confirmed,false);
  assert.deepEqual(API.validateState(seed,state),[]);
});
test('existing fields are locked and tampering blocks export',()=>{
  const seed=fixture(),state=API.createState(seed);
  assert.throws(()=>API.setField(seed,state,'synthetic_1','label','明广'),/锁定/);
  state.records.synthetic_1.label='明广';
  assert.throws(()=>API.exportReview(seed,state,false),/原填写被改动/);
});
test('unconfirmed AI suggestions cannot be exported as completed review',()=>{
  const seed=fixture(),state=API.createState(seed),out=API.exportReview(seed,state,false);
  assert.equal(out.annotation_method,'ai_assisted_human_review');
  assert.equal(out.independent_blind_review,false);
  assert.equal(out.formal_evidence,false);
  assert.equal(out.eligible_for_formal_kappa,false);
  assert.equal(out.eligible_for_formal_gold,false);
  assert.throws(()=>API.exportReview(seed,state,true),/未核对/);
});
test('editing after confirmation requires confirmation again',()=>{
  const seed=fixture(),state=API.createState(seed);
  API.setReviewer(state,{reviewer_name:'Synthetic successor',reviewer_id:'B2'});
  API.setConfirmation(seed,state,'synthetic_2',true);
  API.setField(seed,state,'synthetic_2','evidence','Revised synthetic note');
  assert.equal(state.confirmations.synthetic_2,undefined);
});
test('incomplete edits can be saved and exported as draft',()=>{
  const seed=fixture(),state=API.createState(seed);
  API.setField(seed,state,'synthetic_2','evidence','');
  const restored=JSON.parse(JSON.stringify(state));
  assert.deepEqual(API.validatePreserved(seed,restored),[]);
  assert.equal(API.exportReview(seed,restored,false).items[1].record.evidence,'');
  assert.throws(()=>API.setConfirmation(seed,restored,'synthetic_2',true),/证据说明/);
});
test('uncertain requires a reason that can be added to the original blank field',()=>{
  const seed=fixture(),state=API.createState(seed);
  API.setField(seed,state,'synthetic_2','label','uncertain');
  assert.match(API.validateItem(seed,state,'synthetic_2').join(' '),/uncertain/);
  API.setField(seed,state,'synthetic_2','uncertain_reason','Synthetic evidence gap');
  assert.deepEqual(API.validateItem(seed,state,'synthetic_2'),[]);
});
test('confirmed assisted review remains non-formal and does not imply media viewing',()=>{
  const seed=fixture(),state=API.createState(seed);
  API.setReviewer(state,{reviewer_name:'Synthetic successor',reviewer_id:'B2'});
  API.setConfirmation(seed,state,'synthetic_2',true);
  const out=API.exportReview(seed,state,true);
  assert.equal(out.status,'user_confirmed_ai_additions');
  assert.equal(out.formal_evidence,false);
  assert.equal(out.items[1].record.media_review_confirmed,false);
  assert.equal(out.human_media_review_not_inferred_from_ai_confirmation,true);
  assert.equal(out.reviewer.reviewer_id,'B2');
  assert.equal(out.source_draft_reviewer.reviewer_id,'B');
});
test('successor identity is required and changing it invalidates prior confirmations',()=>{
  const seed=fixture(),state=API.createState(seed);
  assert.throws(()=>API.setConfirmation(seed,state,'synthetic_2',true),/当前复核人/);
  API.setReviewer(state,{reviewer_name:'Synthetic successor',reviewer_id:'B2'});
  API.setConfirmation(seed,state,'synthetic_2',true);
  assert.equal(state.confirmations.synthetic_2.confirmed_by.reviewer_id,'B2');
  API.setReviewer(state,{reviewer_name:'Another synthetic reviewer',reviewer_id:'B3'});
  assert.deepEqual(state.confirmations,{});
  assert.throws(()=>API.exportReview(seed,state,true),/未核对/);
  assert.deepEqual(state.records.synthetic_1,seed.original_records.synthetic_1);
});
