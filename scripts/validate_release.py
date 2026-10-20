"""Validate the English replication data and, optionally, release checksums."""
from pathlib import Path
from collections import Counter
import argparse
import csv
import hashlib
import json
import re
from reproduce import ROOT, read_csv

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-checksums',action='store_true')
    args=parser.parse_args()
    bugs=read_csv(ROOT/'data/bugs.csv')
    tasks=read_csv(ROOT/'data/rq5_outcomes.csv')
    index=read_csv(ROOT/'data/model_output_index.csv')
    assert len(bugs)==459 and len(tasks)==229 and len(index)==687
    assert len({r['bug_id'] for r in bugs})==459
    for r in bugs:
        assert all(r[k] for k in ['issue_summary','symptom_summary','root_cause_summary','fix_summary'])
    assert not any(k.startswith('evidence_review_') or k=='unresolved_fields' for k in bugs[0])
    assert {r['bug_id'] for r in tasks}=={r['bug_id'] for r in bugs if 1<=int(r['patch_loc'])<=35}
    assert Counter(r['framework'] for r in bugs)=={'Tianshou':54,'TRL':126,'RLlib':179,'Stable-Baselines3':100}
    assert sum(r['symptom'] in ('Crash','Functional Failure') for r in bugs)==370
    assert Counter(r['root_cause_code'] for r in bugs)=={'C1':43,'C2':60,'C3':47,'C4':43,'C5':43,'C6':32,'C7':43,'C8':87,'C9':61}
    assert [sum(int(r[k]) for r in tasks) for k in ['gpt_success','deepseek_success','qwen_success']]==[98,92,92]
    assert sum(bool(r['path']) for r in index)==395
    for r in index:
        assert r['bug_id'] in {t['bug_id'] for t in tasks}
        if r['path']:
            path=ROOT/'data'/r['path']
            assert path.is_file(),r['path']
            # This response's explanatory prose was translated; its code diff is unchanged.
            translated_explanation=(r['bug_id']=='trl-3666' and 'deepseek' in r['model'].lower())
            if not translated_explanation:
                assert hashlib.sha256(path.read_text('utf-8').encode()).hexdigest()==r['source_text_sha256'],r['path']
    public_files=[]
    for folder in ['data','docs','prompts','rq5','scripts','results','figures']:
        public_files.extend(p for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    public_files += [ROOT/'README.md',ROOT/'requirements.txt',ROOT/'requirements-tested.txt',ROOT/'.gitignore']
    for path in public_files:
        relative=path.relative_to(ROOT).as_posix()
        assert not re.search('[\u4e00-\u9fff]',relative),relative
        if path.suffix in {'.csv','.json','.jsonl','.md','.txt','.py'}:
            text=path.read_text('utf-8-sig')
            assert not re.search('[\u4e00-\u9fff]',text),f'Untranslated text in {relative}'
            assert not re.search(r'(?i)[A-Z]:[\\/](?:Users|study)[\\/]',text),f'Local path in {relative}'
            assert not re.search(r'\b(?:ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9_-]{32,})',text),f'Possible secret in {relative}'
    if args.verify_checksums:
        for line in (ROOT/'SHA256SUMS').read_text('utf-8').splitlines():
            expected,name=line.split('  ',1)
            assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected,name
    by_id={r['bug_id']:r for r in bugs}
    for name in ['rq3_long_tail_cases.csv','rq4_small_loc_cases.csv']:
        for r in read_csv(ROOT/'results'/name):
            assert r==by_id[r['bug_id']],f'Stale derived record: {name}, {r["bug_id"]}'
    print(json.dumps({'bugs':len(bugs),'rq5_tasks':len(tasks),'available_response_texts':395,'missing_response_texts':292,'public_files_checked':len(public_files),'status':'passed'},indent=2))

if __name__=='__main__':
    main()
