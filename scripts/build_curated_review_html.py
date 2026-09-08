"""Build a browser-based, one-card-at-a-time curated benchmark reviewer."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path("benchmarks/curated")
    parser.add_argument("--input-dir", type=Path, default=root)
    parser.add_argument("--output", type=Path, default=root / "review.html")
    return parser.parse_args()


def read_tsv(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return {"headers": reader.fieldnames or [], "rows": list(reader)}


def main() -> None:
    args = parse_args()
    payload = {
        "ambiguities": read_tsv(args.input_dir / "ambiguous_rac_review.tsv"),
        "unresolved": read_tsv(args.input_dir / "unresolved_spans.tsv"),
        "sentences": read_tsv(args.input_dir / "automatic_rac_segments.tsv"),
        "metadata": json.loads(
            (args.input_dir / "ambiguity_review.meta.json").read_text(encoding="utf-8")
        ),
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace(
        "</", "<\/"
    )
    document = TEMPLATE.replace("__REVIEW_DATA__", encoded)
    args.output.write_text(document, encoding="utf-8", newline="\n")
    print(f"Wrote review interface to {args.output}")


TEMPLATE = r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Khmer Segmenter contextual review</title>
  <style>
    :root{color-scheme:dark;--bg:#101513;--panel:#18201d;--panel2:#202a26;--line:#35433d;--text:#f1f3ed;--muted:#aab7b0;--accent:#5da98a;--accent2:#83c5a8;--warn:#d9ad66;--danger:#dc8178}
    *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:Inter,Segoe UI,Arial,sans-serif;line-height:1.5}
    button,input,textarea,select{font:inherit}.shell{max-width:1080px;margin:auto;padding:24px}.top{display:flex;gap:18px;align-items:flex-start;justify-content:space-between;flex-wrap:wrap}
    h1{font-size:1.65rem;margin:0 0 6px}p{margin:0}.muted{color:var(--muted)}.tabs,.toolbar,.nav,.choices{display:flex;gap:8px;flex-wrap:wrap}
    .tabs{margin:22px 0 14px}.btn{border:1px solid var(--line);background:var(--panel);color:var(--text);border-radius:8px;padding:9px 13px;cursor:pointer}
    .btn:hover{border-color:var(--accent2)}.btn.active,.btn.selected{background:var(--accent);border-color:var(--accent2);color:#08100d}.btn.danger{border-color:var(--danger)}
    .toolbar{align-items:center;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px;margin-bottom:14px}.toolbar input,.toolbar select{background:var(--bg);border:1px solid var(--line);color:var(--text);border-radius:7px;padding:8px}
    .search{min-width:220px;flex:1}.progress{font-variant-numeric:tabular-nums;color:var(--muted);white-space:nowrap}.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:22px;box-shadow:0 10px 30px #0003}
    .card-head{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:18px}.badges{display:flex;gap:7px;flex-wrap:wrap}.badge{background:var(--panel2);border:1px solid var(--line);border-radius:999px;padding:3px 9px;color:var(--muted);font-size:.85rem}
    .badge.high{color:#ffd0ca;border-color:var(--danger)}.badge.medium{color:#ffe0a7;border-color:var(--warn)}.kh{font-family:"Noto Sans Khmer","Khmer OS Battambang",sans-serif;line-height:2;overflow-wrap:anywhere}
    .sentence{font-size:1.5rem;background:var(--bg);border:1px solid var(--line);border-radius:9px;padding:18px;margin:10px 0 20px}.sentence mark{background:#67572e;color:#fff2c8;border-radius:4px;padding:2px 3px}
    .label{display:block;color:var(--muted);font-size:.88rem;margin:14px 0 5px}.choice{display:flex;align-items:center;gap:12px;min-height:58px;text-align:left;flex:1 1 290px;font-size:1.25rem}.choice small{font-family:Inter,Segoe UI,sans-serif;color:inherit;opacity:.75;min-width:82px}
    textarea,.wide-input{width:100%;background:var(--bg);border:1px solid var(--line);border-radius:8px;color:var(--text);padding:10px}.wide-input.kh{font-size:1.25rem}.nav{justify-content:space-between;margin-top:14px}.nav-group{display:flex;gap:8px}
    details{margin-top:18px;color:var(--muted)}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:var(--bg);padding:10px;border-radius:7px}.empty{text-align:center;padding:50px;color:var(--muted)}
    .help{max-width:650px}.export{display:flex;gap:7px;flex-wrap:wrap}.flash{position:fixed;right:18px;bottom:18px;background:var(--accent);color:#08100d;padding:10px 14px;border-radius:8px;display:none}
    @media(max-width:650px){.shell{padding:14px}.card{padding:15px}.sentence{font-size:1.25rem}.choice{flex-basis:100%}}
  </style>
</head>
<body>
<main class="shell">
  <div class="top">
    <div class="help"><h1>Khmer contextual segmentation review</h1><p class="muted">Review one decision at a time. Progress is saved in this browser. Export the TSV files before moving to another browser or computer.</p></div>
    <div class="export">
      <button class="btn" id="importButton">Import reviewed TSV</button>
      <input id="importFiles" type="file" accept=".tsv,text/tab-separated-values" multiple hidden>
      <button class="btn" data-export="ambiguities">Export ambiguities</button>
      <button class="btn" data-export="unresolved">Export unresolved</button>
      <button class="btn" data-export="sentences">Export sentences</button>
    </div>
  </div>
  <div class="tabs">
    <button class="btn active" data-tab="ambiguities">Ambiguities</button>
    <button class="btn" data-tab="unresolved">Unresolved</button>
    <button class="btn" data-tab="sentences">Sentence quality</button>
  </div>
  <div class="toolbar">
    <select id="statusFilter"><option value="pending">Pending only</option><option value="all">All records</option><option value="approved">Approved only</option></select>
    <select id="priorityFilter"><option value="all">All priorities</option><option value="high">High</option><option value="medium">Medium</option><option value="contextual">Contextual</option></select>
    <input id="search" class="search" placeholder="Search sentence, span, or ID">
    <span id="progress" class="progress"></span>
  </div>
  <section id="content"></section>
  <div id="flash" class="flash">Saved</div>
</main>
<script>
const DATA=__REVIEW_DATA__;
const STORAGE_KEY=`khmer-curated-review:${DATA.metadata.model_manifest_sha256}`;
const FILENAMES={ambiguities:'ambiguous_rac_review.reviewed.tsv',unresolved:'unresolved_spans.reviewed.tsv',sentences:'automatic_rac_segments.reviewed.tsv'};
let tab='ambiguities',index=0;
let saved={};try{saved=JSON.parse(localStorage.getItem(STORAGE_KEY)||'{}')}catch(_){saved={}}
function key(kind,row){return `${kind}:${row.case_id||row.sentence_id}`}
function rows(kind){return DATA[kind].rows.map(row=>Object.assign({},row,saved[key(kind,row)]||{}))}
function persist(kind,row,changes){const k=key(kind,row);saved[k]=Object.assign({},saved[k]||{},changes);localStorage.setItem(STORAGE_KEY,JSON.stringify(saved));flash('Saved')}
function flash(message){const el=document.getElementById('flash');el.textContent=message;el.style.display='block';clearTimeout(flash.timer);flash.timer=setTimeout(()=>el.style.display='none',900)}
function esc(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function highlighted(text,start,end){const chars=Array.from(text);return `${esc(chars.slice(0,start).join(''))}<mark>${esc(chars.slice(start,end).join(''))}</mark>${esc(chars.slice(end).join(''))}`}
function approved(kind,row){return kind==='sentences'?row.sentence_review_status==='approved':row.review_status==='approved'}
function filtered(){const status=document.getElementById('statusFilter').value,priority=document.getElementById('priorityFilter').value,q=document.getElementById('search').value.trim().toLowerCase();return rows(tab).filter(row=>{if(status==='pending'&&approved(tab,row))return false;if(status==='approved'&&!approved(tab,row))return false;if(tab==='ambiguities'&&priority!=='all'&&row.priority!==priority)return false;const hay=Object.values(row).join(' ').toLowerCase();return !q||hay.includes(q)})}
function progressText(all){const done=all.filter(row=>approved(tab,row)).length;return `${done}/${all.length} approved`}
function setChoice(row,choice){persist('ambiguities',row,{reviewer_choice:choice,review_status:choice==='uncertain'?'draft':'approved'});afterDecision()}
function setClassification(row,value){persist('unresolved',row,{reviewer_classification:value,review_status:'approved'});afterDecision()}
function setSentence(row,value){persist('sentences',row,{sentence_review_status:value});afterDecision()}
function afterDecision(){if(document.getElementById('statusFilter').value==='pending')index=Math.max(0,index);else index+=1;setTimeout(render,80)}
function choiceButton(label,value,row,kind){const selected=(kind==='ambiguities'?row.reviewer_choice:kind==='unresolved'?row.reviewer_classification:row.sentence_review_status)===value;return `<button class="btn choice kh ${selected?'selected':''}" data-action="${esc(value)}"><small>${esc(label)}</small>${esc(value)}</button>`}
function ambiguityCard(row){const alternatives=[1,2,3].filter(i=>row[`alternative_${i}`]&&row[`alternative_${i}`]!=='none');return `<article class="card"><div class="card-head"><div class="badges"><span class="badge">${esc(row.case_id)}</span><span class="badge ${esc(row.priority)}">${esc(row.priority)}</span><span class="badge">${esc(row.category)}</span></div><span class="muted">${esc(row.sentence_id)}</span></div><span class="label">Sentence context</span><div class="sentence kh">${highlighted(row.source_text,+row.span_start,+row.span_end)}</div><span class="label">Choose the contextually appropriate RAC path</span><div class="choices"><button class="btn choice kh ${row.reviewer_choice==='model'?'selected':''}" data-action="model"><small>Model (1)</small>${esc(row.model_choice)}</button>${alternatives.map(i=>`<button class="btn choice kh ${row.reviewer_choice===`alternative_${i}`?'selected':''}" data-action="alternative_${i}"><small>Alt ${i} (${i+1})</small>${esc(row[`alternative_${i}`])}</button>`).join('')}<button class="btn choice ${row.reviewer_choice==='uncertain'?'selected':''}" data-action="uncertain"><small>Uncertain (U)</small>Needs discussion</button></div><label class="label" for="notes">Reviewer notes</label><textarea id="notes" rows="3">${esc(row.reviewer_notes)}</textarea><details><summary>Dictionary evidence and path costs</summary><pre>${esc(row.path_costs)}\n${esc(row.rac_evidence)}</pre></details></article>`}
function unresolvedCard(row){const classes=['name','valid_missing_term','common_variant','borrowed_term','numeric_notation','typo','noise'];return `<article class="card"><div class="card-head"><div class="badges"><span class="badge">${esc(row.case_id)}</span><span class="badge">${esc(row.model_source)}</span><span class="badge">${esc(row.category)}</span></div><span class="muted">${esc(row.sentence_id)}</span></div><span class="label">Sentence context</span><div class="sentence kh">${highlighted(row.source_text,+row.span_start,+row.span_end)}</div><span class="label">Classification</span><div class="choices">${classes.map((v,i)=>`<button class="btn choice ${row.reviewer_classification===v?'selected':''}" data-action="${v}"><small>${i+1}</small>${v.replaceAll('_',' ')}</button>`).join('')}</div><label class="label">Reviewed boundaries inside this span</label><input id="reviewedText" class="wide-input kh" value="${esc(row.reviewed_segmented_text)}"><label class="label">Suggested RAC entry, when applicable</label><input id="suggestedEntry" class="wide-input kh" value="${esc(row.suggested_rac_entry)}"><label class="label">Reviewer notes</label><textarea id="notes" rows="3">${esc(row.reviewer_notes)}</textarea></article>`}
function sentenceCard(row){return `<article class="card"><div class="card-head"><div class="badges"><span class="badge">${esc(row.sentence_id)}</span><span class="badge">${esc(row.automatic_status)}</span><span class="badge">${esc(row.category)}</span></div></div><span class="label">Confirm only that this sentence is natural and correctly spelled</span><div class="sentence kh">${esc(row.source_text)}</div><span class="label">Model output for reference—not a boundary-review request</span><div class="kh">${esc(row.model_segmented_text)}</div><div class="choices" style="margin-top:18px"><button class="btn choice ${row.sentence_review_status==='approved'?'selected':''}" data-action="approved"><small>1</small>Approve sentence</button><button class="btn choice danger ${row.sentence_review_status==='rejected'?'selected':''}" data-action="rejected"><small>2</small>Reject sentence</button></div><label class="label">Reviewer notes</label><textarea id="notes" rows="3">${esc(row.sentence_reviewer_notes)}</textarea></article>`}
function bind(row){document.querySelectorAll('[data-action]').forEach(button=>button.onclick=()=>{const value=button.dataset.action;if(tab==='ambiguities')setChoice(row,value);else if(tab==='unresolved')setClassification(row,value);else setSentence(row,value)});const notes=document.getElementById('notes');if(notes)notes.onchange=()=>persist(tab,row,tab==='sentences'?{sentence_reviewer_notes:notes.value}:{reviewer_notes:notes.value});const reviewed=document.getElementById('reviewedText');if(reviewed)reviewed.onchange=()=>persist(tab,row,{reviewed_segmented_text:reviewed.value});const suggested=document.getElementById('suggestedEntry');if(suggested)suggested.onchange=()=>persist(tab,row,{suggested_rac_entry:suggested.value})}
function render(){const all=rows(tab),list=filtered();if(index>=list.length)index=Math.max(0,list.length-1);document.getElementById('priorityFilter').style.display=tab==='ambiguities'?'block':'none';document.getElementById('progress').textContent=progressText(all)+(list.length!==all.length?` · ${list.length} shown`:'');const content=document.getElementById('content');if(!list.length){content.innerHTML='<div class="card empty">No records match this filter.</div>';return}const row=list[index];content.innerHTML=(tab==='ambiguities'?ambiguityCard(row):tab==='unresolved'?unresolvedCard(row):sentenceCard(row))+`<div class="nav"><div class="nav-group"><button id="previous" class="btn">← Previous</button><button id="next" class="btn">Next →</button></div><span class="progress">${index+1} of ${list.length}</span></div>`;document.getElementById('previous').onclick=()=>{index=Math.max(0,index-1);render()};document.getElementById('next').onclick=()=>{index=Math.min(list.length-1,index+1);render()};bind(row)}
function tsvValue(value){return String(value??'').replace(/[\t\r\n]+/g,' ')}
function exportTSV(kind){const headers=DATA[kind].headers,body=rows(kind).map(row=>headers.map(header=>tsvValue(row[header])).join('\t'));const blob=new Blob(['\ufeff',headers.join('\t'),'\n',body.join('\n'),'\n'],{type:'text/tab-separated-values;charset=utf-8'});const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download=FILENAMES[kind];link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000)}
function parseTSV(text){const lines=text.replace(/^\ufeff/,'').split(/\r?\n/).filter(Boolean),headers=lines.shift().split('\t');return {headers,rows:lines.map(line=>Object.fromEntries(headers.map((header,i)=>[header,line.split('\t')[i]??''])))} }
async function importReviewed(files){let imported=0;for(const file of files){const parsed=parseTSV(await file.text());let kind;if(parsed.headers.includes('sentence_review_status'))kind='sentences';else if(parsed.headers.includes('reviewer_classification'))kind='unresolved';else if(parsed.headers.includes('reviewer_choice'))kind='ambiguities';else continue;const known=new Set(DATA[kind].rows.map(row=>row.case_id||row.sentence_id));for(const row of parsed.rows){const id=row.case_id||row.sentence_id;if(!known.has(id))continue;saved[`${kind}:${id}`]=row;imported++}}localStorage.setItem(STORAGE_KEY,JSON.stringify(saved));index=0;render();flash(`Imported ${imported} records`)}
document.querySelectorAll('[data-tab]').forEach(button=>button.onclick=()=>{tab=button.dataset.tab;index=0;document.querySelectorAll('[data-tab]').forEach(x=>x.classList.toggle('active',x===button));render()});document.querySelectorAll('[data-export]').forEach(button=>button.onclick=()=>exportTSV(button.dataset.export));['statusFilter','priorityFilter','search'].forEach(id=>document.getElementById(id).oninput=()=>{index=0;render()});
document.getElementById('importButton').onclick=()=>document.getElementById('importFiles').click();document.getElementById('importFiles').onchange=event=>importReviewed([...event.target.files]);
document.addEventListener('keydown',event=>{if(['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName))return;const list=filtered();if(!list.length)return;const row=list[index];if(event.key==='ArrowLeft'){index=Math.max(0,index-1);render()}else if(event.key==='ArrowRight'){index=Math.min(list.length-1,index+1);render()}else if(tab==='ambiguities'&&event.key==='1')setChoice(row,'model');else if(tab==='ambiguities'&&['2','3','4'].includes(event.key)){const choice=`alternative_${+event.key-1}`;if(row[choice]&&row[choice]!=='none')setChoice(row,choice)}else if(tab==='ambiguities'&&event.key.toLowerCase()==='u')setChoice(row,'uncertain');else if(tab==='unresolved'&&['1','2','3','4'].includes(event.key))setClassification(row,['name','valid_missing_term','typo','noise'][+event.key-1]);else if(tab==='sentences'&&event.key==='1')setSentence(row,'approved');else if(tab==='sentences'&&event.key==='2')setSentence(row,'rejected')});
render();
</script>
</body>
</html>'''


if __name__ == "__main__":
    main()
