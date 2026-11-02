'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');
const source = fs.readFileSync(path.join(__dirname,'..','generate_m1_qwen_blind_html.py'),'utf8');
const functions = ['draftMatchesContext','assertReviewCompatibility'].map(name => {
  const match=source.match(new RegExp('^  function '+name+'\\(.*$','m'));
  assert.ok(match); return match[0];
}).join('\n');
const meta={manifest_sha256:'manifest',source_sha256:'source',guide_sha256:'guide',
  evidence_code_scheme:'annotation_guide_table_v1',evidence_code_dictionary_sha256:'dictionary'};
function context(payload){const c=vm.createContext({META:meta,ROLE:'B',REVIEW_SCHEMA_VERSION:'m1_blind_human_review_v3',payload});vm.runInContext(functions,c);return c;}
const good=()=>({schema_version:'m1_blind_human_review_v3',role:'B',...meta,annotation_method:'human',qwen_visible:false});
test('new exports with matching guide and dictionary pass compatibility',()=>{
  assert.equal(vm.runInContext('draftMatchesContext(payload)',context(good())),true);
  assert.doesNotThrow(()=>vm.runInContext('assertReviewCompatibility(payload)',context(good())));
});
test('old versions and mismatched code meanings cannot enter a new review',()=>{
  for(const [key,value] of [['schema_version','m1_blind_human_review_v2'],['role','A'],['guide_sha256','other'],
    ['evidence_code_dictionary_sha256','other'],['evidence_code_scheme','legacy_frozen_ui_v2']]){
    const p={...good(),[key]:value};
    assert.equal(vm.runInContext('draftMatchesContext(payload)',context(p)),false);
    assert.throws(()=>vm.runInContext('assertReviewCompatibility(payload)',context(p)));
  }
});
test('declared AI assistance is rejected even when the version hashes match',()=>{
  for(const change of [{annotation_method:'ai_assisted_human_review'},{qwen_visible:true},{ai_assistance_disclosed:true},{independent_blind_review:false}]){
    assert.throws(()=>vm.runInContext('assertReviewCompatibility(payload)',context({...good(),...change})),/不能导入/);
  }
});
