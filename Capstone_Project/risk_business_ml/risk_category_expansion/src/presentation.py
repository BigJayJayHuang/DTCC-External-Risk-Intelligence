from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

ROOT=Path(__file__).resolve().parents[1]
FIGURES=ROOT/'results/figures';FIGURES.mkdir(exist_ok=True)
ENGLISH=['Business continuity','Cybersecurity','Information technology','Data management','Processing / operations',
         'Clearing financial risks','Corporate financial','Model risk','Legal / regulatory','Third party','Human capital','Strategic']
plt.rcParams.update({'font.size':11,'axes.spines.top':False,'axes.spines.right':False,'figure.facecolor':'white',
                     'axes.labelcolor':'#252b32','text.color':'#252b32','savefig.dpi':160})

def primary_heatmap(matrix):
    values=matrix[[e+'_same_quarter_rho' for e in ['FICC','NSCC','DTC']]].to_numpy(float)
    ns=matrix[[e+'_same_quarter_n' for e in ['FICC','NSCC','DTC']]].to_numpy(int)
    cmap=LinearSegmentedColormap.from_list('association',['#1c679b','#ffffff','#c87728']);cmap.set_bad('#e5e7eb')
    fig,ax=plt.subplots(figsize=(10,9.7))
    im=ax.imshow(np.ma.masked_invalid(values),vmin=-1,vmax=1,cmap=cmap,aspect='auto')
    ax.set_yticks(range(12),ENGLISH);ax.set_xticks(range(3),['FICC','NSCC\nECS clearing\nproxy','DTC\nECS settlement\nproxy'])
    ax.tick_params(axis='both',length=0,pad=10)
    for i in range(12):
        for j in range(3):
            label='N/A' if np.isnan(values[i,j]) else f'{values[i,j]:+.2f}\nn={ns[i,j]}'
            ax.text(j,i,label,ha='center',va='center',fontsize=10,color='#252b32')
    ax.set_title('12 risk families: association with revenue growth',loc='left',pad=24,fontsize=14)
    bar=fig.colorbar(im,ax=ax,shrink=.75,pad=.045);bar.set_label('Spearman correlation (rho)')
    fig.subplots_adjust(left=.30,right=.92,top=.89,bottom=.20)
    fig.text(.04,.045,'Same-quarter retrospective pairs through 2026Q2; source coverage varies.\nNo comparison passes exploratory FDR 5%. External proxies do not establish DTCC exposure.',fontsize=10)
    fig.savefig(FIGURES/'twelve_family_revenue_heatmap.png');return fig

def lag_comparison(matrix):
    fig,axes=plt.subplots(1,2,figsize=(13,8.8),sharey=True)
    y=np.arange(12)
    for ax,e in zip(axes,['FICC','NSCC']):
        ax.barh(y-.18,matrix[e+'_same_quarter_rho'],height=.33,color='#246e9a',label='Same quarter')
        ax.barh(y+.18,matrix[e+'_next_quarter_rho'],height=.33,color='#c18436',label='Risk quarter → next business quarter')
        ax.axvline(0,color='#667085',lw=.9);ax.set_xlim(-1,1);ax.set_xticks([-1,-.5,0,.5,1]);ax.set_xlabel('Spearman rho')
        ax.set_title(e+' revenue growth',loc='left');ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
    axes[0].set_yticks(y,ENGLISH);axes[0].invert_yaxis()
    handles,labels=axes[0].get_legend_handles_labels();fig.legend(handles,labels,loc='upper center',ncol=2,bbox_to_anchor=(.63,.94),frameon=False)
    fig.subplots_adjust(left=.23,right=.97,top=.85,bottom=.14,wspace=.15)
    fig.text(.03,.04,'Each bar uses its available paired quarters; exact n and windows are in the results table.\nLagged association is retrospective and does not establish a usable point-in-time forecast.',fontsize=10)
    fig.savefig(FIGURES/'same_vs_next_quarter_associations.png');return fig

def risk_history():
    obs=pd.read_csv(ROOT/'data/expanded_risk_observations.csv');idx=pd.period_range('2020Q1','2026Q2',freq='Q')
    fig,axes=plt.subplots(2,2,figsize=(12,8.5))
    specs=[('kev_new_entries','ALL','CISA catalog additions','CVE entries'),
           ('cloud_infrastructure_incidents','ALL','Selected cloud infrastructure incident notices','Unique notice IDs'),
           ('finance_sector_quit_rate','ALL','Finance / insurance sector quit rate','Percent, quarterly monthly mean'),
           ('margin_backtest_uncovered_pct','FICC','FICC margin backtest uncovered share','Percent; trailing-year snapshot')]
    for ax,(feature,scope,title,unit) in zip(axes.ravel(),specs):
        d=obs[(obs.feature==feature)&(obs.entity_scope==scope)]
        s=d.set_index(pd.PeriodIndex(d.quarter,freq='Q')).value.reindex(idx)
        ax.plot(range(len(idx)),s,color='#246e9a',lw=1.7,marker='o',markersize=3)
        if feature=='margin_backtest_uncovered_pct':
            d=obs[(obs.feature==feature)&(obs.entity_scope=='NSCC')]
            z=d.set_index(pd.PeriodIndex(d.quarter,freq='Q')).value.reindex(idx)
            ax.plot(range(len(idx)),z,color='#c18436',lw=1.5,marker='s',markersize=3,label='NSCC')
            ax.lines[0].set_label('FICC (GSD + MBSD weighted)');ax.legend(frameon=False,fontsize=9)
        ticks=[0,8,16,25];ax.set_xticks(ticks,[str(idx[i]) for i in ticks]);ax.tick_params(axis='x',labelsize=10)
        ax.set_title(title,loc='left',fontsize=11);ax.set_ylabel(unit,fontsize=10);ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True)
    fig.subplots_adjust(left=.09,right=.97,top=.92,bottom=.14,wspace=.26,hspace=.4)
    fig.text(.04,.04,'Missing early catalog / provider history and missing PQD quarters remain gaps, not zero.\nSources: CISA; official provider histories; BLS via FRED; DTCC PQD 6.5.2 / 6.5.3.',fontsize=10)
    fig.savefig(FIGURES/'expanded_risk_signal_history.png');return fig
