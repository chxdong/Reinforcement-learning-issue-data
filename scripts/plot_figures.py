"""Recreate descriptive figures from released issue-level data."""
from pathlib import Path
import argparse
import textwrap
import os
os.environ.setdefault('MPLCONFIGDIR', str(Path(__file__).resolve().parents[1]/'.cache/matplotlib'))
for variable in ['OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS']:
    os.environ[variable] = '1'
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.path import Path as MplPath
from matplotlib import font_manager
import numpy as np
import pandas as pd
import seaborn as sns
from reproduce import ROOT, FRAMEWORKS

COLORS=['#FFB3BA','#FFE69C','#B5EAD7','#D8BFD8']

def save(fig,folder,name):
    fig.savefig(folder/f'{name}.pdf',bbox_inches='tight',pad_inches=0.04)
    fig.savefig(folder/f'{name}.png',dpi=220,bbox_inches='tight',pad_inches=0.04)
    plt.close(fig)

def distributions(df,folder,column,name):
    categories=df[column].value_counts().index.tolist()
    counts=pd.crosstab(df['framework'],df[column]).reindex(index=FRAMEWORKS,columns=categories,fill_value=0)
    proportions=counts.div(counts.sum(axis=1),axis=0)*100
    fig,ax=plt.subplots(figsize=(10,4.7))
    left=np.zeros(len(FRAMEWORKS))
    colors=plt.cm.Blues(np.linspace(0.3,0.9,len(categories)))
    for category,color in zip(categories,colors):
        values=proportions[category].values
        ax.barh(FRAMEWORKS,values,left=left,color=color,edgecolor='white',linewidth=0.7,label=category)
        for i,v in enumerate(values):
            if v>=5:
                ax.text(left[i]+v/2,i,f'{v:.0f}%',ha='center',va='center',fontsize=10,color='white' if sum(color[:3])<1.5 else 'black')
        left+=values
    ax.invert_yaxis()
    ax.set_xlim(0,100)
    ax.set_xlabel('Percentage of issues within each framework')
    ax.legend(loc='upper center',bbox_to_anchor=(0.5,-0.17),ncol=2,frameon=False,fontsize=9)
    sns.despine(ax=ax)
    save(fig,folder,name)

def violin(df,folder):
    sns.set_theme(style='whitegrid')
    fig,axes=plt.subplots(3,4,figsize=(16,10))
    fields=['open_days','issue_comments','patch_loc']
    labels=['Bug Open Duration\n(days)','Number of Comments','Patch Size (LOC)']
    for i,(field,label) in enumerate(zip(fields,labels)):
        for j,fw in enumerate(FRAMEWORKS):
            ax=axes[i,j]
            values=df.loc[df.framework==fw,field].astype(float)
            sns.violinplot(y=values,ax=ax,cut=0,color=COLORS[j],inner='quartile',linewidth=1.5)
            lo,hi=values.min(),values.max()
            ax.set_ylim(max(0,lo-(hi-lo)*0.1),hi+(hi-lo)*0.2)
            avg,med,sd=values.mean(),values.median(),values.std()
            ax.axhline(med,color='#FF6B6B',linestyle='--',label='Median')
            ax.axhline(avg,color='#3769B0',label='Mean')
            ax.axhline(lo,color=COLORS[j],linestyle=':',label='Min')
            ax.axhline(hi,color=COLORS[j],linestyle='-.',label='Max')
            ax.fill_betweenx([avg-sd,avg+sd],-0.5,0.5,color=COLORS[j],alpha=0.2,label='Std Dev')
            ymin,ymax=ax.get_ylim()
            median_y=max((med-ymin)/(ymax-ymin)+0.05,0.145)
            mean_y=max((avg-ymin)/(ymax-ymin)+0.10,median_y+0.14)
            std_y=max((avg+sd-ymin)/(ymax-ymin)+0.12,mean_y+0.18)
            for x,y,text,ha,va,color in [(0.96,0.88,f'Max: {hi:.2f}','right','top','#222222'),(0.96,std_y,f'Std Dev: {sd:.2f}','right','bottom','teal'),(0.04,mean_y,f'Mean: {avg:.2f}','left','bottom','#3769B0'),(0.04,median_y,f'Median: {med:.2f}','left','bottom','#D94B4B'),(0.96,0.015,f'Min: {lo:.2f}','right','bottom','#3769B0')]:
                ax.text(x,y,text,transform=ax.transAxes,ha=ha,va=va,color=color,fontproperties=font_manager.FontProperties(family='DejaVu Sans',weight='bold',size=20))
            ax.tick_params(axis='y',labelsize=20)
            ax.set_xticks([])
            ax.set_ylabel(label if j==0 else '',fontsize=18,fontweight='bold')
            ax.set_xlabel(fw if i==2 else '',fontsize=22,fontweight='bold')
    handles,legend=axes[0,0].get_legend_handles_labels()
    fig.legend(handles,legend,loc='upper center',bbox_to_anchor=(0.52,0.995),ncol=5,prop={'size':18,'weight':'bold'},frameon=False,handlelength=1.5,columnspacing=1)
    fig.subplots_adjust(left=0.085,right=0.995,bottom=0.075,top=0.93,wspace=0.28,hspace=0.12)
    save(fig,folder,'rq3_violin')

