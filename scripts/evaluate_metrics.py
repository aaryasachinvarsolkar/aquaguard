import joblib
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    classification_report, confusion_matrix, roc_auc_score,
    f1_score, recall_score, precision_score
)

SEED = 42

# ── Rebuild the same dataset used for training ─────────────────────────────
df_real = pd.read_csv('data_processed/training_dataset.csv')
df_real['turbidity'] = df_real['turbidity'].fillna(
    0.05 + 0.08 * df_real['chlorophyll']).clip(0.01, 3.0)

rng = np.random.default_rng(SEED)
regions = {
    'tropical_indian':  (28.5,1.0,0.8,0.6,(-10,25),0.25),
    'tropical_pacific': (27.5,1.5,0.5,0.4,(-15,20),0.15),
    'temperate':        (18.0,5.0,2.0,1.5,(30,60),0.20),
    'upwelling':        (16.0,3.0,8.0,4.0,(-30,10),0.15),
    'arctic':           (4.0,3.0,1.5,1.0,(60,85),0.10),
    'bloom_hotspot':    (22.0,4.0,12.0,5.0,(40,70),0.15),
}
rows = []
for region,(tm,ts,cm,cs,(la,lb),w) in regions.items():
    n = int(6000*w)
    temp = rng.normal(tm,ts,n).clip(0,35)
    chl  = np.abs(rng.lognormal(np.log(cm+0.01),cs/(cm+1),n)).clip(0.01,30)
    turb = (0.05+0.08*chl+rng.normal(0,0.05,n)).clip(0.01,3.0)
    lat  = rng.uniform(la,lb,n)
    bloom_prob = 1/(1+np.exp(-2.0*(chl-4.0)))+rng.normal(0,0.07,n)
    bloom = (bloom_prob.clip(0,1)>0.5).astype(int)
    risk_score = 0.40*(chl/5.0)+0.35*((temp-27)/4.0).clip(-1,1)+0.25*(turb/0.5).clip(0,2)
    risk_prob = 1/(1+np.exp(-2.0*(risk_score-0.5)))+rng.normal(0,0.09,n)
    risk = (risk_prob.clip(0,1)>0.5).astype(int)
    for i in range(n):
        rows.append({
            'latitude': lat[i], 'longitude': rng.uniform(60,100),
            'temperature': round(temp[i],4), 'chlorophyll': round(chl[i],4),
            'turbidity': round(turb[i],4), 'bloom': bloom[i], 'risk': risk[i]
        })

df_syn = pd.DataFrame(rows)
df_real_c = df_real[['latitude','longitude','temperature','chlorophyll','turbidity','bloom','risk']].copy()
df = pd.concat([df_real_c, df_syn], ignore_index=True).sample(frac=1, random_state=SEED).reset_index(drop=True)

df['chl_log']            = np.log1p(df['chlorophyll'])
df['chl_temp']           = df['chlorophyll'] * df['temperature']
df['temp_anomaly']       = (df['temperature'] - 28.0).abs()
df['turb_chl_ratio']     = df['turbidity'] / (df['chlorophyll'] + 0.01)
df['chl_squared']        = df['chlorophyll'] ** 2
df['temp_chl_bloom_idx'] = (df['chlorophyll']>3).astype(float)*(df['temperature']>27).astype(float)
df['is_tropical']        = (df['latitude'].abs()<23.5).astype(float)
df['lat_abs']            = df['latitude'].abs()

FEATURES = ['temperature','chlorophyll','turbidity','chl_log','chl_temp',
            'temp_anomaly','turb_chl_ratio','chl_squared','temp_chl_bloom_idx',
            'is_tropical','lat_abs']
X = df[FEATURES]

SEP = '=' * 58

# ── RISK MODEL ─────────────────────────────────────────────────────────────
print(SEP)
print('  RISK MODEL  (GradientBoosting)')
print(SEP)
risk_model = joblib.load('models/risk_model.pkl')
y_risk = df['risk']
_, X_te, _, y_te = train_test_split(X, y_risk, test_size=0.2, random_state=SEED, stratify=y_risk)
y_pred = risk_model.predict(X_te)
y_prob = risk_model.predict_proba(X_te)[:,1]
print(classification_report(y_te, y_pred, target_names=['Low Risk','High Risk'], digits=4))
print('  ROC-AUC :', round(roc_auc_score(y_te, y_prob), 4))
cm = confusion_matrix(y_te, y_pred)
print(f'  Confusion Matrix:  TN={cm[0,0]}  FP={cm[0,1]}  FN={cm[1,0]}  TP={cm[1,1]}')

