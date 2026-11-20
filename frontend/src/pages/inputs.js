import {feedback, field} from '../components/common/fields.js';
import {empty, panel} from '../components/common/panels.js';
import {table} from '../components/common/table.js';
import {handler} from '../hooks/action.js';
import {session} from '../stores/session.js';
import {workspace} from '../stores/workspace.js';
import {button, el, link, p} from '../utils/dom.js';
import {date, value} from '../utils/format.js';

function calibrationPanel(state, refresh) {
  const error = feedback();
  const sample = button('下载校准单模板', {class:'quiet',onClick:event=>
    handler(sample,error,()=>workspace.download('/calibration/template',workspace.spec.calibration_sample_name))(event)});
  const submit = button('校验并切换校准版', {type:'submit',class:'primary'});
  const upload = session.canWrite && el('form',{class:'fields',onSubmit:handler(submit,error,async event=>{
    const data = new FormData(event.target);
    const file = data.get('calibration_source');
    if (!file?.size) throw new Error('请选择一个校准单 CSV 文件');
    if (file.size > 2_000_000) throw new Error('校准单最多 2 MB');
    await workspace.uploadCalibration({name:data.get('calibration_name'),filename:file.name,csv_text:await file.text()});
    await refresh();
  })},field({key:'calibration_name',label:'校准批次名称',type:'string',max_length:120}),
    el('label',{class:'field',for:'calibration_source'}, el('span',{},'校准单 CSV'),
      el('input',{id:'calibration_source',type:'file',name:'calibration_source',accept:'.csv,text/csv',required:true})), submit);
  const entries = table([
    {key:'probe',label:'探针'},
    {key:'handoff_date',label:'交接日期'},
    {key:'revision',label:'修订号'},
    {label:'校准偏差（°C）',render:row=>`${row.offset > 0 ? '+' : ''}${value(row.offset)}`},
    {key:'calibration_id',label:'校准单号'},
  ], state?.entries || [], {caption:'当前生效校准', pageSize:8, empty:'还没有生效的校准单。导入后按探针与交接日期套用。'});
  const batches = table([
    {key:'name',label:'批次'},
    {key:'version',label:'版本'},
    {label:'应用 / 忽略',render:row=>`${row.applied_count} / ${row.ignored_count}`},
    {key:'author',label:'导入人'},
    {label:'时间',render:row=>date(row.created_at)},
  ], state?.batches || [], {caption:'校准导入历史', pageSize:6, empty:'还没有校准导入记录。'});
  return panel('探针校准',
    p(`当前校准版本 v${state?.version ?? 0}。整批校验通过后一次性切换，失败沿用旧版；同修订冲突整批退回，晚到的旧修订不会覆盖新修订。`,'subtle'),
    sample, upload, error,
    el('h3',{}, '当前生效校准'), entries,
    el('h3',{}, '导入历史'), batches);
}

export async function inputs(route, refresh) {
  const {spec,datasets} = workspace;
  const selected = datasets.find(item => item.id === route.id) || datasets[0];
  const error = feedback();
  const sample = button('下载示例 CSV', {class:'quiet',onClick:event=>handler(sample,error,()=>workspace.download('/template',spec.sample_name))(event)});
  const detail = selected && await workspace.getDataset(selected.id,route.offset);
  const calibration = await workspace.calibration();
  const columns = spec.fields.map(field => ({key:field.key,label:field.label}));
  const preview = detail ? panel('批次明细', el('div',{class:'actions'},
    el('label',{for:'dataset-id',class:'sr'}, '选择数据批次'),
    el('select',{id:'dataset-id','aria-label':'选择数据批次',onChange:event=>{location.hash=`#inputs/${event.target.value}`;}},
      datasets.map(item=>el('option',{value:item.id,selected:item.id === selected.id}, item.name))),
    link('使用此批次运行',`#run/${detail.id}`,{class:'quiet'})),
    p(`${detail.filename} · ${detail.row_count} 行 · ${date(detail.created_at)}`,'filename'),
    table(columns,detail.rows,{caption:'批次明细',pageSize:16}),
    el('div',{class:'pagination'},
      route.offset > 0 && link('上一批明细',`#inputs/${detail.id}/${Math.max(0,route.offset-16)}`,{class:'quiet'}),
      p(`${detail.rows.length ? route.offset+1 : route.offset}–${route.offset+detail.rows.length} / ${detail.row_count}`),
      route.offset+16 < detail.row_count && link('下一批明细',`#inputs/${detail.id}/${route.offset+16}`,{class:'quiet'})))
    : empty('没有可用的批次。请导入示例或业务 CSV。');
  const submit = button('校验并导入', {type:'submit',class:'primary'});
  const upload = session.canWrite && el('form',{class:'fields',onSubmit:handler(submit,error,async event=>{
    const data = new FormData(event.target);
    const file = data.get('source');
    if (!file?.size) throw new Error('请选择一个 CSV 文件');
    if (file.size > 2_000_000) throw new Error('CSV 最多 2 MB');
    const item = await workspace.upload({name:data.get('batch_name'),filename:file.name,csv_text:await file.text()});
    const target = `#inputs/${item.id}`;
    if (location.hash === target) await refresh();
    else location.hash = target;
  })},field({key:'batch_name',label:'批次名称',type:'string',max_length:120}),
    el('label',{class:'field',for:'source'}, el('span',{},'业务 CSV'),el('input',{id:'source',type:'file',name:'source',accept:'.csv,text/csv',required:true})), submit);
  return el('div',{class:'two-col'},el('div',{class:'wide-panel'},preview, calibrationPanel(calibration, refresh)),el('aside',{class:'sidebar-panel'},
    panel('数据导入',p('导入后保留原批次和校验指纹，可用同一份数据复跑。','subtle'),sample,upload,error),
    panel('字段说明',el('dl',{class:'dictionary'},spec.fields.map(item=>el('div',{},el('dt',{},item.label),
      el('dd',{},item.key,item.required === false ? ' · 可空' : ' · 必填',item.options ? ` · ${item.options.join(' / ')}` : ''))))),
    panel('校准字段说明',el('dl',{class:'dictionary'},spec.calibration_fields.map(item=>el('div',{},el('dt',{},item.label),
      el('dd',{},item.key,item.help ? ` · ${item.help}` : '')))))));
}
