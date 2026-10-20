"""Pairwise Pearson chi-square tests with Benjamini-Yekutieli correction."""
from itertools import combinations
from collections import Counter
import numpy as np
from scipy.stats import chi2_contingency
from reproduce import ROOT, FRAMEWORKS, read_csv, write_csv

def main():
    bugs=read_csv(ROOT/'data/bugs.csv')
    output=[]
    for field in ['symptom','root_cause']:
        categories=sorted({r[field] for r in bugs})
        tests=[]
        for a,b in combinations(FRAMEWORKS,2):
            counters=[Counter(r[field] for r in bugs if r['framework']==fw) for fw in [a,b]]
            observed=np.array([[counts[c] for c in categories] for counts in counters])
            observed=observed[:,observed.sum(axis=0)>0]
            statistic,p,dof,expected=chi2_contingency(observed,correction=False)
            tests.append(dict(dimension=field,framework_a=a,framework_b=b,chi_square=float(statistic),df=int(dof),p_raw=float(p),p_by=0.0,expected_cells_below_5=int((expected<5).sum()),expected_cells=int(expected.size)))
        m=len(tests)
        harmonic=sum(1/i for i in range(1,m+1))
        order=sorted(range(m),key=lambda i:tests[i]['p_raw'])
        previous=1.0
        for rank in range(m,0,-1):
            test=tests[order[rank-1]]
            previous=min(previous,test['p_raw']*m*harmonic/rank)
            test['p_by']=previous
        output.extend(tests)
    (ROOT/'results').mkdir(exist_ok=True)
    write_csv(ROOT/'results/distribution_tests.csv',output)
    print('Wrote 12 comparisons; correction is applied separately to each six-test family.')

if __name__=='__main__':
    main()
