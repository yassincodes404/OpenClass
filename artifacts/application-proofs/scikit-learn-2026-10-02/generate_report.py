import html
import json
import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path('/home/yassin/Projects/OpenClass/artifacts/application-proofs/scikit-learn-2026-10-02')


def load(name, default=None):
    path = ROOT / name
    return json.loads(path.read_text()) if path.exists() else default


def ratio(num, den):
    return num / den if den else None


def quantile(values, fraction):
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * fraction
    lo, hi = math.floor(position), math.ceil(position)
    return values[lo] + (values[hi] - values[lo]) * (position - lo)


def metric(rows):
    successful = [row for row in rows if row.get('run')]
    known = [row for row in successful if row['reference'] != 'UNKNOWN']
    heldout = [row for row in successful if row['reference'] == 'UNKNOWN']
    unknown = [row for row in successful if row['run']['selected_choice'] == 'UNKNOWN']
    trusted = [row for row in successful if row['run']['supervision_outcome'] == 'TRUSTED']
    false_trust = [row for row in trusted if not row['correct']]
    classes = ['BUG','ENHANCEMENT','DOCUMENTATION','UNKNOWN']
    confusion = {truth: {pred: sum(row['reference'] == truth and row['run']['selected_choice'] == pred for row in successful) for pred in classes} for truth in classes}
    f1 = {}
    for label in classes:
        tp = confusion[label][label]
        fn = sum(confusion[label].values()) - tp
        fp = sum(confusion[other][label] for other in classes if other != label)
        f1[label] = ratio(2*tp,2*tp+fn+fp)
    usage = [row['run']['provider_metadata'] for row in successful]
    costs = [row['estimated_cost'] for row in usage if row.get('estimated_cost') is not None]
    return {
        'source_cases':60, 'recorded_terminal_cases':len(rows), 'completed_unique_cases':len(successful),
        'failed_terminal_cases':len([row for row in rows if not row.get('run')]),
        'source_label_coverage':ratio(len(successful),60),
        'correct':sum(row['correct'] for row in successful), 'accuracy':ratio(sum(row['correct'] for row in successful),len(successful)),
        'known_correct':sum(row['correct'] for row in known), 'known_completed':len(known),
        'known_accuracy':ratio(sum(row['correct'] for row in known),len(known)),
        'heldout_completed':len(heldout), 'heldout_unknown_detected':sum(row['correct'] for row in heldout),
        'heldout_unknown_recall':ratio(sum(row['correct'] for row in heldout),len(heldout)),
        'unknown_predictions':len(unknown), 'unknown_precision':ratio(sum(row['correct'] for row in unknown),len(unknown)),
        'unknown_rate':ratio(len(unknown),len(successful)),
        'trusted':len(trusted), 'trusted_errors':len(false_trust), 'trusted_error_rate':ratio(len(false_trust),len(trusted)),
        'macro_f1':sum(value for value in f1.values() if value is not None)/len(classes),
        'per_class_f1':f1, 'confusion_matrix':confusion,
        'latency_sample_count':len(successful),
        'p50_latency_ms':quantile([row['run']['latency_ms'] for row in successful],0.5),
        'p95_latency_ms':quantile([row['run']['latency_ms'] for row in successful],0.95),
        'unique_completed_decision_reported_cost_usd':sum(costs), 'cost_coverage':ratio(len(costs),len(successful)),
        'all_runs_real':all(row['run']['real_inference'] and not row['run']['provider_metadata'].get('simulated') for row in successful),
        'failures': [{'number':row['number'], 'url':row['source_url'], 'reference':row['reference'],
                      'prediction':row['run']['selected_choice'],'supervision':row['run']['supervision_outcome'],
                      'scores':row['run']['probabilities']} for row in successful if not row['correct']],
    }


def pct(value):
    return f'{value*100:.1f}%' if value is not None else 'unavailable'