def sankey(df,folder):
    # A static vector rendering avoids a browser dependency during reproduction.
    causes=df.root_cause.value_counts()
    symptoms=df.symptom.value_counts()
    flows=pd.crosstab(df.root_cause,df.symptom)
    gap=0.012
    scale=(1-gap*(len(causes)-1))/len(df)
    def positions(totals):
        y=1.0
        gap_here=gap*(len(causes)-1)/(len(totals)-1)
        result={}
        for label,count in totals.items():
            height=count*scale
            result[label]=(y-height,y)
            y-=height+gap_here
        return result
    left,right=positions(causes),positions(symptoms)
    offsets_l={k:v[0] for k,v in left.items()}
    offsets_r={k:v[0] for k,v in right.items()}
    colors=dict(zip(causes.index,plt.cm.Spectral(np.linspace(0.08,0.92,len(causes)))))
    fig,ax=plt.subplots(figsize=(7.5,10))
    for cause in causes.index:
        for symptom in symptoms.index:
            value=int(flows.loc[cause,symptom])
            if not value:
                continue
            h=value*scale
            a,b=offsets_l[cause],offsets_r[symptom]
            vertices=[(0.04,a),(0.42,a),(0.58,b),(0.96,b),(0.96,b+h),(0.58,b+h),(0.42,a+h),(0.04,a+h),(0.04,a)]
            codes=[MplPath.MOVETO]+[MplPath.CURVE4]*3+[MplPath.LINETO]+[MplPath.CURVE4]*3+[MplPath.CLOSEPOLY]
            ax.add_patch(patches.PathPatch(MplPath(vertices,codes),facecolor=colors[cause],edgecolor='none',alpha=0.42))
            offsets_l[cause]+=h
            offsets_r[symptom]+=h
    for label,(bottom,top) in left.items():
        ax.add_patch(patches.Rectangle((0.015,bottom),0.025,top-bottom,facecolor=colors[label],edgecolor='gray',linewidth=0.5))
        ax.text(0.048,(top+bottom)/2,textwrap.fill(label,31),ha='left',va='center',fontsize=9)
        ax.text(0.007,(top+bottom)/2,str(causes[label]),ha='right',va='center',fontsize=10)
    for label,(bottom,top) in right.items():
        ax.add_patch(patches.Rectangle((0.96,bottom),0.025,top-bottom,facecolor='#dddddd',edgecolor='gray',linewidth=0.5))
        ax.text(0.952,(top+bottom)/2,label,ha='right',va='center',fontsize=10)
        ax.text(0.993,(top+bottom)/2,str(symptoms[label]),ha='left',va='center',fontsize=10)
    ax.set_xlim(-0.06,1.06)
    ax.set_ylim(-0.02,1.02)
    ax.axis('off')
    save(fig,folder,'rq2_sankey')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'figures')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'pdf.fonttype':42,'ps.fonttype':42})
    df=pd.read_csv(ROOT/'data/bugs.csv')
    distributions(df,args.output,'symptom','rq1_symptoms')
    distributions(df,args.output,'root_cause','rq2_root_causes')
    violin(df,args.output)
    sankey(df,args.output)
    print(f'Wrote four figures as PDF and PNG to {args.output}')

if __name__=='__main__':
    main()