# ── BLOOM MODEL ────────────────────────────────────────────────────────────
print()
print(SEP)
print('  BLOOM MODEL  (XGBoost + Calibration)')
print(SEP)
bloom_model = joblib.load('models/bloom_model.pkl')
y_bloom = df['bloom']
_, X_te, _, y_te = train_test_split(X, y_bloom, test_size=0.2, random_state=SEED, stratify=y_bloom)
y_pred = bloom_model.predict(X_te)
y_prob = bloom_model.predict_proba(X_te)[:,1]
print(classification_report(y_te, y_pred, target_names=['No Bloom','Bloom'], digits=4))
print('  ROC-AUC :', round(roc_auc_score(y_te, y_prob), 4))
cm = confusion_matrix(y_te, y_pred)
print(f'  Confusion Matrix:  TN={cm[0,0]}  FP={cm[0,1]}  FN={cm[1,0]}  TP={cm[1,1]}')

# ── OIL SPILL MODEL ────────────────────────────────────────────────────────
print()
print(SEP)
print('  OIL SPILL MODEL  (XGBoost + SAR features)')
print(SEP)
oil_data  = joblib.load('models/oil_spill_model.pkl')
oil_model = oil_data['model']
SAR_FEATURES = oil_data['features']

rng2 = np.random.default_rng(SEED)
n=5000; nc=int(n*0.72); ns=n-nc
sar_c=rng2.normal(-12,4.5,nc); tc=rng2.uniform(5,33,nc); cc=np.abs(rng2.lognormal(0.1,0.8,nc)).clip(0.01,20)
wc=rng2.uniform(1,15,nc); wvc=rng2.uniform(0.3,4.0,nc); lc=(rng2.random(nc)<0.04).astype(int)
sar_s=rng2.normal(-22,3.5,ns); ts=rng2.uniform(5,33,ns); cs2=np.abs(rng2.lognormal(0.1,0.8,ns)).clip(0.01,20)
ws=rng2.uniform(0.5,8,ns); wvs=rng2.uniform(0.1,1.5,ns); ls=np.where(rng2.random(ns)<0.04,0,1)
df_sar = pd.DataFrame({
    'sar_vv':       np.concatenate([sar_c,sar_s]).round(4),
    'temperature':  np.concatenate([tc,ts]).round(4),
    'chlorophyll':  np.concatenate([cc,cs2]).round(4),
    'wind_speed':   np.concatenate([wc,ws]).round(4),
    'wave_height':  np.concatenate([wvc,wvs]).round(4),
    'sar_wind_ratio': (np.concatenate([sar_c,sar_s])/(np.concatenate([wc,ws])+0.1)).round(4),
    'oil_spill':    np.concatenate([lc,ls])
}).sample(frac=1, random_state=SEED).reset_index(drop=True)

X_sar = df_sar[SAR_FEATURES]; y_sar = df_sar['oil_spill']
_, X_te, _, y_te = train_test_split(X_sar, y_sar, test_size=0.2, random_state=SEED, stratify=y_sar)
y_pred = oil_model.predict(X_te)
y_prob = oil_model.predict_proba(X_te)[:,1]
print(classification_report(y_te, y_pred, target_names=['No Spill','Oil Spill'], digits=4))
print('  ROC-AUC :', round(roc_auc_score(y_te, y_prob), 4))
cm = confusion_matrix(y_te, y_pred)
print(f'  Confusion Matrix:  TN={cm[0,0]}  FP={cm[0,1]}  FN={cm[1,0]}  TP={cm[1,1]}')

# ── SUMMARY TABLE ──────────────────────────────────────────────────────────
print()
print(SEP)
print('  SUMMARY')
print(SEP)
print(f"{'Model':<22} {'Precision':>10} {'Recall':>10} {'F1':>10} {'AUC':>10}")
print('-' * 58)

risk_model2 = joblib.load('models/risk_model.pkl')
_, Xte, _, yte = train_test_split(X, df['risk'], test_size=0.2, random_state=SEED, stratify=df['risk'])
yp = risk_model2.predict(Xte); ypr = risk_model2.predict_proba(Xte)[:,1]
print(f"{'Risk (High Risk)':<22} {precision_score(yte,yp):>10.4f} {recall_score(yte,yp):>10.4f} {f1_score(yte,yp):>10.4f} {roc_auc_score(yte,ypr):>10.4f}")

bloom_model2 = joblib.load('models/bloom_model.pkl')
_, Xte, _, yte = train_test_split(X, df['bloom'], test_size=0.2, random_state=SEED, stratify=df['bloom'])
yp = bloom_model2.predict(Xte); ypr = bloom_model2.predict_proba(Xte)[:,1]
print(f"{'Bloom (Bloom)':<22} {precision_score(yte,yp):>10.4f} {recall_score(yte,yp):>10.4f} {f1_score(yte,yp):>10.4f} {roc_auc_score(yte,ypr):>10.4f}")

_, Xte, _, yte = train_test_split(X_sar, y_sar, test_size=0.2, random_state=SEED, stratify=y_sar)
yp = oil_model.predict(Xte); ypr = oil_model.predict_proba(Xte)[:,1]
print(f"{'Oil Spill':<22} {precision_score(yte,yp):>10.4f} {recall_score(yte,yp):>10.4f} {f1_score(yte,yp):>10.4f} {roc_auc_score(yte,ypr):>10.4f}")
print(SEP)