manifest = load('manifest.json')
metrics = {key:metric(load(key+'-decisions.json',[])) for key in ['gpt','gemini']}
telemetry = [json.loads(line) for line in (ROOT/'provider-telemetry.jsonl').read_text().splitlines()]
reported_costs = [row['cost_usd'] for row in telemetry if row.get('cost_usd') is not None]
events = Counter(row['event'] for row in telemetry)
result = {
    'generated_at_utc':datetime.now(UTC).isoformat(), 'branch':'origin/feat/portal-phase-10',
    'baseline_commit':'d539862', 'deployment':'Local Phase 10 checkout with bounded real-provider wiring',
    'workspace':manifest['workspace'], 'metrics':metrics,
    'provider_telemetry_event_counts':dict(events),
    'gateway_reported_pipeline_cost_usd':sum(reported_costs),
    'pipeline_calls_with_reported_cost':len(reported_costs),
    'cost_scope':'Reported successful API-pipeline choice/cluster-discovery calls, including persisted diagnostic duplicates; excludes embeddings without reported cost, connectivity probes, legacy Teacher/diagnosis calls without persisted cost, and unreported failed-call charges. This is not a complete bill.',
    'provider_errors_by_status':dict(Counter(str(row.get('status')) for row in telemetry if row['event']=='provider.error')),
    'blocked_metrics': {'learned_improvement':None,'knowledge_retention':None,'execution_success_rate':None,
                        'verification_success_rate':None,'complete_teacher_cost':None},
}
(ROOT/'results.json').write_text(json.dumps(result,indent=2))

comparison = '\n'.join(f"| {key.upper()} | {m['completed_unique_cases']}/60 | {m['known_correct']}/{m['known_completed']} ({pct(m['known_accuracy'])}) | {m['heldout_unknown_detected']}/{m['heldout_completed']} ({pct(m['heldout_unknown_recall'])}) | {m['trusted_errors']}/{m['trusted']} ({pct(m['trusted_error_rate'])}) |" for key,m in metrics.items())
failure_lines = []
for key,m in metrics.items():
    for row in m['failures'][:8]:
        failure_lines.append(f"- {key.upper()}: [issue #{row['number']}]({row['url']}) — reference `{row['reference']}`, prediction `{row['prediction']}`, supervision `{row['supervision']}`.")
project_lines = '\n'.join(f"- [{key.upper()} project](http://127.0.0.1:5173/projects/{conf['project']['id']})" for key,conf in manifest['projects'].items())
discovery_lines=[]
for key in metrics:
    discoveries=load(key+'-discoveries.json',[])
    teacher=load(key+'-teacher.json')
    discovery_lines.append(f"- {key.upper()}: {len(load(key+'-clusters.json',[]))} real embedding clusters; {len([r for r in discoveries if r.get('candidate')])} persisted cluster proposals. Teacher: `{(teacher or {}).get('proposal',{}).get('kind','unavailable')}`.")
    for entry in discoveries:
        candidate=entry.get('candidate')
        if candidate:
            discovery_lines.append(f"  - `{candidate['type']}` / `{candidate.get('canonical_name')}` from {entry['cluster_size']} runs; status `{candidate['status']}`, provider `{candidate['provider']}`.")

