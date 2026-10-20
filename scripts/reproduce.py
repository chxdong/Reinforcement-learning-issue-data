"""Recompute the paper's descriptive statistics and paired RQ5 comparisons."""
from pathlib import Path
from collections import Counter
from statistics import mean, median, stdev, NormalDist
from math import sqrt, exp
import argparse
import csv
import json

ROOT = Path(__file__).resolve().parents[1]
FRAMEWORKS = ['Tianshou', 'TRL', 'RLlib', 'Stable-Baselines3']
MODELS = ['GPT-5.3-Codex', 'DeepSeek-Flash', 'Qwen3.5-122B-A10B']
LABELS = ['gpt_success', 'deepseek_success', 'qwen_success']

def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def write_csv(path, rows):
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

def wilson(success, n):
    z = NormalDist().inv_cdf(0.975)
    p = success / n
    denominator = 1 + z*z/n
    center = (p + z*z/(2*n)) / denominator
    radius = z * sqrt(p*(1-p)/n + z*z/(4*n*n)) / denominator
    return [100*(center-radius), 100*(center+radius)]

def repair_summary(records):
    n = len(records)
    matrix = [[int(r[col]) for col in LABELS] for r in records]
    counts = [sum(r[i] for r in matrix) for i in range(3)]
    row_sums = [sum(r) for r in matrix]
    total = sum(counts)
    denominator = 3*total - sum(x*x for x in row_sums)
    q = 2*(3*sum(x*x for x in counts)-total*total)/denominator if denominator else None
    return dict(n=n, models=[dict(model=model,success=s,failure=n-s,rate=100*s/n,ci=wilson(s,n)) for model,s in zip(MODELS,counts)],
        Q=q, p=exp(-q/2) if q is not None else None,
        overlap={str(k):row_sums.count(k) for k in range(4)}, union=sum(x>0 for x in row_sums))

def distribution(bugs, field):
    names = [name for name,_ in Counter(r[field] for r in bugs).most_common()]
    rows=[]
    for fw in FRAMEWORKS:
        subset=[r for r in bugs if r['framework']==fw]
        counts=Counter(r[field] for r in subset)
        for name in names:
            rows.append(dict(framework=fw, category=name, count=counts[name], total=len(subset), percentage=100*counts[name]/len(subset)))
    return rows

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'results')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    bugs=read_csv(ROOT/'data/bugs.csv')
    tasks=read_csv(ROOT/'data/rq5_outcomes.csv')
    assert len(bugs)==len({r['issue_html_url'] for r in bugs})==459
    assert len(tasks)==len({r['issue_html_url'] for r in tasks})==229
    selected={r['issue_html_url'] for r in bugs if 1<=int(r['patch_loc'])<=35}
    assert selected=={r['issue_html_url'] for r in tasks}
    assert all(r[k] in ('0','1') for r in tasks for k in LABELS)
    valid_locs=[int(r['patch_loc']) for r in bugs if int(r['patch_loc'])>0]
    selection=dict(all_bugs=len(bugs),zero_loc=len(bugs)-len(valid_locs),positive_loc=len(valid_locs),p50=median(valid_locs),rq5_tasks=len(tasks),small_loc=sum(int(r['patch_loc'])<=10 for r in tasks))
    assert selection==dict(all_bugs=459,zero_loc=2,positive_loc=457,p50=35,rq5_tasks=229,small_loc=109)
    write_csv(args.output/'rq1_symptoms_by_framework.csv',distribution(bugs,'symptom'))
    write_csv(args.output/'rq2_roots_by_framework.csv',distribution(bugs,'root_cause'))
    pairs=Counter((r['root_cause'],r['symptom']) for r in bugs)
    write_csv(args.output/'rq2_sankey.csv',[dict(Source=a,Target=b,Value=n) for (a,b),n in sorted(pairs.items())])
    metrics=[]
    for fw in FRAMEWORKS:
        for column in ['open_days','issue_comments','patch_loc','changed_files']:
            values=[float(r[column]) for r in bugs if r['framework']==fw and r[column]!='']
            metrics.append(dict(framework=fw,metric=column,n=len(values),minimum=min(values),maximum=max(values),mean=mean(values),median=median(values),sample_std=stdev(values)))
    write_csv(args.output/'rq3_repair_metrics.csv',metrics)
    write_csv(args.output/'rq3_long_tail_cases.csv',[r for r in bugs if float(r['open_days'])>=28 or int(r['issue_comments'])>=4 or int(r['patch_loc'])>=75])
    write_csv(args.output/'rq4_small_loc_cases.csv',[r for r in bugs if 1<=int(r['patch_loc'])<=10])
    output=dict(selection=selection,overall=repair_summary(tasks),small=repair_summary([r for r in tasks if int(r['patch_loc'])<=10]),
        roots={f'C{i}':repair_summary([r for r in tasks if r['root_cause_code']==f'C{i}']) for i in range(1,10)},
        frameworks={fw:repair_summary([r for r in tasks if r['framework']==fw]) for fw in FRAMEWORKS})
    output['temporal']=[]
    for model,label,cutoff in zip(MODELS,LABELS,['2025-08-31','2025-05-31','2025-07-31']):
        groups={}
        for name,later in [('on_or_before',False),('after',True)]:
            records=[r for r in tasks if (r['created_at'][:10]>cutoff)==later]
            success=sum(int(r[label]) for r in records)
            groups[name]=dict(n=len(records),success=success,rate=100*success/len(records))
        output['temporal'].append(dict(model=model,cutoff=cutoff,groups=groups))
    # Independent saved analysis is a reference, not an input to calculations.
    reference=json.loads((ROOT/'data/reference_rq5_results.json').read_text('utf-8'))
    for scope in ['overall','small']:
        for field in ['n','models','Q','p','overlap','union']:
            assert output[scope][field]==reference[scope][field],(scope,field)
    for scope in ['roots','frameworks']:
        for group in reference[scope]:
            assert output[scope][group]['models']==reference[scope][group]['models'],(scope,group)
    assert output['temporal']==reference['temporal']
    (args.output/'rq5_results.json').write_text(json.dumps(output,indent=2)+'\n',encoding='utf-8')
    flat=[]
    for group, result in [('overall',output['overall']),('1-10 LOC',output['small'])]+list(output['roots'].items()):
        for row in result['models']:
            flat.append(dict(group=group,n=result['n'],model=row['model'],success=row['success'],failure=row['failure'],rate_percent=row['rate'],wilson_low_percent=row['ci'][0],wilson_high_percent=row['ci'][1]))
    write_csv(args.output/'rq5_tables.csv',flat)
    print(json.dumps({'selection':selection,'overall':output['overall'],'small':output['small']},indent=2))
    print(f'Results written to {args.output.resolve()}')

if __name__=='__main__':
    main()
