(function (root) {
  'use strict';
  const copy = value => JSON.parse(JSON.stringify(value));
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const labels = ['明广', '暗广', '非广', 'uncertain', 'out_of_scope'];
  const itemFor = (seed, id) => seed.items.find(item => item.post_id === id);
  function createState(seed) {
    return {source_snapshot_sha256: seed.source_snapshot_sha256, records: copy(seed.records), confirmations: {}, edit_log: []};
  }
  function setField(seed, state, id, field, value) {
    const item = itemFor(seed, id);
    if (!item || !item.editable_fields.includes(field)) throw new Error('此字段是原草稿已有内容，已锁定保留。');
    state.records[id][field] = copy(value);
    delete state.confirmations[id];
    state.edit_log.push({post_id: id, field, edited_at: new Date().toISOString()});
  }
  function validateItem(seed, state, id) {
    const item = itemFor(seed, id), record = state.records[id], errors = [];
    if (!item || !record) return ['缺少样本'];
    for (const [field, value] of Object.entries(seed.original_records[id])) {
      if (!item.editable_fields.includes(field) && !same(record[field], value)) errors.push('原填写被改动：' + field);
    }
    if (!labels.includes(record.label)) errors.push('请选择有效标签');
    if (record.confidence === '' || !Number.isFinite(Number(record.confidence)) || Number(record.confidence) < 0 || Number(record.confidence) > 1) errors.push('置信度须为 0 至 1');
    if (typeof record.evidence !== 'string' || !record.evidence.trim()) errors.push('证据说明不能为空');
    if (record.label === 'uncertain' && (typeof record.uncertain_reason !== 'string' || !record.uncertain_reason.trim())) errors.push('uncertain 需要原因');
    return errors;
  }
  function setConfirmation(seed, state, id, checked) {
    const item = itemFor(seed, id);
    if (!item || !item.ai_filled_fields.length) throw new Error('此条没有 AI 新增字段');
    if (checked) {
      const errors = validateItem(seed, state, id);
      if (errors.length) throw new Error(errors.join('；'));
      state.confirmations[id] = {confirmed: true, confirmed_at: new Date().toISOString(), scope: 'AI 新增或补齐字段；不代表观看了未查看的媒体'};
    } else delete state.confirmations[id];
  }
  function validatePreserved(seed, state) {
    const errors = [];
    if (!state || state.source_snapshot_sha256 !== seed.source_snapshot_sha256) return ['草稿来源不匹配'];
    if (!state.records || Object.keys(state.records).length !== seed.items.length) return ['样本数量不匹配'];
    if (!state.confirmations || !Array.isArray(state.edit_log)) return ['复核状态结构不完整'];
    for (const item of seed.items) {
      const record = state.records[item.post_id];
      if (!record || typeof record !== 'object') {errors.push('缺少样本 #' + item.ordinal);continue;}
      for (const [field, value] of Object.entries(seed.original_records[item.post_id])) {
        if (!item.editable_fields.includes(field) && !same(record[field], value)) errors.push('#' + item.ordinal + ' 原填写被改动：' + field);
      }
      for (const field of ['label','confidence','evidence','uncertain_reason']) if (typeof record[field] !== 'string') errors.push('#' + item.ordinal + ' 字段类型错误：' + field);
      if (!Array.isArray(record.evidence_codes)) errors.push('#' + item.ordinal + ' 证据代码格式错误');
    }
    return errors;
  }
  function validateState(seed, state) {
    const errors = validatePreserved(seed, state);
    if (errors.length) return errors;
    for (const item of seed.items) errors.push(...validateItem(seed, state, item.post_id).map(e => '#' + item.ordinal + ' ' + e));
    return errors;
  }
  function exportReview(seed, state, finalReview) {
    const errors = finalReview ? validateState(seed, state) : validatePreserved(seed, state);
    if (errors.length) throw new Error(errors.join('\n'));
    const pending = seed.items.filter(item => item.ai_filled_fields.length && !state.confirmations[item.post_id]?.confirmed);
    if (finalReview && pending.length) throw new Error('还有 ' + pending.length + ' 条新增内容未核对，请逐条确认，或使用“导出复核草稿”。');
    return {
      schema_version: finalReview ? 'm1_ai_assisted_human_review_v1' : 'm1_ai_assisted_review_draft_v1',
      status: finalReview ? 'user_confirmed_ai_additions' : 'awaiting_user_review',
      annotation_method: 'ai_assisted_human_review',
      ai_assistance_disclosed: true, independent_blind_review: false,
      formal_evidence: false, eligible_for_formal_kappa: false, eligible_for_formal_gold: false,
      source_snapshot_sha256: seed.source_snapshot_sha256,
      manifest_sha256: seed.manifest_sha256, guide_sha256: seed.guide_sha256,
      source_sha256: seed.source_sha256, role: 'B', reviewer: copy(seed.reviewer),
      exported_at: new Date().toISOString(), sample_count: seed.items.length,
      original_user_record_flags_retained: true,
      human_media_review_not_inferred_from_ai_confirmation: true,
      items: seed.items.map(item => ({ordinal: item.ordinal, post_id: item.post_id,
        record: copy(state.records[item.post_id]), ai_filled_fields: [...item.ai_filled_fields],
        evidence_code_scheme: item.evidence_code_scheme, ai_suggestion: copy(item.ai_suggestion),
        review_note: item.review_note,
        human_confirmation: copy(state.confirmations[item.post_id] || {confirmed: false, required: Boolean(item.ai_filled_fields.length)})})),
      edit_log: copy(state.edit_log), media_inspection: copy(seed.media_inspection)
    };
  }
  const api = {copy, createState, setField, setConfirmation, validateItem, validatePreserved, validateState, exportReview};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.AssistedReview = api;
})(typeof globalThis === 'undefined' ? this : globalThis);