report=f'''# Real scikit-learn issue triage: measured local application challenge

Workspace: **{manifest['workspace']['name']}**. Source: [actual public scikit-learn issues](https://github.com/scikit-learn/scikit-learn/issues). The frozen 60-case cohort uses real source text, real inference and real embeddings. Additional portal observations without source provenance are excluded from all case metrics; two clustering proposals contain these extra observations and are not source-grounded application evidence. Local sign-in is the existing development admin account.

{project_lines}

## Protocol and independent references

60 distinct actual issues, 15 each with exclusive task labels Bug, Enhancement, Documentation and Build / CI. Known choices are BUG, ENHANCEMENT and DOCUMENTATION; Build / CI is deliberately absent and its reference is UNKNOWN. Both providers see the same source title/body without maintainer labels. Data, timestamps, exact submitted text, SHA-256 hashes, truncations, exclusions and selection rules are retained in `dataset.json`, `protocol.json` and GitHub snapshots. Labels are independent source references, not model-generated truth or full human adjudication. Titles sometimes disclose type tags, so this is a small curated application probe, not a production accuracy estimate. Successful retries do not remove original failures.

## Results

| Provider | Completed source cases | Known accuracy | Held-out UNKNOWN recall | Errors labeled TRUSTED |
|---|---:|---:|---:|---:|
{comparison}

Full confusion matrices, per-class F1, UNKNOWN precision, p50/p95 latency, run IDs, distributions, provenance and source links are in `results.json` and per-provider decisions. Providers cannot be ranked on these incomplete, differently covered samples. Across all 15 withheld cases, GPT detected 4 and Gemini detected 2; the displayed recall uses only completed cases. Accuracy denominators use completed independent-source-labeled cases; completion coverage and failed terminal cases are shown separately. One reconciled persisted run per source/model is used for metrics; additional attempts and diagnostic runs remain in the database.

Gateway-reported cost for the instrumented API pipeline: **${result['gateway_reported_pipeline_cost_usd']:.6f} USD**, across {len(reported_costs)} calls with reported cost. Scope: {result['cost_scope']} Missing costs are unavailable, not zero.

## Real disagreements

{chr(10).join(failure_lines)}

Every disagreement is retained. A source label can be imperfect; these are disagreements against the declared independent reference, not invented certainty about the correct route.

## Discovery and learning boundaries

{chr(10).join(discovery_lines)}

Teacher and discovery suggestions are inactive proposals, never ground truth. Evaluation/activation guard responses and unchanged service snapshots are saved. Verified replay evaluation, human approval, immutable activation and a verified external task execution are not implemented by this branch. No learned improvement, retention, real-world action success or end-to-end autonomous learning is claimed.

## What this challenged

1. The original Phase 10 clustering and cluster-discovery endpoints hard-coded simulated adapters; bounded existing-port HTTP wiring was required to run this real-only case. The original branch cannot claim these results without that local patch.
2. Real requests exposed gateway HTTP 429s, surfaced by the portal as generic HTTP 502s. Failures were retained, retries paced and persisted results reconciled. Error identity/usage and recovery are insufficient for production operation.
3. The full real ingestion request exceeded the control plane's HTTP body limit (413); eight-item batches succeeded. Batch item limits alone do not describe payload byte limits.
4. Uncalibrated LLM self-assessment can receive TRUSTED status through the current generic margin rule. The trusted-reference-error denominator is reported explicitly.
5. Decision-service instructions are stored, but the executor's choice port carries the observation and bounded ontology, not the full service instructions. This experiment encoded scope in choice definitions too.
6. The UNKNOWN/clustering surface examines only the latest 200 runs. Repeated source events, mixed providers and long-lived projects need explicit cohort/evidence handling; this report reconciles unique source/model records.
7. Provider-config cards are stored references rather than enforced bindings. Explicit per-service model overrides were added and used for this comparison. Embedding/discovery/Teacher telemetry is not fully reflected in portal cost rollups.
8. Jev was actually attempted through Vercel and returned HTTP 403 `no_providers_available`; Gemini and GPT connectivity and decisions were real hosted calls.
9. Core audit reads return HTTP 400 after clustering because stored audit payloads disagree with the core reader schema. Authenticated control-plane audit reads still work; both outcomes are retained.
10. Code inspection shows re-clustering deletes previous clusters and cascades to their proposals, threatening retained review history. This destructive path was not exercised again. Three of the five current clusters contain frozen-cohort sources; two contain additional observations without source provenance.
11. The safe evaluation and activation blocks remain in force. Before/after learned quality and verified outbound action metrics are unavailable.

## Validation and retained artifacts

Focused adapter and Phase 9/10 contract/persistence tests: 28 passed. Python lint/format and provider/server strict typing passed. Portal and control-plane builds/tests passed; Python package builds passed. A freshly migrated disposable PostgreSQL database passed all four persistence tests with explicit mock test fixtures; those fixtures are separate from the real application workspace. The default-provider persistence run failed the unchanged unavailable-Laya assumption. Full `make check` fails on 79 existing Prettier formatting files. Full `make test` yielded 412 passed, 14 skipped, 2 failures in unchanged Laya/supervisor assumptions. Full `npm run build` could not build the separate unused Next.js app because its dependency download/install was incomplete. These qualifications are retained in validation logs; they are not passing-release claims.

The experiment is an isolated local Phase 10 checkout. `provider-wiring.patch`, the added adapter/tests, the credential-free runner and the provider guide preserve the reviewable change. No upstream issues, packages, releases or images were published.
'''
(ROOT/'REPORT.md').write_text(report)

data={'metrics':metrics,'manifest':manifest,'dataset':load('dataset.json'),'result':result,
      'discoveries':{k:load(k+'-discoveries.json',[]) for k in metrics},
      'decisions':{k:load(k+'-decisions.json',[]) for k in metrics}}
serialized=json.dumps(data,ensure_ascii=False).replace('<','\\u003c')
page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OpenClass · Real issue triage</title><style>
*{box-sizing:border-box}body{margin:0;background:#f5f5f0;color:#172d29;font:16px system-ui}main{max-width:1200px;margin:auto;padding:48px 24px}header{border-bottom:1px solid #c9d2cb;padding-bottom:24px}.eyebrow{font-size:12px;letter-spacing:.16em;color:#547167}h1{font-size:clamp(32px,5vw,58px);max-width:850px;line-height:1.1;margin:15px 0}h2{margin-top:32px}a{color:#23634f}.lede{max-width:850px;color:#52675d;line-height:1.65}.cards{display:grid;grid-template-columns:1fr 1fr;gap:20px}.card{background:white;border:1px solid #d3ddd3;border-radius:14px;padding:24px}.metrics{display:grid;grid-template-columns:1fr 1fr;gap:18px}.number{font-size:32px;font-weight:650}.label{font-size:13px;color:#64746a}.warn{background:#faf0d9;border:1px solid #ddbf70;padding:18px;border-radius:10px;line-height:1.6}.tag{display:inline-block;padding:4px 9px;background:#e1efe5;border-radius:20px;font-size:12px}table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:12px 8px;border-bottom:1px solid #d9e0d6}th{font-size:12px;color:#64746a}select,input{padding:10px;border:1px solid #bccabc;border-radius:8px;background:white}button{cursor:pointer}.bad{color:#a33624}.good{color:#23634f}.scroll{overflow:auto}ul{line-height:1.8}.links{display:flex;gap:20px;margin:20px 0}.cost{font-size:14px;color:#657468}footer{margin-top:30px;font-size:13px;color:#617266}@media(max-width:720px){.cards{grid-template-columns:1fr}main{padding:24px 16px}}
</style><main><header><p class="eyebrow">OPENCLASS / ACTUAL APPLICATION EVIDENCE</p><h1>Real issues.<br>Measured decisions.</h1><p class="lede">60 public scikit-learn maintainer issues. Two hosted LLMs. Three known routes and a withheld build/CI category. Source labels are independent references; every disagreement and failed attempt is retained.</p><span class="tag">Real source data + real inference</span> <span class="tag">Local Phase 10 experiment</span><div class="links" id="links"></div></header><h2>Provider comparison</h2><div class="cards" id="cards"></div><p class="cost" id="cost"></p><h2>What the project still cannot claim</h2><p class="warn">Uncalibrated LLM scores can be marked TRUSTED by the current margin rule. The original branch used simulated clustering/discovery; this run needed a local real-provider patch. Verified replay evaluation, approval, immutable activation and verified external execution remain unavailable. No learning improvement or production readiness is claimed.</p><p class="warn">Coverage differs substantially: GPT detected UNKNOWN on 4 of all 15 withheld cases, Gemini on 2 of 15. Recall cards count completed cases only; these incomplete samples do not support ranking the providers. Embedding costs are unavailable. Core audit reads fail after clustering; control audit works. Re-clustering has a code-verified history-deletion gap.</p><h2>Inactive discoveries</h2><p>Three clusters contain frozen GitHub source evidence. Two additional clusters contain portal observations without source provenance and are excluded from case metrics. All five proposals remain inactive.</p><div id="discoveries"></div><h2>Inspect every source case</h2><p><select id="model"><option value="gpt">GPT-4.1 mini</option><option value="gemini">Gemini 2.5 Flash</option></select> <select id="filter"><option value="all">All cases</option><option value="wrong">Reference disagreements</option><option value="trusted">Trusted disagreements</option><option value="unknown">Held-out build / CI</option><option value="error">Failed terminal cases</option></select> <input id="search" placeholder="Search issue title or number"></p><div class="scroll"><table><thead><tr><th>Actual source issue</th><th>Reference</th><th>Prediction</th><th>Supervision</th><th>Outcome</th></tr></thead><tbody id="rows"></tbody></table></div><h2>Interpretation and evidence</h2><ul><li>Curated source labels can be imperfect; title tags and templates may make some items easier.</li><li>Sources and hypotheses were frozen before inference. Only exact source title/body text was submitted, with documented truncation; source labels were excluded.</li><li>Duplicate and interrupted attempts are reconciled from persisted run IDs. Earlier HTTP 429/502 failures remain in the artifact history.</li><li>The full-batch import hit HTTP 413; small batches worked. Jev returned 403 no_providers_available.</li><li>Source records, exact inputs, distributions, costs, latency, confusion matrices, audit history, guards and code patch are retained locally.</li></ul><footer id="footer"></footer></main><script>
const DATA=__DATA__;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct=v=>v==null?'unavailable':(v*100).toFixed(1)+'%';
document.getElementById('links').innerHTML=Object.entries(DATA.manifest.projects).map(([k,v])=>`<a href="/projects/${v.project.id}">${k==='gpt'?'GPT':'Gemini'} workspace project ↗</a>`).join('');
document.getElementById('cards').innerHTML=Object.entries(DATA.metrics).map(([k,m])=>`<article class="card"><p class="eyebrow">${k==='gpt'?'GPT-4.1 MINI':'GEMINI 2.5 FLASH'}</p><div class="metrics"><div><div class="number">${pct(m.known_accuracy)}</div><div class="label">known label agreement · ${m.known_correct}/${m.known_completed}</div></div><div><div class="number">${pct(m.heldout_unknown_recall)}</div><div class="label">held-out UNKNOWN recall · ${m.heldout_unknown_detected}/${m.heldout_completed}</div></div><div><div class="number bad">${m.trusted_errors}/${m.trusted}</div><div class="label">trusted reference disagreements</div></div><div><div class="number">${m.completed_unique_cases}/60</div><div class="label">completed source cases</div></div></div><p class="label">Macro F1 ${m.macro_f1.toFixed(3)} · UNKNOWN precision ${pct(m.unknown_precision)} · p95 ${(m.p95_latency_ms/1000).toFixed(2)}s</p></article>`).join('');
document.getElementById('cost').textContent=`Reported instrumented pipeline cost: $${DATA.result.gateway_reported_pipeline_cost_usd.toFixed(6)} USD. Partial cost scope: excludes unreported Teacher/diagnosis and failed-call charges; full billing total unavailable.`;
document.getElementById('discoveries').innerHTML=Object.entries(DATA.discoveries).flatMap(([k,list])=>list.filter(x=>x.candidate).map(x=>`<article class="card"><span class="tag">${esc(x.candidate.type)}</span><h3>${esc(x.candidate.display_name||x.candidate.canonical_name||'Insufficient evidence')}</h3><p>${esc(x.candidate.definition||x.candidate.reason)}</p><p class="label">${esc(k)} · ${x.cluster_size} evidence runs · ${esc(x.candidate.status)} · ${esc(x.candidate.provider)}</p></article>`)).join('')||'<p>No persisted real cluster proposals available. See the retained failure records.</p>';
function render(){const model=document.getElementById('model').value,filter=document.getElementById('filter').value,q=document.getElementById('search').value.toLowerCase();const ds=new Map(DATA.dataset.map(x=>[x.number,x]));document.getElementById('rows').innerHTML=DATA.decisions[model].filter(x=>filter==='all'||filter==='wrong'&&x.run&&!x.correct||filter==='trusted'&&x.run&&!x.correct&&x.run.supervision_outcome==='TRUSTED'||filter==='unknown'&&x.reference==='UNKNOWN'||filter==='error'&&!x.run).filter(x=>(x.number+' '+ds.get(x.number).title).toLowerCase().includes(q)).map(x=>`<tr><td><a href="${esc(x.source_url)}" target="_blank" rel="noreferrer">#${x.number} · ${esc(ds.get(x.number).title)}</a></td><td>${esc(x.reference)}</td><td>${esc(x.run?.selected_choice||'HTTP '+x.error_status)}</td><td>${esc(x.run?.supervision_outcome||'not completed')}</td><td class="${x.correct?'good':'bad'}">${x.correct?'Matches reference':x.run?'Disagrees':'Failed'}</td></tr>`).join('');}
for(const id of ['model','filter','search'])document.getElementById(id).addEventListener('input',render);render();document.getElementById('footer').textContent='Generated '+DATA.result.generated_at_utc+' · Source evidence and exact protocol preserved in artifacts/application-proofs/scikit-learn-2026-10-02.';
</script></html>'''.replace('__DATA__',serialized)
(ROOT/'report.html').write_text(page)
Path('/tmp/openclass-portal-phase-10/apps/portal/public/real-issue-triage-report.html').write_text(page)
print(json.dumps({'metrics':{k:{field:value for field,value in m.items() if field in ['completed_unique_cases','known_accuracy','heldout_unknown_recall','trusted_errors','trusted']} for k,m in metrics.items()},'pipeline_cost_usd':result['gateway_reported_pipeline_cost_usd']}))
